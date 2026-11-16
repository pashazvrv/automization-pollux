# Атомизация запросов POLLUX

Разбор запросов на Task / Task constraints / Format constraints / Context,
поиск неделимых запросов, многостадийный пайплайн и метрики качества.
Датасет: ai-forever/POLLUX (split test, пул ~1812 запросов).

## Структура
- PLAN.md — план работ и статус этапов
- SCHEMA.md — классы, правила разметки, критерии неделимости
- DECISIONS.md — журнал решений по схеме
- EXPERIMENTS.md — очередь экспериментов (что и как запускать)
- prompts/ — системные промпты стадий (только правила)
- prompts/fewshot/ — few-shot примеры к промптам (подаются отдельным блоком)
- src/ — клиент LLM (LiteLLM-гейтвей), пайплайн, валидатор, метрики
- scripts/ — подготовка данных, пилот, прогоны, оценка
- data/, gold/, results/, report/ — данные, золотой набор, прогоны, отчёт

## Старт
1. `cp .env.example .env` и заполнить `LLM_KEY` и имена моделей (в чат их не отправлять)
2. `pip install -r requirements.txt`
3. `python scripts/check_endpoints.py` — проверка гейтвея и моделей
