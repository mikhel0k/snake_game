"""
Бот для игры в змейку по API.

Файлы: config (настройки), api (get_world, step), world (WorldView, next_head),
strategy (цели, путь, fallback, choose_direction), main (цикл run).
Точка входа: snake_bot.main.run() или python bot.py ...
"""
from snake_bot.main import run

__all__ = ["run"]
