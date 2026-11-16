"""HTML-дашборд по прогону: читает results/<TAG>_metrics.json (если есть) и/или
сам файл прогона results/<TAG>_*.jsonl, строит results/dashboards/<TAG>.html.
python scripts/dashboard.py <TAG> [--extra "Заголовок=путь_к_текстовому_логу"]...
Также обновляет общий results/dashboards/index.html по всем тегам."""
import json, os, sys, html, datetime, collections

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(R, "results")
DASH = os.path.join(RES, "dashboards")
BASELINE = "v4a"   # референс для сравнения (прошлый прогон GPT без few-shot)

CSS = """
body{font-family:Segoe UI,Arial,sans-serif;margin:24px;background:#f6f7f9;color:#222}
h1{font-size:22px} h2{font-size:17px;margin:26px 0 8px;border-bottom:2px solid #dde1e6;padding-bottom:4px}
table{border-collapse:collapse;background:#fff;margin:6px 0}
th,td{border:1px solid #dde1e6;padding:5px 10px;font-size:13px;text-align:left}
th{background:#eef1f4}
.card{display:inline-block;background:#fff;border:1px solid #dde1e6;border-radius:8px;padding:10px 16px;margin:4px 8px 4px 0;vertical-align:top}
.card .v{font-size:22px;font-weight:600} .card .l{font-size:12px;color:#667}
.good{color:#1a7f37}.bad{color:#c0392b}.warn{color:#b26a00}.mut{color:#667}
pre{background:#fff;border:1px solid #dde1e6;padding:10px;font-size:12px;overflow:auto}
.bar{height:10px;background:#4f8ef7;border-radius:3px}
.small{font-size:12px;color:#667}
"""

def esc(x): return html.escape(str(x))

def pct(x, d=1): return f"{100*x:.{d}f}%" if isinstance(x, (int, float)) else "—"
def num(x, d=3): return f"{x:.{d}f}" if isinstance(x, (int, float)) else "—"

def delta(new, old, d=3, inverse=False):
    """HTML-дельта нового против референса; inverse=True — меньше = лучше."""
    if not isinstance(new, (int, float)) or not isinstance(old, (int, float)): return ""
    dd = new - old
    if abs(dd) < 1e-9: return '<span class="mut">=</span>'
    good = (dd < 0) if inverse else (dd > 0)
    return f'<span class="{"good" if good else "bad"}">{dd:+.{d}f}</span>'

def table(rows, header=None):
    out = ["<table>"]
    if header: out.append("<tr>" + "".join(f"<th>{esc(h)}</th>" for h in header) + "</tr>")
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    out.append("</table>")
    return "\n".join(out)

def find_run(tag):
    for n in os.listdir(RES):
        if n.startswith(tag + "_") and n.endswith(".jsonl") and "eval" not in n and "judge" not in n:
            return os.path.join(RES, n)
    return None

def load_jsonl(p):
    out = []
    if p and os.path.exists(p):
        for l in open(p, encoding="utf-8"):
            try: out.append(json.loads(l))
            except Exception: pass
    return out

def summarize_run(path):
    """Сводка по файлу прогона без матчинга (для g0/g4/g5 и как дополнение)."""
    recs = load_jsonl(path)
    s = {"n": len(recs), "errors": 0, "exact": 0, "uncovered": 0, "indivisible": 0,
         "judge": collections.Counter(), "fixer_fixed": 0, "atoms": []}
    lint = collections.Counter(); moves = collections.Counter(); s4 = collections.Counter()
    for r in recs:
        v = r.get("validation") or {}
        s["errors"] += bool(r.get("errors"))
        s["exact"] += bool(v.get("all_exact"))
        s["uncovered"] += bool(v.get("uncovered"))
        for k, _ in v.get("lint", []): lint[k] += 1
        st = r.get("stages") or {}
        s5 = st.get("s5") or {}
        s["judge"][s5.get("verdict", "error" if "error" in s5 else "?")] += 1
        s6 = st.get("s6") or {}
        s["fixer_fixed"] += bool(s6.get("fixed") and s6.get("parse"))
        for it in (st.get("s3") or {}).get("items", []): moves[it.get("move_to") or "атомы"] += 1
        for it in (st.get("s4") or {}).get("items", []): s4[it.get("class")] += 1
        e = r.get("export") or {}
        s["indivisible"] += bool(e.get("indivisible"))
        s["atoms"].append(len(e.get("tasks", [])) + len((e.get("constraints") or {}).get("task_constraints", []))
                          + len((e.get("constraints") or {}).get("format_constraints", [])))
    s["lint"], s["s3_moves"], s["s4_classes"] = dict(lint), dict(moves), dict(s4)
    s["judge"] = dict(s["judge"])
    return s

def prf_row(name, m, base=None):
    return [esc(name), num(m.get("P")), num(m.get("R")), num(m.get("F1")),
            (delta(m.get("F1"), (base or {}).get("F1")) if base else "")]

def render(tag, metrics, run_sum, extras, baseline):
    H = [f"<html><head><meta charset='utf-8'><title>{esc(tag)}</title><style>{CSS}</style></head><body>"]
    H.append(f"<h1>Прогон {esc(tag)} <span class='small'>{datetime.datetime.now():%Y-%m-%d %H:%M}</span></h1>")
    cards = []
    if metrics:
        p = metrics["pipeline"]
        cards += [(f"{metrics['n']}", "запросов в метриках"), (pct(p["exact"]/max(metrics["n"],1)), "точные спаны"),
                  (str(p["stage_errors"]), "ошибок стадий"), (str(p["atoms_mean"]), "атомов в среднем")]
        ma = metrics.get("match_after") or {}
        if ma.get("lenient"):
            cards += [(num(ma["lenient"]["F1"]), "lenient F1"), (num(ma["strict"]["F1"]), "strict F1"),
                      (pct(ma["attach_acc"]), "attach acc")]
        jg = metrics.get("judge_gold") or {}
        v = jg.get("verdicts") or {}
        if v:
            ff = v.get("fix", 0) / max(v.get("fix", 0) + v.get("ok", 0), 1)
            cards += [(pct(ff), "false-fix судьи на эталоне")]
    elif run_sum:
        cards += [(str(run_sum["n"]), "запросов"), (pct(run_sum["exact"]/max(run_sum["n"],1)), "точные спаны"),
                  (str(run_sum["errors"]), "ошибок стадий"), (str(run_sum["indivisible"]), "неделимых"),
                  (esc(run_sum["judge"]), "судья ok/fix")]
    H.append("".join(f"<div class='card'><div class='v'>{v}</div><div class='l'>{esc(l)}</div></div>" for v, l in cards))

    if metrics:
        b = baseline or {}
        p, bp = metrics["pipeline"], b.get("pipeline") or {}
        # --- здоровье пайплайна
        rows = [["ошибки стадий", p["stage_errors"], (bp or {}).get("stage_errors", "—"), delta(p["stage_errors"], (bp or {}).get("stage_errors"), 0, inverse=True)],
                ["точные спаны", p["exact"], (bp or {}).get("exact", "—"), delta(p["exact"], (bp or {}).get("exact"), 0)],
                ["непокрытые куски", p["uncovered"], (bp or {}).get("uncovered", "—"), delta(p["uncovered"], (bp or {}).get("uncovered"), 0, inverse=True)],
                ["lint (всего запросов)", p["lint_any"], (bp or {}).get("lint_any", "—"), ""]]
        H.append("<h2>Здоровье пайплайна</h2>" + table(rows, ["метрика", tag, BASELINE, "Δ"]))
        H.append("<span class='small'>lint: " + esc(json.dumps(p["lint"], ensure_ascii=False)) +
                 " | s3 переносы: " + esc(json.dumps(p["s3_moves"], ensure_ascii=False)) +
                 " | s4 классы: " + esc(json.dumps(p["s4_classes"], ensure_ascii=False)) + "</span>")
        # --- матчинг after vs before
        ma, mb = metrics.get("match_after") or {}, metrics.get("match_before") or {}
        ba = (b.get("match_after") or {})
        H.append("<h2>Сопоставление с эталоном (после фиксера)</h2>")
        rows = [prf_row("lenient", ma.get("lenient") or {}, ba.get("lenient")),
                prf_row("strict", ma.get("strict") or {}, ba.get("strict"))]
        for c in ("T", "TC", "FC"):
            rows.append(prf_row("класс " + c, (ma.get("by_class") or {}).get(c) or {}, (ba.get("by_class") or {}).get(c)))
        ci = ma.get("ci95") or {}
        rows.append(["ci95 lenient", esc(ci.get("lenient_F1", "—")), "", "", ""])
        rows.append(["ci95 strict", esc(ci.get("strict_F1", "—")), "", "", ""])
        H.append(table(rows, ["метрика", "P", "R", "F1", f"ΔF1 vs {BASELINE}"]))
        pa, pbase = ma.get("pairs") or {}, ba.get("pairs") or {}
        rows = [[esc(k), pa.get(k, 0), pbase.get(k, "—"), delta(pa.get(k), pbase.get(k), 0, inverse=k != "equal")]
                for k in ("equal", "partial", "over_split", "under_split")]
        rows.append(["attach_acc", pct(ma.get("attach_acc")), pct(ba.get("attach_acc")), delta(ma.get("attach_acc"), ba.get("attach_acc"))])
        H.append("<h2>Пары и привязка</h2>" + table(rows, ["тип", tag, BASELINE, "Δ"]))
        # --- фиксер
        H.append("<h2>Эффект фиксера (до → после)</h2>")
        fx = metrics.get("fixer") or {}
        rows = [["lenient F1", num((mb.get("lenient") or {}).get("F1")), num((ma.get("lenient") or {}).get("F1")), delta((ma.get("lenient") or {}).get("F1"), (mb.get("lenient") or {}).get("F1"))],
                ["strict F1", num((mb.get("strict") or {}).get("F1")), num((ma.get("strict") or {}).get("F1")), delta((ma.get("strict") or {}).get("F1"), (mb.get("strict") or {}).get("F1"))],
                ["over_split", (mb.get("pairs") or {}).get("over_split", "—"), pa.get("over_split", "—"), delta(pa.get("over_split"), (mb.get("pairs") or {}).get("over_split"), 0, inverse=True)],
                ["under_split", (mb.get("pairs") or {}).get("under_split", "—"), pa.get("under_split", "—"), delta(pa.get("under_split"), (mb.get("pairs") or {}).get("under_split"), 0, inverse=True)]]
        H.append(table(rows, ["метрика", "до", "после", "Δ"]))
        H.append("<span class='small'>фиксер: " + esc(json.dumps(fx, ensure_ascii=False)) + "</span>")
        # --- судья
        H.append("<h2>Судья</h2>")
        jr, jg = metrics.get("judge_run") or {}, metrics.get("judge_gold") or {}
        bjg = (b.get("judge_gold") or {})
        v, vb = jg.get("verdicts") or {}, bjg.get("verdicts") or {}
        ff = v.get("fix", 0) / max(v.get("fix", 0) + v.get("ok", 0), 1) if v else None
        ffb = vb.get("fix", 0) / max(vb.get("fix", 0) + vb.get("ok", 0), 1) if vb else None
        rows = [["на прогоне", esc(jr.get("verdicts")), "", ""],
                ["на эталоне (ложные тревоги)", esc(v), "", ""],
                ["false-fix rate (цель <10%)", pct(ff), pct(ffb), delta(ff, ffb, 3, inverse=True)]]
        H.append(table(rows, ["что", tag, BASELINE, "Δ"]))
        if jg.get("major"): H.append("<span class='small'>major на эталоне: " + esc(json.dumps(jg["major"], ensure_ascii=False)) + "</span>")
        # --- неделимость
        H.append("<h2>Неделимость</h2>")
        ic, bic = metrics.get("indivisible_confusion") or {}, b.get("indivisible_confusion") or {}
        def pr(c):
            tp, fp, fn = c.get("gold_yes_model_yes", 0), c.get("gold_no_model_yes", 0), c.get("gold_yes_model_no", 0)
            return (tp / (tp + fp) if tp + fp else None, tp / (tp + fn) if tp + fn else None)
        pr1, rc1 = pr(ic); pr0, rc0 = pr(bic) if bic else (None, None)
        rows = [["precision (цель >0.7)", num(pr1, 2), num(pr0, 2), delta(pr1, pr0, 2)],
                ["recall", num(rc1, 2), num(rc0, 2), delta(rc1, rc0, 2)]]
        rows.append(["confusion (gold×model)", esc(ic), "", ""])
        H.append(table(rows, ["метрика", tag, BASELINE, "Δ"]))
        if metrics.get("indivisible_model"):
            H.append("<span class='small'>причины модели: " + esc(json.dumps(metrics["indivisible_model"], ensure_ascii=False)) + "</span>")
        # --- по типам задач
        ptt = ma.get("per_task_type") or {}
        if ptt:
            rows = [[esc(k), str(v.get("n_atoms_gold", "")), num(v.get("P")), num(v.get("R")), num(v.get("F1"))]
                    for k, v in sorted(ptt.items(), key=lambda x: (x[1].get("F1") or 0))]
            H.append("<h2>По типам задач (худшие сверху)</h2>" + table(rows, ["тип", "атомов эталона", "P", "R", "F1"]))
        # --- примеры ошибок
        ex = ma.get("examples") or []
        if ex:
            rows = []
            for e in ex[:15]:
                rows.append([esc(e["id"]), esc(e["prompt"][:120]),
                             "<span class='bad'>" + esc("; ".join(e["missed"])[:200]) + "</span>",
                             "<span class='warn'>" + esc("; ".join(e["extra"])[:200]) + "</span>",
                             str(e["over_split"]), str(e["under_split"])])
            H.append("<h2>Худшие запросы (топ-15)</h2>" + table(rows, ["id", "запрос", "пропущено", "лишнее", "over", "under"]))
    elif run_sum:
        H.append("<h2>Сводка прогона (без матчинга с эталоном)</h2>")
        n = max(run_sum["n"], 1)
        rows = [["запросов", run_sum["n"]], ["ошибки стадий", f"{run_sum['errors']} ({pct(run_sum['errors']/n)})"],
                ["точные спаны", f"{run_sum['exact']} ({pct(run_sum['exact']/n)})"],
                ["непокрытые куски", run_sum["uncovered"]], ["неделимых", run_sum["indivisible"]],
                ["судья", esc(run_sum["judge"])], ["фиксер что-то менял", run_sum["fixer_fixed"]],
                ["атомов в среднем", round(sum(run_sum["atoms"])/n, 2)]]
        H.append(table(rows, ["метрика", "значение"]))
        H.append("<span class='small'>lint: " + esc(json.dumps(run_sum["lint"], ensure_ascii=False)) +
                 " | s3 переносы: " + esc(json.dumps(run_sum["s3_moves"], ensure_ascii=False)) +
                 " | s4 классы: " + esc(json.dumps(run_sum["s4_classes"], ensure_ascii=False)) + "</span>")

    for title, text in extras:
        H.append(f"<h2>{esc(title)}</h2><pre>{esc(text)}</pre>")
    H.append("</body></html>")
    return "\n".join(H)

def build(tag, extras=None):
    os.makedirs(DASH, exist_ok=True)
    mp = os.path.join(RES, f"{tag}_metrics.json")
    metrics = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else None
    bp = os.path.join(RES, f"{BASELINE}_metrics.json")
    baseline = json.load(open(bp, encoding="utf-8")) if tag != BASELINE and os.path.exists(bp) else None
    run_path = find_run(tag)
    run_sum = summarize_run(run_path) if run_path else None
    page = render(tag, metrics, run_sum, extras or [], baseline)
    out = os.path.join(DASH, f"{tag}.html")
    open(out, "w", encoding="utf-8").write(page)
    print("дашборд:", out)
    return out

def rebuild_index():
    """Общий index.html со ссылками и ключевыми числами всех тегов."""
    tags = sorted(f[:-5] for f in os.listdir(DASH) if f.endswith(".html") and f != "index.html")
    rows = []
    for t in tags:
        mp = os.path.join(RES, f"{t}_metrics.json")
        cells = [f'<a href="{esc(t)}.html">{esc(t)}</a>']
        if os.path.exists(mp):
            m = json.load(open(mp, encoding="utf-8"))
            ma = m.get("match_after") or {}
            v = (m.get("judge_gold") or {}).get("verdicts") or {}
            ff = v.get("fix", 0) / max(v.get("fix", 0) + v.get("ok", 0), 1) if v else None
            cells += [str(m.get("n", "")), num((ma.get("lenient") or {}).get("F1")), num((ma.get("strict") or {}).get("F1")),
                      str((ma.get("pairs") or {}).get("over_split", "")), pct(ma.get("attach_acc")), pct(ff)]
        else:
            s = summarize_run(find_run(t)) if find_run(t) else None
            cells += ([str(s["n"]), "—", "—", "—", "—", "—"] if s else ["?"] * 6)
        rows.append(cells)
    page = (f"<html><head><meta charset='utf-8'><title>эксперименты</title><style>{CSS}</style></head><body>"
            f"<h1>Эксперименты atomization-pollux</h1>"
            + table(rows, ["тег", "n", "lenient F1", "strict F1", "over_split", "attach", "false-fix gold"])
            + "</body></html>")
    open(os.path.join(DASH, "index.html"), "w", encoding="utf-8").write(page)

if __name__ == "__main__":
    tag = sys.argv[1]
    extras = []
    for a in sys.argv[2:]:
        if a.startswith("--extra="):
            title, _, path = a[len("--extra="):].partition("=")
            text = open(path, encoding="utf-8").read() if os.path.exists(path) else "(лог не найден)"
            extras.append((title, text))
    build(tag, extras)
    rebuild_index()
