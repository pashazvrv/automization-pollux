"""Оценка прогона v4 по эталону в согласованной форме и сбор метрик для дашборда.
python scripts/eval_v4.py match       — сопоставление атомов модели и эталона (LLM, кэш, можно прерывать)
python scripts/eval_v4.py judge-gold  — судья (S5) на эталоне: доля ложных тревог (кэш, можно прерывать)
python scripts/eval_v4.py report      — метрики -> results/v4_metrics.json
Эталон: claude_annot/claude_300.json (нормализованная разметка; ссылок на куски запроса в нём нет)."""
import json, os, sys, collections
from concurrent.futures import ThreadPoolExecutor
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(R, "src"))
from pipeline import ask

TAG = os.environ.get("TAG", "v4b")          # v4a — без примеров из эталона, v4b — с few-shot
RUN = os.path.join(R, "results", f"{TAG}_gpt_300.jsonl")
GOLD = os.path.join(R, "claude_annot", "claude_300.json")
MATCH = os.path.join(R, "results", f"{TAG}_eval_match.jsonl")
JGOLD = os.path.join(R, "results", f"{TAG}_judge_gold.jsonl")
OUT = os.path.join(R, "results", f"{TAG}_metrics.json")
FEW = os.path.join(R, "data", "gold_v3", "fewshot_v4.json")   # запросы из примеров промптов — в метрики не идут
EXCL = set(json.load(open(FEW, encoding="utf-8"))) if os.path.exists(FEW) else set()
MATCHER, JUDGE = "gpt2", "gpt2"

def load_jsonl(p):
    out = {}
    if os.path.exists(p):
        for l in open(p, encoding="utf-8"):
            try: d = json.loads(l); out[d["id"]] = d
            except Exception: pass
    return out

def atoms_of(rec):
    """[(класс, norm, attach)] из записи формата разметчика."""
    A = [("T", t, None) for t in rec["tasks"]]
    for k, c in (("task_constraints", "TC"), ("format_constraints", "FC")):
        for i, n in enumerate(rec["constraints"][k]):
            A.append((c, n, rec["attach"][k][i] if i < len(rec["attach"][k]) else ["*"]))
    return A

def model_before_fix(r):
    """Запись разметчика из разбора до фиксера (если фиксер что-то менял)."""
    from pipeline import export_record
    p = r["parsed"]; b = p.get("_before_fix")
    if not b: return None
    q = dict(p); q.update(b); q["indivisible"] = None
    return export_record(r["id"], r["export"]["text"], q)

def match_one(prompt, G, M):
    if not G or not M: return {"pairs": []}
    lst = lambda X, s: "\n".join(f"{s}{i + 1} ({c}) {n}" for i, (c, n, _) in enumerate(X))
    res, _, err = ask(MATCHER, "eval/match.txt", f"Запрос:\n{prompt[:3000]}\n\nЭталон:\n{lst(G, 'G')}\n\nМодель:\n{lst(M, 'M')}")
    return res if res else {"error": err}

def cmd_match():
    run = load_jsonl(RUN); gold = {g["id"]: g for g in json.load(open(GOLD, encoding="utf-8"))}
    done = load_jsonl(MATCH); todo = [i for i in gold if i in run and i not in done and run[i].get("export")]
    def job(i):
        r, g = run[i], gold[i]; G = atoms_of(g); M = atoms_of(r["export"])
        o = {"id": i, "after": match_one(g["text"], G, M)}
        mb = model_before_fix(r)
        if mb: o["before"] = match_one(g["text"], G, atoms_of(mb))
        return o
    with open(MATCH, "a", encoding="utf-8") as f, ThreadPoolExecutor(16) as ex:
        for n, o in enumerate(ex.map(job, todo), 1):
            f.write(json.dumps(o, ensure_ascii=False) + "\n"); f.flush()
            if n % 20 == 0: print(n, "/", len(todo), flush=True)

def gold_view(g):
    t = [{"id": f"t{i + 1}", "frags": [], "norm": n} for i, n in enumerate(g["tasks"])]
    def at(a): return [x if x == "*" else f"t{x + 1}" for x in a]
    tc = [{"norm": n, "src": [], "attach": at(g["attach"]["task_constraints"][i])} for i, n in enumerate(g["constraints"]["task_constraints"])]
    fc = [{"norm": n, "src": [], "attach": at(g["attach"]["format_constraints"][i]), "check": g["checks"][i] if i < len(g["checks"]) else None}
          for i, n in enumerate(g["constraints"]["format_constraints"])]
    c = g["context"]
    short = lambda x: x if len(x) < 300 else " ".join(x.split()[:5]) + "……" + " ".join(x.split()[-5:])
    return json.dumps({"tasks": t, "task_constraints": tc, "format_constraints": fc,
                       "context": {"data": [short(x) for x in c["data"]], "background": c["background"], "role": c["role"]}}, ensure_ascii=False)

def cmd_judge_gold():
    gold = [g for g in json.load(open(GOLD, encoding="utf-8")) if not g["indivisible"]]
    done = {k: v for k, v in load_jsonl(JGOLD).items() if "error" not in (v.get("s5") or {"error": 1})}
    todo = [g for g in gold if g["id"] not in done]
    if os.path.exists(JGOLD):   # убрать неудачные строки, их пересчитаем
        open(JGOLD, "w", encoding="utf-8").writelines(json.dumps(v, ensure_ascii=False) + "\n" for v in done.values())
    note = "\n\n(Разбор — ручной эталон: ссылок src на куски запроса в нём нет, это не ошибка; frags задач пусты по той же причине.)"
    def job(g):
        r, _, e = ask(JUDGE, "s5_judge.txt", f"Промпт:\n{g['text']}\n\nРазбор:\n{gold_view(g)}{note}")
        return {"id": g["id"], "s5": r if r else {"error": e}}
    with open(JGOLD, "a", encoding="utf-8") as f, ThreadPoolExecutor(16) as ex:
        for n, o in enumerate(ex.map(job, todo), 1):
            f.write(json.dumps(o, ensure_ascii=False) + "\n"); f.flush()
            if n % 20 == 0: print(n, "/", len(todo), flush=True)

def score(G, M, res):
    """Метрики одного запроса по выравниванию."""
    pairs = [p for p in (res or {}).get("pairs", []) if isinstance(p, dict)]
    usedG, usedM, s = set(), set(), collections.Counter()
    cls_conf = collections.Counter(); att = [0, 0]; chk = [0, 0]
    tmap = {}
    for p in pairs:
        g = [x - 1 for x in p.get("g", []) if isinstance(x, int) and 0 < x <= len(G) and x - 1 not in usedG]
        m = [x - 1 for x in p.get("m", []) if isinstance(x, int) and 0 < x <= len(M) and x - 1 not in usedM]
        if not g or not m or (len(g) > 1 and len(m) > 1): continue
        usedG.update(g); usedM.update(m); rel = p.get("rel", "equal")
        if len(g) == 1 and len(m) == 1:
            s["one2one_" + ("equal" if rel == "equal" else "partial")] += 1
            gc, mc = G[g[0]][0], M[m[0]][0]; cls_conf[(gc, mc)] += 1
            if gc == "T" and mc == "T": tmap[m[0]] = g[0]
        elif len(m) > 1: s["over_split"] += 1; s["over_split_atoms"] += len(m)
        else: s["under_split"] += 1; s["under_split_atoms"] += len(g)
    # привязка и проверка формата на парах 1:1 ограничений
    for p in pairs:
        g, m = p.get("g", []), p.get("m", [])
        if len(g) == 1 and len(m) == 1 and isinstance(g[0], int) and isinstance(m[0], int) and g[0] <= len(G) and m[0] <= len(M):
            gc, gn, ga = G[g[0] - 1]; mc, mn, ma = M[m[0] - 1]
            if gc != "T" and mc != "T" and ga is not None and ma is not None:
                gt = set(ga); mt = {("*" if x == "*" else tmap.get(x, -1)) for x in ma}
                att[1] += 1; att[0] += int(gt == mt or (gt == {"*"} and len([a for a in G if a[0] == "T"]) == 1 and mt == {0}) or (mt == {"*"} and len([a for a in G if a[0] == "T"]) == 1 and gt == {0}))
    s["G"] = len(G); s["M"] = len(M)
    for c in ("T", "TC", "FC"):
        s["G_" + c] = sum(1 for a in G if a[0] == c); s["M_" + c] = sum(1 for a in M if a[0] == c)
        s["G_" + c + "_hit"] = sum(1 for i in usedG if G[i][0] == c); s["M_" + c + "_hit"] = sum(1 for i in usedM if M[i][0] == c)
        s["G_" + c + "_strict"] = 0
    for p in pairs:
        g, m = p.get("g", []), p.get("m", [])
        if len(g) == 1 and len(m) == 1 and p.get("rel", "equal") == "equal" and isinstance(g[0], int) and 0 < g[0] <= len(G):
            s["G_" + G[g[0] - 1][0] + "_strict"] += 1
    s["G_hit"] = len(usedG); s["M_hit"] = len(usedM)
    return s, cls_conf, att

def prf(tp_m, m, tp_g, g):
    P = tp_m / m if m else None; Rr = tp_g / g if g else None
    F = 2 * P * Rr / (P + Rr) if P and Rr else (0.0 if (P is not None and Rr is not None) else None)
    return {"P": P, "R": Rr, "F1": F}

def cmd_report():
    run = {k: v for k, v in load_jsonl(RUN).items() if k not in EXCL}
    gold = {g["id"]: g for g in json.load(open(GOLD, encoding="utf-8")) if g["id"] not in EXCL}
    mt = {k: v for k, v in load_jsonl(MATCH).items() if k not in EXCL}
    jg = {k: v for k, v in load_jsonl(JGOLD).items() if k not in EXCL}
    items = {json.loads(l)["id"]: json.loads(l) for l in open(os.path.join(R, "data", "gold_v3", "items_300.jsonl"), encoding="utf-8")}
    M = {"tag": TAG, "n": len(run), "excluded_fewshot": len(EXCL)}
    # --- здоровье пайплайна
    st = collections.Counter(); lint = collections.Counter(); moves = collections.Counter(); s4 = collections.Counter()
    natoms = []; per_task_type = collections.defaultdict(lambda: collections.Counter())
    for r in run.values():
        v = r.get("validation") or {}; p = r.get("parsed") or {}
        st["stage_errors"] += bool(r.get("errors")); st["exact"] += bool(v.get("all_exact"))
        st["uncovered"] += bool(v.get("uncovered")); st["lint_any"] += bool(v.get("lint"))
        for k, _ in v.get("lint", []): lint[k] += 1
        for it in ((r.get("stages") or {}).get("s3") or {}).get("items", []):
            moves[it.get("move_to") or "атомы"] += 1
        for it in ((r.get("stages") or {}).get("s4") or {}).get("items", []): s4[it.get("class")] += 1
        e = r.get("export") or {}
        natoms.append(len(e.get("tasks", [])) + len(e.get("constraints", {}).get("task_constraints", [])) + len(e.get("constraints", {}).get("format_constraints", [])))
    M["pipeline"] = {"stage_errors": st["stage_errors"], "exact": st["exact"], "uncovered": st["uncovered"], "lint_any": st["lint_any"],
                     "lint": dict(lint), "s3_moves": dict(moves), "s4_classes": dict(s4),
                     "atoms_total": sum(natoms), "atoms_mean": round(sum(natoms) / max(len(natoms), 1), 2)}
    # --- судья на прогоне модели
    def judge_stats(src):
        c = collections.Counter(); mj = collections.Counter(); mn = collections.Counter(); rules = collections.Counter()
        for s in src:
            if not isinstance(s, dict) or "verdict" not in s: c["error"] += 1; continue
            c[s["verdict"]] += 1
            for e in s.get("errors", []):
                (mj if e.get("severity") == "major" else mn)[e.get("type", "?")] += 1
        return {"verdicts": dict(c), "major": dict(mj), "minor": dict(mn)}
    M["judge_run"] = judge_stats([(r.get("stages") or {}).get("s5") for r in run.values()])
    M["judge_gold"] = judge_stats([j.get("s5") for j in jg.values()]); M["judge_gold"]["n"] = len(jg)
    # --- фиксер и неделимость
    fx = collections.Counter(); reasons = collections.Counter()
    for r in run.values():
        s6 = (r.get("stages") or {}).get("s6") or {}
        if "error" in s6: fx["error"] += 1; continue
        fx["fixed"] += bool(s6.get("fixed") and s6.get("parse")); fx["applied"] += len(s6.get("applied") or []); fx["rejected"] += len(s6.get("rejected") or [])
        if s6.get("indivisible"): reasons[s6.get("reason") or "?"] += 1
    M["fixer"] = dict(fx); M["indivisible_model"] = dict(reasons)
    # --- неделимость: сравнение с эталоном
    conf = collections.Counter()
    for i, g in gold.items():
        if i not in run: continue
        conf[(bool(g["indivisible"]), bool((run[i].get("export") or {}).get("indivisible")))] += 1
    M["indivisible_confusion"] = {"gold_yes_model_yes": conf[(True, True)], "gold_yes_model_no": conf[(True, False)],
                                  "gold_no_model_yes": conf[(False, True)], "gold_no_model_no": conf[(False, False)]}
    # --- сопоставление атомов
    def agg(which):
        T = collections.Counter(); CC = collections.Counter(); A = [0, 0]; per_type = collections.defaultdict(collections.Counter); n = 0
        examples = []
        for i, o in mt.items():
            g = gold[i]; r = run[i]
            if g["indivisible"] or r["export"]["indivisible"]: continue
            if which == "before" and o.get("before"): res = o["before"]; e = model_before_fix(r)
            else: res = o.get("after"); e = r["export"]
            if not res or "error" in res: continue
            G = atoms_of(g); Mm = atoms_of(e); s, cc, att = score(G, Mm, res); n += 1
            T.update(s); CC.update(cc); A[0] += att[0]; A[1] += att[1]
            tt = items[i].get("task_type", "?"); per_type[tt].update({"G": s["G"], "M": s["M"], "G_hit": s["G_hit"], "M_hit": s["M_hit"]})
            if which == "after" and (s["G"] - s["G_hit"] or s["M"] - s["M_hit"] or s["over_split"] or s["under_split"]):
                pairs = res.get("pairs", [])
                hg = {x for p in pairs for x in p.get("g", []) if isinstance(x, int)}; hm = {x for p in pairs for x in p.get("m", []) if isinstance(x, int)}
                examples.append({"id": i, "prompt": g["text"][:220], "missed": [G[k][1] for k in range(len(G)) if k + 1 not in hg],
                                 "extra": [Mm[k][1] for k in range(len(Mm)) if k + 1 not in hm],
                                 "over_split": s["over_split"], "under_split": s["under_split"]})
        out = {"n": n, "lenient": prf(T["M_hit"], T["M"], T["G_hit"], T["G"]),
               "strict": prf(T["one2one_equal"], T["M"], T["one2one_equal"], T["G"]),
               "by_class": {c: prf(T["M_" + c + "_hit"], T["M_" + c], T["G_" + c + "_hit"], T["G_" + c]) for c in ("T", "TC", "FC")},
               "by_class_counts": {c: {"G": T["G_" + c], "M": T["M_" + c]} for c in ("T", "TC", "FC")},
               "pairs": {"equal": T["one2one_equal"], "partial": T["one2one_partial"], "over_split": T["over_split"], "under_split": T["under_split"]},
               "class_confusion": {f"{a}->{b}": v for (a, b), v in CC.items()},
               "attach_acc": A[0] / A[1] if A[1] else None,
               "per_task_type": {k: prf(v["M_hit"], v["M"], v["G_hit"], v["G"]) | {"n_atoms_gold": v["G"]} for k, v in per_type.items()}}
        if which == "after": out["examples"] = sorted(examples, key=lambda x: -(len(x["missed"]) + len(x["extra"])))[:25]
        return out
    M["match_after"] = agg("after"); M["match_before"] = agg("before")
    json.dump(M, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: M[k] for k in ("pipeline", "fixer", "indivisible_confusion")}, ensure_ascii=False))
    print("after", json.dumps({k: M["match_after"][k] for k in ("n", "lenient", "strict", "by_class", "pairs", "attach_acc")}, ensure_ascii=False))
    print("before", json.dumps({k: M["match_before"][k] for k in ("lenient", "strict", "pairs")}, ensure_ascii=False))
    print("judge_run", M["judge_run"]); print("judge_gold", M["judge_gold"])

if __name__ == "__main__":
    {"match": cmd_match, "judge-gold": cmd_judge_gold, "report": cmd_report}[sys.argv[1]]()
