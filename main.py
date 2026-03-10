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
import time
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Header, Request, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
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


async def broadcast_after_tick(app: FastAPI) -> None:
    """Разослать состояние игры всем подключённым по WebSocket после тика."""
    ws_players = getattr(app.state, "ws_players", {}) or {}
    ws_spectators = getattr(app.state, "ws_spectators", set()) or set()
    for player_id, ws in list(ws_players.items()):
        try:
            data = game.get_world_around(player_id, WORLD_VIEW_RADIUS)
            if "error" in data:
                continue
            data["game_started"] = game.game_started
            data["game_ended"] = game.game_ended
            data["sleep_until_next_tick"] = await game.get_sleep_until_next_tick()
            await ws.send_json(data)
        except Exception:
            try:
                await ws.close()
            except Exception:
                pass
            ws_players.pop(player_id, None)
    for ws in list(ws_spectators):
        try:
            await ws.send_json(game.get_state())
        except Exception:
            try:
                await ws.close()
            except Exception:
                pass
            ws_spectators.discard(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.admin_token = None
    app.state.ws_players = {}
    app.state.ws_spectators = set()
    loaded = _load_generated_players()
    app.state.current_players = loaded
    app.state.players_initialized = len(loaded) > 0  # один раз создали — дальше только уровень
    game.load_game_history()  # загрузить сохранённые результаты игр (кто сколько скушал)

    async def game_loop():
        TICK_TIMEOUT = 2.0  # ждём ходы от всех; если не все за 2 сек — тик по таймауту
        POLL_INTERVAL = 0.02
        next_tick_at = time.monotonic() + TICK_TIMEOUT
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            now = time.monotonic()
            all_ready = await game.all_players_ready_for_tick()
            if all_ready or now >= next_tick_at:
                await game.do_tick()
                next_tick_at = now + TICK_TIMEOUT
                await broadcast_after_tick(app)

    task = asyncio.create_task(game_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Snake API", lifespan=lifespan)


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
async def get_world_deprecated():
    """Игра только по WebSocket. Подключайтесь к ws://HOST/ws/play?player_id=...&password=..."""
    raise HTTPException(status_code=410, detail="Use WebSocket: /ws/play?player_id=...&password=...")


@app.post("/step")
async def step_deprecated():
    """Игра только по WebSocket. Подключайтесь к /ws/play и шлите JSON {\"direction\": \"up\"}."""
    raise HTTPException(status_code=410, detail="Use WebSocket: /ws/play")


@app.get("/ping")
async def ping():
    """Проверка доступности и замер пинга. Без авторизации. Клиент замеряет RTT по времени ответа."""
    return {"ok": True}


@app.get("/spectate")
async def spectate():
    """Полное состояние для наблюдателей (без авторизации). Для пуша в реальном времени — WebSocket /ws/spectate."""
    return game.get_state()


@app.websocket("/ws/play")
async def ws_play(websocket: WebSocket):
    """
    Игрок подключается по WebSocket: в query player_id, password, name (опц.).
    Сервер пушит состояние после каждого тика. Клиент шлёт JSON {"direction": "up"} для хода.
    """
    await websocket.accept()
    player_id = websocket.query_params.get("player_id") or ""
    password = websocket.query_params.get("password") or ""
    name = (websocket.query_params.get("name") or "").strip() or "Player"
    players = getattr(websocket.app.state, "current_players", []) or []
    if not _check_player(players, player_id, password):
        await websocket.close(code=4001)
        return
    await game.set_player_name(player_id, name)
    ws_players = websocket.app.state.ws_players
    ws_players[player_id] = websocket
    try:
        data = game.get_world_around(player_id, WORLD_VIEW_RADIUS)
        if "error" not in data:
            data["game_started"] = game.game_started
            data["game_ended"] = game.game_ended
            data["sleep_until_next_tick"] = await game.get_sleep_until_next_tick()
            await websocket.send_json(data)
        while True:
            msg = await websocket.receive_text()
            try:
                obj = json.loads(msg)
                d = (obj.get("direction") or "").strip().lower()
                if d in ("up", "down", "left", "right"):
                    direction = Direction(d)
                    await game.set_direction(player_id, direction)
            except (json.JSONDecodeError, ValueError):
                pass
    except WebSocketDisconnect:
        pass
    finally:
        ws_players.pop(player_id, None)


@app.websocket("/ws/spectate")
async def ws_spectate(websocket: WebSocket):
    """Наблюдатель: подключается без авторизации, получает полное состояние после каждого тика."""
    await websocket.accept()
    ws_spectators = websocket.app.state.ws_spectators
    ws_spectators.add(websocket)
    try:
        await websocket.send_json(game.get_state())
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_spectators.discard(websocket)


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

    grid_width = None
    grid_height = None
    obstacles = None
    duration_seconds = None

    ct = request.headers.get("content-type", "") or ""
    if "application/json" in ct:
        try:
            body = await request.json()
            level_val = max(1, min(5, int(body.get("level", 1))))
            if body.get("grid_width") is not None:
                grid_width = max(10, min(150, int(body.get("grid_width"))))
            if body.get("grid_height") is not None:
                grid_height = max(10, min(150, int(body.get("grid_height"))))
            if body.get("obstacles") is not None:
                obstacles = max(0, min(2000, int(body.get("obstacles"))))
            if body.get("duration_seconds") is not None:
                duration_seconds = max(10, min(3600, float(body.get("duration_seconds"))))
            elif body.get("duration_minutes") is not None:
                duration_seconds = max(0.5, min(60, float(body.get("duration_minutes")))) * 60
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
            if form.get("grid_width"):
                grid_width = max(10, min(150, int(form.get("grid_width"))))
            if form.get("grid_height"):
                grid_height = max(10, min(150, int(form.get("grid_height"))))
            if form.get("obstacles") is not None and form.get("obstacles") != "":
                obstacles = max(0, min(2000, int(form.get("obstacles"))))
            if form.get("duration_seconds"):
                duration_seconds = max(10, min(3600, float(form.get("duration_seconds"))))
            elif form.get("duration_minutes"):
                duration_seconds = max(0.5, min(60, float(form.get("duration_minutes")))) * 60
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
    await game.start_game(
        level_val,
        player_ids,
        grid_width=grid_width,
        grid_height=grid_height,
        obstacles=obstacles,
        duration_seconds=duration_seconds,
    )
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
