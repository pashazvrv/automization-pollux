"""Сравнение разбора пайплайна с ручным эталоном (100 запросов: часть A — настройка, часть B — контроль).
python scripts/eval_gold.py --pred results/gold_gpt_v5.jsonl [--tag v5]
Пишет results/gold/eval_<tag>.xlsx и results/gold/eval_<tag>.json (для make_report.py).
Две метрики:
  строгая: тот же класс и пересечение (IoU) >= 0.5, края без знаков препинания;
  мягкая:  фрагмент модели считается верным, если >= 50% его лежит внутри эталонного фрагмента того же класса,
           эталонный найден, если >= 50% его покрыто фрагментами модели того же класса (дробление не штрафуется)."""
import argparse, json, os, sys, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from pipeline import expand, _find
ap = argparse.ArgumentParser()
ap.add_argument("--pred", required=True); ap.add_argument("--gold", default="data/gold/gold_all.json")
ap.add_argument("--merge", action="store_true", help="не различать огр. задачи и огр. формата (один класс «con»)")
ap.add_argument("--tag", default="run"); ap.add_argument("--iou", type=float, default=0.5)
a = ap.parse_args()
os.makedirs("results/gold", exist_ok=True)
CL = ["task", "con", "bg", "role", "mat"] if a.merge else ["task", "tc", "fc", "bg", "role", "mat"]
def mp(c): return "con" if (a.merge and c in ("tc", "fc")) else c
NAME = {"con": "все огр.", "task": "задача", "tc": "огр.задачи", "fc": "огр.формата", "bg": "фон", "role": "роль", "mat": "материал", "none": "—"}
PUNCT = " \t\r\n.,:;!?—–-«»\"'()"
gold = {g["id"]: g for g in json.load(open(a.gold, encoding="utf-8")) if g.get("part") != "S"}   # S = запросы, вошедшие в примеры промптов, в оценке не участвуют
pred = {}
for l in open(a.pred, encoding="utf-8"):
    r = json.loads(l); pred[r["id"]] = r

def trim(p, s0, s1):
    while s0 < s1 and p[s0] in PUNCT: s0 += 1
    while s1 > s0 and p[s1 - 1] in PUNCT: s1 -= 1
    return s0, s1

def locate(p, s):
    if not isinstance(s, str) or not s.strip(): return None
    if "……" in s: s = expand(p, s) or s
    return _find(p, s)

def pred_spans(r, p):
    pa = r.get("parsed") or {}; c = pa.get("context") or {}
    src = {"task": [(t.get("span") if isinstance(t, dict) else t) for t in pa.get("tasks", [])],
           "tc": pa.get("task_constraints", []), "fc": pa.get("format_constraints", []),
           "bg": c.get("background", []), "role": c.get("role", []), "mat": (c.get("data", []) or []) + (c.get("text", []) or [])}
    out = []; lost = 0
    for cl, lst in src.items():
        for s in lst:
            pos = locate(p, s)
            if pos:
                s0, s1 = trim(p, *pos)
                if s1 > s0: out.append((mp(cl), s0, s1))
            elif isinstance(s, str) and s.strip(): lost += 1
    return out, lost

def inter(a0, a1, b0, b1): return max(0, min(a1, b1) - max(a0, b0))
def iou(a0, a1, b0, b1):
    i = inter(a0, a1, b0, b1); u = (a1 - a0) + (b1 - b0) - i
    return i / u if u else 0
def covered(s0, s1, spans):   # доля [s0,s1), покрытая объединением spans
    pts = sorted((max(s0, x0), min(s1, x1)) for x0, x1 in spans if x1 > s0 and x0 < s1)
    tot = 0; cur = s0
    for x0, x1 in pts:
        x0 = max(x0, cur)
        if x1 > x0: tot += x1 - x0; cur = x1
    return tot / (s1 - s0) if s1 > s0 else 0

def blank(): return {c: collections.Counter() for c in CL}
M = {pt: {"strict": blank(), "soft": blank()} for pt in ("all", "A", "B")}
conf = {pt: collections.defaultdict(collections.Counter) for pt in ("all", "A", "B")}
ind = {pt: collections.Counter() for pt in ("all", "A", "B")}
cases = []; lost_total = 0; nres = 0
for gid, g in gold.items():
    r = pred.get(gid); pts = ("all", g.get("part", "A"))
    if not r or not r.get("parsed"): cases.append({"id": gid, "part": g.get("part"), "status": "нет результата"}); continue
    nres += 1; p = g["text"]; ps, lost = pred_spans(r, p); lost_total += lost
    gs = [(mp(x["cls"]), *trim(p, x["start"], x["end"])) for x in g["annotations"]]
    gs = [x for x in gs if x[2] > x[1]]
    # строгая
    used = set(); miss = []; extra = []
    for cl, s0, s1 in gs:
        best = None
        for j, (pc, q0, q1) in enumerate(ps):
            if j in used or pc != cl: continue
            v = iou(s0, s1, q0, q1)
            if v >= a.iou and (best is None or v > best[0]): best = (v, j)
        for pt in pts:
            M[pt]["strict"][cl]["gold"] += 1
            if best: M[pt]["strict"][cl]["tp_r"] += 1
        if best: used.add(best[1])
        # мягкая полнота
        cv = covered(s0, s1, [(q0, q1) for pc, q0, q1 in ps if pc == cl])
        for pt in pts:
            M[pt]["soft"][cl]["gold"] += 1
            if cv >= 0.5: M[pt]["soft"][cl]["tp_r"] += 1
        if not best: miss.append([cl, p[s0:s1][:120], "частично" if cv >= 0.5 else "нет"])
        # путаница
        cov = collections.Counter()
        for pc, q0, q1 in ps: cov[pc] += inter(s0, s1, q0, q1)
        top = cov.most_common(1); k = top[0][0] if top and top[0][1] >= 0.5 * (s1 - s0) else "none"
        for pt in pts: conf[pt][cl][k] += 1
    for j, (pc, q0, q1) in enumerate(ps):
        gin = [(x0, x1) for gc, x0, x1 in gs if gc == pc]
        sin = sum(inter(q0, q1, x0, x1) for x0, x1 in gin) / (q1 - q0)
        for pt in pts:
            M[pt]["strict"][pc]["pred"] += 1; M[pt]["soft"][pc]["pred"] += 1
            if j in used: M[pt]["strict"][pc]["tp_p"] += 1
            if sin >= 0.5: M[pt]["soft"][pc]["tp_p"] += 1
        if j not in used: extra.append([pc, p[q0:q1][:120], "внутри эталона" if sin >= 0.5 else "лишнее"])
    pi = bool((r["parsed"] or {}).get("indivisible")); gi = g["indivisible"]
    for pt in pts: ind[pt][("gold" if gi else "no") + "/" + ("pred" if pi else "no")] += 1
    cases.append({"id": gid, "part": g.get("part"), "text": p[:300], "gold_indiv": gi, "pred_indiv": pi, "miss": miss, "extra": extra,
                  "score": len(miss) + sum(1 for e in extra if e[2] == "лишнее")})

def prf(c):
    tpp, tpr, G, Pn = c["tp_p"], c["tp_r"], c["gold"], c["pred"]
    P = tpp / Pn if Pn else 0; R = tpr / G if G else 0
    return round(P, 3), round(R, 3), round(2 * P * R / (P + R), 3) if P + R else 0
summary = {"tag": a.tag, "n": len(gold), "with_result": nres, "lost_spans": lost_total, "iou": a.iou, "merge": a.merge, "classes": CL, "parts": {}}
for pt in ("all", "A", "B"):
    d = {"n": sum(1 for g in gold.values() if pt == "all" or g.get("part") == pt)}
    for kind in ("strict", "soft"):
        d[kind] = {c: dict(zip(("P", "R", "F1"), prf(M[pt][kind][c])), gold=M[pt][kind][c]["gold"], pred=M[pt][kind][c]["pred"]) for c in CL}
    d["conf"] = {c: [conf[pt][c][k] for k in CL + ["none"]] for c in CL}
    d["indiv"] = dict(ind[pt]); summary["parts"][pt] = d
summary["cases"] = sorted(cases, key=lambda c: -c.get("score", 0))
json.dump(summary, open(f"results/gold/eval_{a.tag}.json", "w", encoding="utf-8"), ensure_ascii=False)

print(f"\nЗапросов с результатом: {nres}/{len(gold)}; спанов модели не найдено в тексте: {lost_total}")
for pt, title in (("A", "Часть A (настройка, без запросов-примеров)"), ("B", "Часть B (контроль)"), ("all", "Все запросы без примеров")):
    d = summary["parts"][pt]; print(f"\n=== {title} ===")
    print(f"{'класс':<12}{'эт.':>5}{'мод.':>5} | {'строго P':>8}{'R':>6}{'F1':>6} | {'мягко P':>8}{'R':>6}{'F1':>6}")
    for c in CL:
        s, m = d["strict"][c], d["soft"][c]
        print(f"{NAME[c]:<12}{s['gold']:>5}{s['pred']:>5} | {s['P']:>8.2f}{s['R']:>6.2f}{s['F1']:>6.2f} | {m['P']:>8.2f}{m['R']:>6.2f}{m['F1']:>6.2f}")
    print("неделимые:", d["indiv"])
try:
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "сводка"
    ws.append(["часть", "метрика", "класс", "эталон", "модель", "P", "R", "F1"])
    for pt in ("A", "B", "all"):
        for kind in ("strict", "soft"):
            for c in CL:
                x = summary["parts"][pt][kind][c]; ws.append([pt, "строгая" if kind == "strict" else "мягкая", NAME[c], x["gold"], x["pred"], x["P"], x["R"], x["F1"]])
    w2 = wb.create_sheet("по запросам"); w2.append(["id", "часть", "пропущено моделью", "лишнее / иначе размечено у модели", "неделимый (эталон/модель)"])
    for c in summary["cases"]:
        if c.get("status"): w2.append([c["id"], c["part"], c["status"]]); continue
        w2.append([c["id"], c["part"], " | ".join(f"{NAME[k]}: {t} [{n}]" for k, t, n in c["miss"]), " | ".join(f"{NAME[k]}: {t} [{n}]" for k, t, n in c["extra"]),
                   f"{'да' if c['gold_indiv'] else 'нет'} / {'да' if c['pred_indiv'] else 'нет'}"])
    for col, w in zip("ABCDE", (10, 8, 70, 70, 22)): w2.column_dimensions[col].width = w
    path = f"results/gold/eval_{a.tag}.xlsx"
    try: wb.save(path)
    except PermissionError: path = path.replace(".xlsx", "_new.xlsx"); wb.save(path)
    print("\nТаблица:", path)
except Exception as e: print("xlsx не записан:", e)
print(f"Данные для отчёта: results/gold/eval_{a.tag}.json  (python scripts/make_report.py --tag {a.tag})")
