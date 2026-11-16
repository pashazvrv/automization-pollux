"""Регрессионная проверка правок промптов: как изменились ошибки на тех же запросах
между двумя прогонами (по кэшам сопоставления с эталоном).
python scripts/regression_check.py <старый_TAG> <новый_TAG>
Пример: python scripts/regression_check.py v4a g2"""
import json, os, sys, collections
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD, NEW = sys.argv[1], sys.argv[2]

def load(tag, name):
    p = os.path.join(R, "results", f"{tag}_{name}")
    return {json.loads(l)["id"]: json.loads(l) for l in open(p, encoding="utf-8")} if os.path.exists(p) else {}

gold = {g["id"]: g for g in json.load(open(os.path.join(R, "claude_annot", "claude_300.json"), encoding="utf-8"))}
run_o, run_n = load(OLD, "gpt_300.jsonl"), load(NEW, "gpt_300.jsonl")
mt_o, mt_n = load(OLD, "eval_match.jsonl"), load(NEW, "eval_match.jsonl")
FEW = set(json.load(open(os.path.join(R, "data", "gold_v3", "fewshot_v4.json"), encoding="utf-8")))

def atoms_of(rec):
    A = [t for t in rec["tasks"]]
    for k in ("task_constraints", "format_constraints"):
        A += rec["constraints"][k]
    return A

def errors(i, run, mt):
    """(missed, extra, over, under) для запроса по сопоставлению after."""
    g, r, o = gold.get(i), run.get(i), mt.get(i)
    if not g or not r or not r.get("export") or not o: return None
    if g["indivisible"] or r["export"]["indivisible"]: return None
    res = o.get("after")
    if not res or "error" in res: return None
    G, M = atoms_of(g), atoms_of(r["export"])
    hg = {x for p in res.get("pairs", []) for x in p.get("g", []) if isinstance(x, int)}
    hm = {x for p in res.get("pairs", []) for x in p.get("m", []) if isinstance(x, int)}
    over = sum(1 for p in res.get("pairs", []) if len(p.get("m", [])) > 1)
    under = sum(1 for p in res.get("pairs", []) if len(p.get("g", [])) > 1)
    return (len(G) - len(hg & set(range(1, len(G) + 1))), len(M) - len(hm & set(range(1, len(M) + 1))), over, under)

fixed, broken, better, worse = [], [], [], []
same_clean = same_bad = 0
tot_o, tot_n = collections.Counter(), collections.Counter()
for i in sorted(set(mt_o) & set(mt_n)):
    eo, en = errors(i, run_o, mt_o), errors(i, run_n, mt_n)
    if eo is None or en is None: continue
    so, sn = sum(eo), sum(en)
    for k in range(4):
        tot_o[k] += eo[k]; tot_n[k] += en[k]
    if so and not sn: fixed.append(i)
    elif not so and sn: broken.append(i)
    elif sn < so: better.append((i, so, sn))
    elif sn > so: worse.append((i, so, sn))
    elif not so: same_clean += 1
    else: same_bad += 1

lbl = ["пропуски", "лишние", "over_split", "under_split"]
print(f"сравнение {OLD} -> {NEW}, запросов: {len(fixed) + len(broken) + len(better) + len(worse) + same_clean + same_bad}")
for k in range(4):
    print(f"  {lbl[k]:14} было {tot_o[k]:3}  стало {tot_n[k]:3}  ({tot_n[k] - tot_o[k]:+})")
print(f"\nисправлены полностью: {len(fixed)} {fixed}")
print(f"стало лучше (ошибок меньше): {len(better)} {better[:15]}")
print(f"стало хуже: {len(worse)} {worse[:15]}")
print(f"сломаны (были чисты): {len(broken)} {broken}")
print(f"чисты в обоих: {same_clean} | с ошибками в обоих: {same_bad}")
fx = [i for i in fixed if i in FEW]
print(f"\n(из исправленных {len(fx)} теперь в few-shot примерах: {fx})")
