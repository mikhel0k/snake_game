"""
Главный цикл бота: только WebSocket. Подключаемся к ws://.../ws/play, получаем состояние пушами после каждого тика, шлём ход.
"""
import sys
from pathlib import Path

# Чтобы при запуске python main.py из pack_for_students находился пакет pack_for_students
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import asyncio
import json
from urllib.parse import quote

from pack_for_students import config
from pack_for_students.strategy import choose_direction


async def _run_ws() -> None:
    try:
        import websockets
    except ImportError:
        print("Установите: pip install websockets")
        raise SystemExit(1)
    config.from_argv()
    if not config.PASSWORD:
        print("Укажите пароль: python bot.py [BASE_URL] [PLAYER_ID] [PASSWORD] [NAME]")
        raise SystemExit(1)
    base = config.BASE_URL.rstrip("/").replace("http://", "ws://").replace("https://", "wss://")
    url = f"{base}/ws/play?player_id={quote(config.PLAYER_ID)}&password={quote(config.PASSWORD)}&name={quote(config.NAME)}"
    print(f"Бот: {config.PLAYER_ID} ({config.NAME})")
    print(f"WebSocket: {base}/ws/play?...")
    print("Ожидание состояния от сервера. Ctrl+C — выход.\n")
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                async for message in ws:
                    try:
                        world = json.loads(message)
                    except json.JSONDecodeError:
                        continue
                    if not world.get("game_started"):
                        continue
                    if world.get("game_ended"):
                        continue
                    me = world.get("me") or {}
                    if not me.get("alive", True):
                        continue
                    tick = world.get("tick", 0)
                    score = me.get("score", 0)
                    direction = choose_direction(world)
                    await ws.send(json.dumps({"direction": direction}))
                    print(f"[тик {tick}] Очки: {score} → ход {direction}")
        except Exception as e:
            print(f"Ошибка: {e}, переподключение через {config.RETRY_INTERVAL} сек...")
            await asyncio.sleep(config.RETRY_INTERVAL)


def run() -> None:
    """Точка входа: игра только по WebSocket."""
    config.from_argv()
    asyncio.run(_run_ws())


if __name__ == "__main__":
    run()
