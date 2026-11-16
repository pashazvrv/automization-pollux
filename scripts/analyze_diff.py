# Разбор расхождений v4a: все extra/missed атомы + примеры эталона
import json, os, collections, sys
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAG = os.environ.get("TAG", "v4a")
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

extra, missed = [], []
for i, o in mt.items():
    if i in FEW: continue
    g, r = gold.get(i), run.get(i)
    if not g or not r or not r.get("export"): continue
    if g["indivisible"] or r["export"]["indivisible"]: continue
    res = o.get("after")
    if not res or "error" in res: continue
    G, M = atoms_of(g), atoms_of(r["export"])
    hg = {x for p in res.get("pairs", []) for x in p.get("g", []) if isinstance(x, int)}
    hm = {x for p in res.get("pairs", []) for x in p.get("m", []) if isinstance(x, int)}
    for k in range(len(G)):
        if k + 1 not in hg: missed.append((i, G[k][0], G[k][1]))
    for k in range(len(M)):
        if k + 1 not in hm: extra.append((i, M[k][0], M[k][1]))

print("=== MISSED (в эталоне есть, модель не выделила):", len(missed))
for i, c, n in missed: print(f"  {i} [{c}] {n}")
print()
print("=== EXTRA (у модели есть, в эталоне нет):", len(extra))
for i, c, n in extra: print(f"  {i} [{c}] {n}")

if "--gold" in sys.argv:
    ids = sys.argv[sys.argv.index("--gold") + 1:]
    for i in ids:
        g = gold[i]
        print("\n=== GOLD", i, "===")
        print(g["text"][:400])
        print(json.dumps({k: g[k] for k in ("tasks", "constraints", "context", "indivisible")}, ensure_ascii=False, indent=1)[:3000])
