"""
Вспомогательные HTTP-запросы (для тестов или своих скриптов). Игра идёт по WebSocket (/ws/play).
GET /world и POST /step на сервере возвращают 410 — используйте WebSocket. Функции get_world/step оставлены для совместимости.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

from pack_for_students import config


# ---------------------------------------------------------------------------
# Общая функция запроса (GET/POST)
# ---------------------------------------------------------------------------

def request(method: str, path: str, body: dict | None = None) -> dict | None:
    """
    Выполнить HTTP-запрос к серверу, вернуть разобранный JSON или None при ошибке.

    method — "GET" или "POST", path — например "/world?..." или "/step?...",
    body — для POST передаётся как JSON (для GET игнорируется).
    Таймаут 5 сек; при любой ошибке (сеть, HTTP 4xx/5xx) возвращается None и печатается сообщение.
    """
    url = config.BASE_URL.rstrip("/") + path
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    if body is not None:
        req.data = json.dumps(body).encode()  # POST body в JSON
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # Ограничиваем длину тела ответа в сообщении об ошибке
        print(f"HTTP {e.code}: {e.read().decode()[:200]}")
        return None
    except Exception as e:
        print(f"Ошибка: {e}")
        return None


# ---------------------------------------------------------------------------
# Получить мир (вызывается каждый тик в main)
# ---------------------------------------------------------------------------

def get_world() -> dict | None:
    """
    Получить текущее состояние мира для игрока (GET /world).

    В query передаются player_id, password, name из config.
    Ответ содержит me (тело, направление, очки, alive), apples, snakes, walls, tick, level и др.
    None при сетевой ошибке или неверном ответе.
    """
    # Параметры в query: player_id, password, name (опц.)
    q = f"player_id={config.PLAYER_ID}&password={urllib.parse.quote(config.PASSWORD)}&name={config.NAME}"
    return request("GET", f"/world?{q}")


# ---------------------------------------------------------------------------
# Отправить ход (направление после choose_direction в main)
# ---------------------------------------------------------------------------

def step(direction: str) -> dict | None:
    """
    Отправить один ход на сервер (POST /step).

    direction — "up" | "down" | "left" | "right".
    Возвращает ответ сервера (dict с ok, sleep_until_next_tick) при успехе, иначе None.
    Параметры player_id и password берутся из config.
    """
    q = f"player_id={config.PLAYER_ID}&password={urllib.parse.quote(config.PASSWORD)}"
    r = request("POST", f"/step?{q}", {"direction": direction})
    if r is not None and r.get("ok") is True:
        return r
    return None
