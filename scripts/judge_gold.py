"""Прогон судьи (S4, опционально S5) на РУЧНОЙ разметке: эталон подаётся как «разбор».
python scripts/judge_gold.py [--judge gpt2] [--s5] [--workers 8] [--limit N] [--fresh]
Пишет results/gold/judge_gold.jsonl (можно прерывать и запускать снова — готовые id пропускаются).
Смысл: если судья «находит ошибки» в разметке человека, то либо в эталоне есть неточности,
либо судья придирается/понимает правила иначе. Сравнение с тем, как он судит разбор модели, — в make_judge_report.py."""
import argparse, json, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from pipeline import ask, judge_view, log
ap = argparse.ArgumentParser()
ap.add_argument("--judge", choices=["glm", "gpt", "gpt2"], default="gpt2")
ap.add_argument("--gold", default="data/gold/gold_all.json")
ap.add_argument("--out", default="results/gold/judge_gold.jsonl")
ap.add_argument("--s5", action="store_true", help="заодно прогнать S5 (неделимые)")
ap.add_argument("--include-fewshot", action="store_true", help="включить 11 примеров из промптов (часть S)")
ap.add_argument("--workers", type=int, default=8); ap.add_argument("--limit", type=int, default=None)
ap.add_argument("--fresh", action="store_true")
a = ap.parse_args()

def gold_to_parsed(g):
    P = {"tasks": [], "task_constraints": [], "format_constraints": [],
         "context": {"data": [], "text": [], "background": [], "role": []}, "indivisible": None}
    for x in g["annotations"]:
        t, c = x["text"], x["cls"]
        if not t.strip(): continue
        if c == "task": P["tasks"].append({"span": t, "norm": t})
        elif c == "tc": P["task_constraints"].append(t)
        elif c == "fc": P["format_constraints"].append(t)
        elif c == "bg": P["context"]["background"].append(t)
        elif c == "role": P["context"]["role"].append(t)
        elif c == "mat": P["context"]["text"].append(t)
    return P

def one(g):
    p = g["text"]; view = judge_view(gold_to_parsed(g))
    r4, _, e4 = ask(a.judge, "s4_judge.txt", f"Промпт:\n{p}\n\nРазбор:\n{view}")
    out = {"id": g["id"], "part": g.get("part"), "view": json.loads(view), "s4": r4 if r4 else {"error": e4}}
    if a.s5:
        r5, _, e5 = ask(a.judge, "s5_indivisible.txt", f"Промпт:\n{p}\n\nРазбор:\n{view}\n\nПодсказки разметчика о вплетённых требованиях:\n[]")
        out["s5"] = r5 if r5 else {"error": e5}
    return out

gold = [g for g in json.load(open(a.gold, encoding="utf-8")) if a.include_fewshot or g.get("part") != "S"]
if a.limit: gold = gold[:a.limit]
os.makedirs(os.path.dirname(a.out), exist_ok=True)
if a.fresh and os.path.exists(a.out): os.remove(a.out)
done = set()
if os.path.exists(a.out):
    for l in open(a.out, encoding="utf-8"):
        try: done.add(json.loads(l)["id"])
        except Exception: pass
todo = [g for g in gold if g["id"] not in done]
print(f"к проверке {len(gold)}, уже готово {len(done)}, в работе {len(todo)}; судья {a.judge}")
with open(a.out, "a", encoding="utf-8") as f, ThreadPoolExecutor(a.workers) as ex:
    futs = {ex.submit(one, g): g["id"] for g in todo}
    for n, fu in enumerate(as_completed(futs), 1):
        try: res = fu.result()
        except Exception as e: res = {"id": futs[fu], "s4": {"error": f"crash: {e}"}}
        f.write(json.dumps(res, ensure_ascii=False) + "\n"); f.flush()
        v = (res.get("s4") or {}).get("verdict", "?")
        print(f"{n}/{len(todo)} {res['id']} -> {v}", flush=True)
print("Готово:", a.out)
