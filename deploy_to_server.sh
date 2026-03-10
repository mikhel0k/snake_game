#!/bin/bash
# Выкладка сервера змейки на удалённый хост.
# Использование: ./deploy_to_server.sh [user@host]
# По умолчанию: root@176.57.215.99 (замени на свой сервер).

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

SERVER="${1:-root@176.57.215.99}"
REMOTE_DIR="/opt/snake-game"

echo "Копирую файлы на $SERVER:$REMOTE_DIR ..."
ssh "$SERVER" "mkdir -p $REMOTE_DIR"
# Не используем --delete, чтобы не затереть generated_players.json на сервере
rsync -avz \
  --exclude='pack_for_students' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.git' \
  --exclude='*.pyc' \
  --exclude='.env' \
  --exclude='generated_players.json' \
  --exclude='run_game.py' \
  --exclude='deploy_to_server.sh' \
  ./ "$SERVER:$REMOTE_DIR/"

echo "Пересборка и перезапуск контейнера на сервере..."
ssh "$SERVER" "cd $REMOTE_DIR && \
  docker stop snake-game 2>/dev/null || true && \
  docker rm snake-game 2>/dev/null || true && \
  docker build --no-cache -t snake-server . && \
  docker run -d -p 8002:8002 --name snake-game snake-server"

echo "Готово. Сервер: http://${SERVER#*@}:8002/  (админка: /admin)"
