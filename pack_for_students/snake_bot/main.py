"""
Главный цикл бота: опрос мира, проверки состояния, вызов стратегии, отправка хода.

Один тик: get_world() → проверки (ошибка, игра не начата, конец, мы мёртвы) → choose_direction(world) → step() → sleep.
Решение «куда идти» принимается только в strategy.choose_direction. Чтобы подставить свою стратегию —
замени вызов choose_direction на свою функцию (world: dict) -> str.
Сон до следующего тика — по полю sleep_until_next_tick из ответа сервера, чтобы не проскакивать тики.
"""
import time

from snake_bot import config
from snake_bot.api import get_world, step
from snake_bot.strategy import choose_direction


def run() -> None:
    """
    Запустить бота: бесконечный цикл до Ctrl+C.
    Каждый тик: get_world → проверки (ошибка/не старт/конец/мёртв) → choose_direction → step → sleep.
    """
    config.from_argv()
    if not config.PASSWORD:
        print("Укажите пароль: python -m snake_bot [BASE_URL] [PLAYER_ID] [PASSWORD] [NAME]")
        raise SystemExit(1)

    print(f"Бот: {config.PLAYER_ID} ({config.NAME})")
    print(f"Сервер: {config.BASE_URL}")
    print("4 раза в секунду: world → step. Игра 3 мин. Ctrl+C — выход.\n")

    while True:
        # Запрашиваем мир (GET /world)
        world = get_world()
        if world is None:
            print("Нет ответа от сервера, повтор через 2 сек...")
            time.sleep(config.RETRY_INTERVAL)
            continue
        if "error" in world:
            print(f"Ошибка: {world['error']}")
            time.sleep(config.RETRY_INTERVAL)
            continue
        if not world.get("game_started"):
            print("Ожидание старта игры админом...")
            time.sleep(config.RETRY_INTERVAL)
            continue
        if world.get("game_ended"):
            print("Игра окончена (3 мин). Ожидание новой игры...")
            time.sleep(config.RETRY_INTERVAL)
            continue

        # Достаём данные нашей змейки из ответа
        me = world.get("me") or {}
        tick = world.get("tick", 0)
        score = me.get("score", 0)
        alive = me.get("alive", False)

        if not alive:
            print(f"[тик {tick}] Мёртв, ждём респавн...")
            time.sleep(config.TICK_INTERVAL)
            continue

        # Единственный вызов стратегии: подставь свою функцию вместо choose_direction при необходимости
        direction = choose_direction(world)
        step_resp = step(direction)
        if step_resp:
            print(f"[тик {tick}] Очки: {score} → ход {direction}")
        else:
            print(f"[тик {tick}] Не удалось отправить ход")

        # Спим до следующего тика (сервер подсказывает время в sleep_until_next_tick)
        sleep_s = None
        if step_resp is not None:
            val = step_resp.get("sleep_until_next_tick")
            if val is not None and (type(val) is int or type(val) is float):
                sleep_s = float(val)
        if sleep_s is None:
            val = world.get("sleep_until_next_tick")
            if val is not None and (type(val) is int or type(val) is float):
                sleep_s = float(val)
        if sleep_s is None:
            sleep_s = config.TICK_INTERVAL
        if sleep_s < 0:
            sleep_s = 0.0
        if sleep_s > config.TICK_INTERVAL * 1.5:
            sleep_s = config.TICK_INTERVAL * 1.5
        time.sleep(sleep_s)
