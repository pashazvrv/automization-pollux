# Атомизация запросов POLLUX

Разбор запросов на Task / Task constraints / Format constraints / Context,
поиск неделимых запросов, многостадийный пайплайн и метрики качества.
Датасет: ai-forever/POLLUX (split test, пул ~1812 запросов).

## Структура
- PLAN.md — план работ и статус этапов
- SCHEMA.md — классы, правила разметки, критерии неделимости
- prompts/ — системные промпты стадий
- src/ — клиент LLM, пайплайн, валидатор, метрики
- scripts/ — подготовка данных, пилот, полный прогон
- data/, gold/, results/, report/ — данные, золотой набор, прогоны, отчёт

## Старт
1. `cp .env.example .env` и заполнить токены (в чат их не отправлять)
2. `pip install -r requirements.txt`
3. `python scripts/check_endpoints.py` — проверка GLM и OpenRouter
