"""
FastAPI: змейка с авторизацией, админкой и режимом наблюдения.
Пароль админа фиксированный. Аккаунты игроков создаются один раз при первом запуске игры:
админ вводит логины (или оставляет player_1, player_2, …), сервер генерирует пароли и сохраняет
в файл; при следующих стартах используются те же логины/пароли, выбирается только уровень.
"""
import asyncio
import json
import os
import secrets
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Header, Request, Form
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from game import GameState, Direction


# Фиксированный пароль админа. Аккаунты игроков создаются один раз при первом старте игры.
ADMIN_PASSWORD = "Edhvevcbbohc"

# Файл с сохранёнными логинами/паролями (создаётся при первом запуске игры, переиспользуется потом).
GENERATED_PLAYERS_FILE = os.environ.get(
    "GENERATED_PLAYERS_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_players.json"),
)


def _generate_passwords_for_logins(logins: list[str]) -> list[dict]:
    """По списку логинов сгенерировать пароли. Логин не пустой и не только пробелы."""
    out = []
    for login in logins:
        s = (login or "").strip()
        if not s:
            continue
        out.append({"login": s, "password": secrets.token_urlsafe(10)[:10]})
    return out


def _default_logins(count: int) -> list[str]:
    """player_1 … player_N."""
    return [f"player_{i}" for i in range(1, count + 1)]


game = GameState()


def _load_generated_players() -> list[dict]:
    """Загрузить сохранённый список игроков из файла (если есть)."""
    path = GENERATED_PLAYERS_FILE
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) > 0:
            return data
    except Exception:
        pass
    return []


def _save_generated_players(players: list[dict]) -> None:
    """Сохранить список игроков в файл (для повторного использования)."""
    path = GENERATED_PLAYERS_FILE
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(players, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.admin_token = None
    loaded = _load_generated_players()
    app.state.current_players = loaded
    app.state.players_initialized = len(loaded) > 0  # один раз создали — дальше только уровень
    async def game_loop():
        while True:
            await asyncio.sleep(0.25)  # 4 тика в секунду
            await game.do_tick()
    task = asyncio.create_task(game_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Snake API", lifespan=lifespan)


class DirectionRequest(BaseModel):
    direction: str


WORLD_VIEW_RADIUS = 25


def _get_current_players(request: Request) -> list[dict]:
    return getattr(request.app.state, "current_players", []) or []


def _check_player(players: list[dict], player_id: str, password: str) -> bool:
    for p in players:
        if p.get("login") == player_id and p.get("password") == password:
            return True
    return False


def _check_admin(request: Request, password: str) -> bool:
    return password == ADMIN_PASSWORD


@app.get("/world")
async def get_world(
    request: Request,
    player_id: str,
    password: str,
    name: str = "Player",
):
    """Мир в радиусе 25 от головы. Требуется player_id и password (выдаются админом при старте игры)."""
    players = _get_current_players(request)
    if not _check_player(players, player_id, password):
        raise HTTPException(status_code=401, detail="Invalid login or password")
    await game.set_player_name(player_id, name)
    if not game.game_started:
        return {"game_started": False, "message": "Ожидание старта от админа"}
    data = game.get_world_around(player_id, WORLD_VIEW_RADIUS)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    data["game_started"] = True
    data["sleep_until_next_tick"] = await game.get_sleep_until_next_tick()
    return data


@app.post("/step")
async def step(
    request: Request,
    player_id: str,
    password: str,
    req: DirectionRequest,
):
    """Ход. Только для залогиненного игрока, только когда игра запущена."""
    players = _get_current_players(request)
    if not _check_player(players, player_id, password):
        raise HTTPException(status_code=401, detail="Invalid login or password")
    if not game.game_started:
        raise HTTPException(status_code=400, detail="Game not started")
    try:
        d = Direction(req.direction.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid direction: up/down/left/right")
    ok = await game.set_direction(player_id, d)
    if not ok:
        raise HTTPException(status_code=404, detail="Player not found or dead")
    sleep_until = await game.get_sleep_until_next_tick()
    return {"ok": True, "sleep_until_next_tick": sleep_until}


@app.get("/spectate")
async def spectate():
    """Полное состояние для наблюдателей (без авторизации)."""
    return game.get_state()


def _admin_password(request: Request, x_admin_password: str | None = Header(None)):
    if not x_admin_password or not _check_admin(request, x_admin_password):
        raise HTTPException(status_code=401, detail="Invalid admin password")
    return x_admin_password


def _is_admin(request: Request) -> bool:
    """Проверка: пароль в заголовке или валидный cookie."""
    pw = request.headers.get("X-Admin-Password")
    if pw and _check_admin(request, pw):
        return True
    token = request.cookies.get("admin_session")
    if token and getattr(request.app.state, "admin_token", None) == token:
        return True
    return False


@app.get("/admin/login")
async def admin_login_get():
    """GET на /admin/login — просто на /admin (чтобы обновление не давало 405)."""
    return RedirectResponse("/admin", status_code=302)


@app.post("/admin/login")
async def admin_login(request: Request, password: str = Form(...)):
    """Вход по фиксированному паролю админа. При успехе — страница админки с cookie."""
    if not _check_admin(request, password):
        return RedirectResponse("/admin?error=1", status_code=303)
    request.app.state.admin_token = secrets.token_urlsafe(32)
    html_path = static_dir / "admin.html"
    raw = html_path.read_text(encoding="utf-8")
    inject = '<script>(function(){var lb=document.getElementById("loginBox");var d=document.getElementById("dashboard");if(lb)lb.style.display="none";if(d){d.classList.add("visible");d.style.display="block";}window.__adminCookie=1;history.replaceState(null,"","/admin");})();</script>'
    raw = raw.replace("</body>", inject + "</body>", 1)
    r = Response(content=raw, media_type="text/html", headers=_no_cache_headers)
    r.set_cookie("admin_session", request.app.state.admin_token, max_age=86400, path="/", samesite="lax")
    return r


@app.get("/admin/state")
async def admin_state(request: Request, _: str = Header(None, alias="X-Admin-Password")):
    """Состояние для админки. Авторизация: заголовок X-Admin-Password или cookie admin_session."""
    if not _is_admin(request):
        raise HTTPException(status_code=401, detail="Invalid admin password")
    state = game.get_state()
    state["credentials_players"] = _get_current_players(request)
    state["players_initialized"] = getattr(request.app.state, "players_initialized", False)
    return state


@app.post("/admin/start")
async def admin_start(request: Request):
    """
    Старт раунда. Cookie или X-Admin-Password.
    Если аккаунты ещё не созданы (первый запуск): JSON {level, logins: ["a","b",...]} или {level, player_count: N}.
    Если уже созданы: JSON {level} — используются те же логины/пароли.
    """
    if not _is_admin(request):
        raise HTTPException(status_code=401, detail="Invalid admin password")
    level_val = 1
    players = getattr(request.app.state, "current_players", []) or []
    initialized = getattr(request.app.state, "players_initialized", False)

    ct = request.headers.get("content-type", "") or ""
    if "application/json" in ct:
        try:
            body = await request.json()
            level_val = max(1, min(5, int(body.get("level", 1))))
            if not initialized:
                logins = body.get("logins")
                if isinstance(logins, list) and len(logins) > 0:
                    logins = [str(x).strip() for x in logins if str(x).strip()]
                if not logins:
                    player_count = max(1, min(10, int(body.get("player_count", 6))))
                    logins = _default_logins(player_count)
                players = _generate_passwords_for_logins(logins)
                if not players:
                    raise HTTPException(status_code=400, detail="Нужен хотя бы один логин или player_count")
                request.app.state.current_players = players
                request.app.state.players_initialized = True
                _save_generated_players(players)
        except HTTPException:
            raise
        except (TypeError, ValueError, KeyError):
            if not initialized:
                raise HTTPException(status_code=400, detail="При первом запуске нужны logins или player_count")
    else:
        form = await request.form()
        try:
            level_val = max(1, min(5, int(form.get("level", 1))))
            if not initialized:
                raw = (form.get("logins") or "").strip()
                if raw:
                    logins = [s.strip() for s in raw.replace(",", "\n").splitlines() if s.strip()]
                else:
                    player_count = max(1, min(10, int(form.get("player_count", 6))))
                    logins = _default_logins(player_count)
                players = _generate_passwords_for_logins(logins)
                if not players:
                    raise ValueError("empty")
                request.app.state.current_players = players
                request.app.state.players_initialized = True
                _save_generated_players(players)
        except (TypeError, ValueError):
            if not initialized:
                raise HTTPException(status_code=400, detail="При первом запуске нужны logins или player_count")

    player_ids = [p["login"] for p in players]
    await game.start_game(level_val, player_ids)
    return {"ok": True, "level": level_val, "players": players, "players_initialized": request.app.state.players_initialized}


# Статика и страницы (без mount на "/", чтобы не перехватывать /admin/state)
static_dir = Path(__file__).parent / "static"
_no_cache_headers = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}

if static_dir.exists():
    @app.get("/")
    async def index():
        return FileResponse(static_dir / "index.html", headers=_no_cache_headers)

    async def _admin_html(request: Request):
        html_path = static_dir / "admin.html"
        raw = html_path.read_text(encoding="utf-8")
        if _is_admin(request):
            inject = '<script>(function(){var lb=document.getElementById("loginBox");var d=document.getElementById("dashboard");if(lb)lb.style.display="none";if(d){d.classList.add("visible");d.style.display="block";}window.__adminCookie=1;})();</script>'
            raw = raw.replace("</body>", inject + "</body>", 1)
        return Response(content=raw, media_type="text/html", headers=_no_cache_headers)

    @app.get("/admin")
    async def admin_page(request: Request):
        return await _admin_html(request)

    @app.get("/admin/")
    async def admin_page_slash(request: Request):
        return await _admin_html(request)

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
