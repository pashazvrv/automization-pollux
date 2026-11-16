"""Аудит LLM-матчера: выгружает предложенные им пары и несопоставленные атомы
для ручной проверки. Разметить колонку verdict (ok / bad_pair / missed_pair),
потом посчитать точность и полноту матчера.
python scripts/match_audit.py [TAG] [N] -> results/<TAG>_match_audit.csv"""
import json, os, sys, csv, random
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAG = sys.argv[1] if len(sys.argv) > 1 else "v4a"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 30
run = {json.loads(l)["id"]: json.loads(l) for l in open(os.path.join(R, "results", f"{TAG}_gpt_300.jsonl"), encoding="utf-8")}
gold = {g["id"]: g for g in json.load(open(os.path.join(R, "claude_annot", "claude_300.json"), encoding="utf-8"))}
mt = {json.loads(l)["id"]: json.loads(l) for l in open(os.path.join(R, "results", f"{TAG}_eval_match.jsonl"), encoding="utf-8")}
FEW = set(json.load(open(os.path.join(R, "data", "gold_v3", "fewshot_v4.json"), encoding="utf-8")))

def atoms_of(rec):
    A = [("T", t) for t in rec["tasks"]]
    for k, c in (("task_constraints", "TC"), ("format_constraints", "FC")):
        for n in rec["constraints"][k]:
            A.append((c, n))
    return A

ids = [i for i in mt if i not in FEW and i in gold and i in run and not gold[i]["indivisible"]
       and run[i].get("export") and not run[i]["export"]["indivisible"] and mt[i].get("after") and "error" not in mt[i]["after"]]
random.Random(42).shuffle(ids)
rows = []
for i in ids[:N]:
    G, M = atoms_of(gold[i]), atoms_of(run[i]["export"])
    pairs = mt[i]["after"].get("pairs", [])
    hg, hm = set(), set()
    for p in pairs:
        g = [x - 1 for x in p.get("g", []) if isinstance(x, int) and 0 < x <= len(G)]
        m = [x - 1 for x in p.get("m", []) if isinstance(x, int) and 0 < x <= len(M)]
        hg.update(x + 1 for x in g); hm.update(x + 1 for x in m)
        rows.append({"id": i, "kind": "pair", "rel": p.get("rel", ""),
                     "gold": " | ".join(f"[{G[x][0]}] {G[x][1]}" for x in g),
                     "model": " | ".join(f"[{M[x][0]}] {M[x][1]}" for x in m), "verdict": ""})
    for k in range(len(G)):
        if k + 1 not in hg:
            rows.append({"id": i, "kind": "gold_unmatched", "rel": "", "gold": f"[{G[k][0]}] {G[k][1]}", "model": "", "verdict": ""})
    for k in range(len(M)):
        if k + 1 not in hm:
            rows.append({"id": i, "kind": "model_unmatched", "rel": "", "gold": "", "model": f"[{M[k][0]}] {M[k][1]}", "verdict": ""})

out = os.path.join(R, "results", f"{TAG}_match_audit.csv")
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["id", "kind", "rel", "gold", "model", "verdict"])
    w.writeheader(); w.writerows(rows)
print(f"{len(rows)} строк из {min(N, len(ids))} запросов -> {out}")
print("Разметь verdict: ok / bad_pair (пара неверна) / missed_pair (для unmatched: пара должна была быть).")
