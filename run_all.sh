#!/usr/bin/env bash
# Полный прогон очереди экспериментов «из коробки»: окружение -> .env -> проверка -> G0..G5 -> архив результатов.
#
# Запуск (ключ и модели передаются переменными окружения):
#   LLM_KEY=... LLM_MODEL=... LLM_MODEL_JUDGE=... bash run_all.sh
#
# Если .env уже лежит рядом — переменные не нужны, скрипт возьмёт его.
# Любые аргументы пробрасываются в run_queue.py, например:
#   bash run_all.sh --only g0
#   bash run_all.sh --from g2 --workers 16
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\n\033[1m=== %s ===\033[0m\n' "$*"; }

# --- 1. Python и виртуальное окружение -------------------------------------
say "1/5  Окружение"
PY=python3; command -v python3 >/dev/null 2>&1 || PY=python
command -v "$PY" >/dev/null 2>&1 || { echo "НЕТ python3 — установи Python 3.10+"; exit 1; }
if [ ! -d .venv ]; then
  "$PY" -m venv .venv || { echo "venv не создался (нужен пакет python3-venv)"; exit 1; }
fi
# shellcheck disable=SC1091
if   [ -f .venv/bin/activate ]; then source .venv/bin/activate      # Linux/macOS
elif [ -f .venv/Scripts/activate ]; then source .venv/Scripts/activate  # Windows (Git Bash)
else echo "venv не создался (нужен пакет python3-venv)"; exit 1; fi
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "python: $(python --version), зависимости установлены"

# --- 2. .env из переменных окружения (если файла ещё нет) -------------------
say "2/5  Конфигурация (.env)"
if [ -f .env ]; then
  echo ".env уже есть — использую его"
else
  : "${LLM_KEY:?задай ключ:  LLM_KEY=... bash run_all.sh}"
  : "${LLM_MODEL:?задай имя модели:  LLM_MODEL=... bash run_all.sh}"
  cat > .env <<EOF
LLM_URL=${LLM_URL:-https://gigagateway.eye.salute.ru/litellm/v1/chat/completions}
LLM_KEY=${LLM_KEY}
LLM_PROVIDER=${LLM_PROVIDER:-alibaba}
LLM_MODEL=${LLM_MODEL}
LLM_MODEL_JUDGE=${LLM_MODEL_JUDGE:-${LLM_MODEL}}
LLM_MODEL_GLM=${LLM_MODEL_GLM:-}
LLM_USE_CURL=${LLM_USE_CURL:-0}
EOF
  chmod 600 .env
  echo ".env создан из переменных окружения (модель: ${LLM_MODEL})"
fi

# --- 3. Проверка доступа к гейтвею ------------------------------------------
say "3/5  Проверка эндпоинтов"
python scripts/check_endpoints.py || {
  echo; echo "Эндпоинты не отвечают — очередь НЕ запускаю."
  echo "Проверь LLM_KEY и имена моделей. Если ошибка SSL — LLM_USE_CURL=1 bash run_all.sh"
  exit 1
}

# --- 4. Очередь экспериментов G0 -> G2 -> G4 -> G5 --------------------------
say "4/5  Очередь экспериментов"
set +e
python scripts/run_queue.py "$@"
RC=$?
set -e
if [ $RC -ne 0 ]; then
  echo; echo "Очередь остановилась с кодом $RC (см. вывод выше и results/logs/)."
  echo "После исправления просто перезапусти: bash run_all.sh --from <шаг>"
fi

# --- 5. Упаковка результатов -------------------------------------------------
say "5/5  Упаковка результатов"
tar -czf results_bundle.tar.gz --exclude='results/v4_dash' results/ 2>/dev/null || true
echo "Готово. Прислать обратно: results_bundle.tar.gz"
echo "Дашборды: results/dashboards/index.html"
exit $RC
