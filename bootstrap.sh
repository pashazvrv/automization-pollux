#!/usr/bin/env bash
# Bootstrap: подтягивает репозиторий и запускает всю очередь экспериментов.
# Запуск:
#   LLM_KEY=... LLM_MODEL=... bash bootstrap.sh
# Аргументы пробрасываются в run_all.sh (например: bash bootstrap.sh --only g0).
set -euo pipefail

REPO_URL="${POLLUX_REPO:-__REPO_URL__}"   # можно переопределить: POLLUX_REPO=... bash bootstrap.sh
DIR=atomization-pollux

if [ "$REPO_URL" = "__REPO_URL__" ]; then
  echo "Не задан адрес репозитория. Либо впиши его в REPO_URL в этом файле,"
  echo "либо запусти:  POLLUX_REPO=<url> LLM_KEY=... LLM_MODEL=... bash bootstrap.sh"
  exit 1
fi

if [ -d "$DIR/.git" ]; then
  echo "=== репозиторий уже есть, обновляю ==="
  git -C "$DIR" pull --ff-only
else
  echo "=== клонирую $REPO_URL ==="
  git clone "$REPO_URL" "$DIR"
fi

cd "$DIR"
exec bash run_all.sh "$@"
