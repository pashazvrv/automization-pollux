@echo off
rem Запуск очереди экспериментов (G0 -> G2 -> G4 -> G5) с дашбордами после каждого шага.
rem Двойной клик = вся очередь. Аргументы пробрасываются, напр.: run_experiments.bat --only g0
cd /d %~dp0
if not exist .env (
  echo [ОШИБКА] Нет файла .env
  echo Скопируй .env.example в .env и впиши LLM_KEY, LLM_MODEL, LLM_MODEL_JUDGE
  pause
  exit /b 1
)
python scripts/run_queue.py --open %*
pause
