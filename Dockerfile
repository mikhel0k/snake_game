# Образ только для сервера игры (без бота для студентов).
# Сборка: docker build -t snake-server .
# Запуск: docker run -p 8002:8002 snake-server
# Учётные данные: смонтируй свой credentials.json или задай CREDENTIALS_FILE.

FROM python:3.11-slim

WORKDIR /app

# Зависимости сервера
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код сервера и статика (pack_for_students в образ не попадает благодаря .dockerignore)
COPY main.py game.py levels.py ./
COPY static/ ./static/

# Файл учётных данных: по умолчанию пустой (нет игроков).
# Чтобы добавить игроков — смонтируй свой credentials.json: -v /path/to/credentials.json:/app/credentials.json
RUN echo '{"admin_password": "", "players": [], "game_started": false, "level": 1}' > credentials.json

EXPOSE 8002

# Запуск uvicorn как в run_game.py
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
