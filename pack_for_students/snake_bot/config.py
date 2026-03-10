"""
Настройки бота: URL, учётные данные, константы направлений.

Разделение: только конфиг и константы, без логики.
Меняй BASE_URL, PLAYER_ID, PASSWORD при запуске через аргументы (см. from_argv) или правь значения здесь.
"""
import sys

# ---------------------------------------------------------------------------
# Направления и запрет разворота на 180°
# Змейка не может в следующем тике пойти «назад» (голова врезается в шею).
# OPPOSITE используется в world.safe_directions() для отсечения такого хода.
# ---------------------------------------------------------------------------
DIRECTIONS = ("up", "down", "left", "right")
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}

# ---------------------------------------------------------------------------
# Подключение к серверу (переопределяются из sys.argv в from_argv() или при запуске bot.py)
# BASE_URL — без завершающего слэша; по умолчанию локальный сервер на порту 8002.
# PLAYER_ID и PASSWORD задайте при запуске: python bot.py BASE_URL PLAYER_ID PASSWORD [NAME]
# ---------------------------------------------------------------------------
BASE_URL = "http://176.57.215.99:8002/"
PLAYER_ID = "3"
PASSWORD = "9JFGlT_ac9"  # обязательно укажите при запуске или в аргументах
NAME = "HUY"

# ---------------------------------------------------------------------------
# Тайминги
# TICK_INTERVAL: пауза между запросами world+step (только для HTTP).
# RETRY_INTERVAL: пауза при ошибке/ожидании старта/конце игры перед повтором.
# ---------------------------------------------------------------------------
TICK_INTERVAL = 0.5
RETRY_INTERVAL = 2.0

def from_argv() -> None:
    """
    Обновить BASE_URL, PLAYER_ID, PASSWORD, NAME из sys.argv.

    Варианты:
      python bot.py BASE_URL PLAYER_ID PASSWORD [NAME]
      python bot.py PLAYER_ID PASSWORD [NAME]   — URL берётся из config (по умолчанию localhost:8002)
    Вызывается один раз при старте в main.run().
    """
    global BASE_URL, PLAYER_ID, PASSWORD, NAME
    args = [a for a in sys.argv[1:] if a]
    if len(args) >= 4:
        BASE_URL = args[0].rstrip("/")
        PLAYER_ID = args[1]
        PASSWORD = args[2]
        NAME = args[3]
    elif len(args) == 3:
        BASE_URL = args[0].rstrip("/")
        PLAYER_ID = args[1]
        PASSWORD = args[2]
    elif len(args) == 2:
        # Без URL: два аргумента = PLAYER_ID, PASSWORD (BASE_URL остаётся из config)
        PLAYER_ID = args[0]
        PASSWORD = args[1]
    elif len(args) == 1:
        if args[0].startswith("http://") or args[0].startswith("https://"):
            BASE_URL = args[0].rstrip("/")
        else:
            PLAYER_ID = args[0]
