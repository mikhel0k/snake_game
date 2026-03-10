#!/usr/bin/env python3
"""
Точка входа для бота.

Запуск: python bot.py [BASE_URL] [PLAYER_ID] [PASSWORD] [NAME]
  BASE_URL   — адрес сервера (например http://127.0.0.1:8002)
  PLAYER_ID  — логин игрока
  PASSWORD  — пароль (обязателен)
  NAME      — отображаемое имя (опционально)

Вся логика в пакете snake_bot. Игра только по WebSocket (ws://.../ws/play). Нужно: pip install websockets.
"""
from snake_bot.main import run

if __name__ == "__main__":
    run()
