# Очередь экспериментов (v5, 16.11, одна модель — GLM)

## Как запускать — коротко (подробнее: FOR_DANIIL.md)

1. Один раз: скопировать `.env.example` в `.env`, вписать `LLM_KEY`, `LLM_MODEL`, `LLM_MODEL_JUDGE` (судью можно = основной модели).
2. Проверить доступ: `python scripts/check_endpoints.py` — все три строки должны быть OK.
3. Запустить всю очередь: **двойной клик по `run_experiments.bat`** (или `python scripts/run_queue.py --open`).
   Очередь сама идёт G0 → G2 → G4 → G5, после каждого шага строит HTML-дашборд
   и в конце открывает `results/dashboards/index.html`.
4. Если G0 не прошёл гейт — очередь сама остановится и напишет, что делать.

Полезные варианты:
- `python scripts/run_queue.py --only g0` — один шаг;
- `python scripts/run_queue.py --from g2` — продолжить с шага (всё кэшируется, прерванный запуск просто перезапусти той же командой);
- `python scripts/run_queue.py --only g0 --fresh` — перезапуск шага с чистого листа;
- `python scripts/run_queue.py --force` — идти дальше, даже если гейт G0 провален;
- прервать можно в любой момент (Ctrl+C) — ничего не потеряется.

Результаты: дашборды `results/dashboards/<тег>.html` (+ общий `index.html`),
сырые прогоны `results/*.jsonl`, таблицы для глаз `results/*.xlsx`, логи `results/logs/`.

## Что внутри очереди

Модель одна (GLM через гейтвей). Базовые точки — прошлые прогоны на GPT:
`results/v4a_metrics.json` (промпты без few-shot) и `results/v4b_metrics.json` (с few-shot),
пересчитаны на тех же 40 исключениях few-shot. Сравнение с ними — референс, а не конкурс:
модель и промпты меняются одновременно, факторы не разделяются.

Перед запуском: `.env` (`LLM_KEY`, `LLM_MODEL`; `LLM_MODEL_JUDGE` пусть = LLM_MODEL),
`pip install -r requirements.txt`, `python scripts/check_endpoints.py`.

Обозначение прогонов: `g0`, `g2`, `g4`, `g5` (TAG для eval_v4.py).

## G0. Дымовой прогон — 30 запросов, полный пайплайн (ОБЯЗАТЕЛЬНО первым)
Проверяет, что GLM следует формату v5 (JSON, точные спаны, якоря «……»).
```bash
python scripts/run_pilot.py --model gpt --judge gpt2 \
  --in data/gold_v3/items_300.jsonl --out results/g0_gpt_30.jsonl --limit 30 --workers 8
```
Критерий прохода: ошибки стадий < 5%; точные спаны > 95%; нет массовых сбоев формата
(смотреть вывод скрипта: «сбой разбора», «спаны точные») + глазами 3–5 разборов в xlsx.
Если критерий не выполнен — чинить промпты под GLM до следующих шагов.

## G2. Основной прогон — 300 эталонных, S1–S6
```bash
python scripts/run_pilot.py --model gpt --judge gpt2 \
  --in data/gold_v3/items_300.jsonl --out results/g2_gpt_300.jsonl --workers 8
TAG=g2 python scripts/eval_v4.py match
TAG=g2 python scripts/eval_v4.py judge-gold   # это же G3: судья на эталоне
TAG=g2 python scripts/eval_v4.py report
python scripts/regression_check.py v4a g2     # это же G1: регрессия правил v5
```
Смотрим (порядок важности):
1. регрессионный набор (G1): доля исправленных и доля сломанных случаев;
2. over_split (было 109 в v4a), лишние атомы по типам «Написать/изменить код»;
3. false-fix судьи на эталоне (G3, было 32%, цель <10%);
4. эффект фиксера: match_after − match_before (over_split, strict F1);
5. точность неделимости (было 0.37, цель >0.7); attach_acc (было 0.70);
6. lenient/strict F1 с ci95 — контроль, что не хуже v4a за пределами шума.

## G4. Стабильность — повтор 100 запросов
```bash
python scripts/run_pilot.py --model gpt --judge gpt2 \
  --in data/gold_v3/items_300.jsonl --out results/g4_gpt_100.jsonl \
  --limit 100 --workers 8
python scripts/stability.py results/g2_gpt_300.jsonl results/g4_gpt_100.jsonl
```
Даёт шумовой порог (Jaccard, доля идентичных, согласие по неделимости): разницы
между прогонами меньше этого порога не интерпретируем. Нестабильные запросы —
кандидаты в причину неделимости `unstable`.

## G5. Черновики held-out — 150 запросов из train-пула
```bash
python scripts/run_pilot.py --model gpt --judge gpt2 \
  --in data/splits/train.jsonl --out results/g5_heldout_150.jsonl --limit 150 --workers 8
```
Черновики идут на ручную проверку → честный тестовый набор; релизные метрики
считаем только на нём. Gold-300 после этого объявляется dev.

## Ручные аудиты (обязательны: матчер и судья теперь тоже GLM)
- Аудит матчера: `python scripts/match_audit.py g2 30` → разметить verdict в CSV
  (ok / bad_pair / missed_pair) → P/R матчера = систематический сдвиг метрик.
- Вычитка 10–15 разборов G0 глазами до больших прогонов.
- Два открытых вопроса из DECISIONS.md (no_task в эталоне; граница загадка/угадай) —
  решить до релизных метрик.

## Порядок
G0 → (чиним, если надо) → G2 (+G1, +G3) → G4 → аудит матчера → G5.
Если бюджет жмёт: G4 и G5 откладываются, G0/G2/G3 — нет.
Оркестратор `run_queue.py` выполняет G0→G2→G4→G5 сам, включая гейт G0,
матчинг/судью/отчёт/регрессию на G2 и дашборд после каждого шага;
ручной аудит матчера — отдельно, между G4 и G5 (очередь после G4 можно прервать).
