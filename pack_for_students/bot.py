#!/usr/bin/env python3
"""
Точка входа для бота.

Запуск: python bot.py [BASE_URL] [PLAYER_ID] [PASSWORD] [NAME]
  BASE_URL   — адрес сервера (например http://127.0.0.1:8002)
  PLAYER_ID  — логин игрока
  PASSWORD  — пароль (обязателен)
  NAME      — отображаемое имя (опционально)

Игра только по WebSocket (ws://.../ws/play). Нужно: pip install websockets.
"""
import sys
from pathlib import Path

# Чтобы при запуске python bot.py из pack_for_students находился пакет pack_for_students
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from pack_for_students.main import run

if __name__ == "__main__":
    run()
