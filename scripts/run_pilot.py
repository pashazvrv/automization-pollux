"""python scripts/run_pilot.py --model gpt [--judge gpt2] [--limit 5] [--in data/splits/pilot.jsonl]"""
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import run
ap = argparse.ArgumentParser()
ap.add_argument("--model", choices=["glm", "gpt", "gpt2"], required=True)
ap.add_argument("--judge", choices=["glm", "gpt", "gpt2"], default=None)
ap.add_argument("--in", dest="inp", default="data/splits/pilot.jsonl")
ap.add_argument("--out", default=None)
ap.add_argument("--limit", type=int, default=None)
ap.add_argument("--offset", type=int, default=0)  # сдвиг выборки: другие примеры
ap.add_argument("--workers", type=int, default=8)
ap.add_argument("--fresh", action="store_true", help="удалить прежний файл результатов и начать заново")
a = ap.parse_args()
recs = [json.loads(l) for l in open(a.inp, encoding="utf-8")]
if a.limit:   # равномерно по файлу, чтобы в тест попали все группы и типы
    step = max(1, len(recs) // a.limit); recs = recs[a.offset % step::step][:a.limit]
out = a.out or f"results/pilot_{a.model}.jsonl"
if a.fresh and os.path.exists(out): os.remove(out)
run(recs, out, a.model, a.judge, a.workers)

from to_xlsx import convert
path, st = convert(out)
n = max(st["n"], 1)
print(f"\nГотово: {st['n']} запросов. Таблица: {path}")
print(f"  сбой разбора: {st['errors']} | спаны точные: {st['exact']}/{n} ({100*st['exact']//n}%) | "
      f"судья ok/fix: {st['judge_ok']}/{st['judge_fix']} | неделимых: {st['indivisible']}")
