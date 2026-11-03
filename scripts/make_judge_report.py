"""Инфографик «судья на ручной разметке».
python scripts/make_judge_report.py [--judge results/gold/judge_gold.jsonl] [--model results/gold/gold_gpt_v6.jsonl] [--out results/gold/report_judge.html]"""
import argparse, json, os, html, collections
ap = argparse.ArgumentParser()
ap.add_argument("--judge", default="results/gold/judge_gold.jsonl")
ap.add_argument("--base", default=None, help="прежний прогон судьи (v1) для сравнения")
ap.add_argument("--model", default="results/gold/gold_gpt_v6.jsonl")
ap.add_argument("--gold", default="data/gold/gold_all.json")
ap.add_argument("--out", default="results/gold/report_judge.html")
a = ap.parse_args()
G = {g["id"]: g for g in json.load(open(a.gold, encoding="utf-8")) if g.get("part") != "S"}
J = {}
for l in open(a.judge, encoding="utf-8"):
    r = json.loads(l); J[r["id"]] = r
M = {}
if os.path.exists(a.model):
    for l in open(a.model, encoding="utf-8"):
        r = json.loads(l); M[r["id"]] = (r.get("stages") or {}).get("s5")
TYPES = ["missing_task","extra_task","missing_constraint","extra_constraint","wrong_class","role","background","material","span"]
RU = {"missing_task":"пропущена задача","extra_task":"лишняя задача","missing_constraint":"пропущено ограничение",
      "extra_constraint":"выдумано ограничение","wrong_class":"неверный класс","role":"роль","background":"фон","material":"материал","span":"границы спана"}
def stats(src, ids):
    n = ok = fix = err = 0; mj = collections.Counter(); mn = collections.Counter(); nmaj = 0
    for i in ids:
        s = src.get(i)
        if not s or "error" in s or "verdict" not in s: err += 1; continue
        n += 1
        if s["verdict"] == "fix": fix += 1
        else: ok += 1
        for e in s.get("errors", []):
            (mj if e.get("severity") == "major" else mn)[e.get("type", "?")] += 1
    return dict(n=n, ok=ok, fix=fix, err=err, major=mj, minor=mn)
B0 = {}
if a.base and os.path.exists(a.base):
    for l in open(a.base, encoding="utf-8"):
        r = json.loads(l); B0[r["id"]] = r.get("s5") or r.get("s4")
ids = [i for i in J if i in G]
Jg = {i: J[i].get("s5") or J[i].get("s4") for i in ids}
parts = {"all": ids, "A": [i for i in ids if G[i]["part"] == "A"], "B": [i for i in ids if G[i]["part"] == "B"]}
SG = {k: stats(Jg, v) for k, v in parts.items()}
common = [i for i in ids if i in M]
SM = {k: stats(M, [i for i in v if i in M]) for k, v in parts.items()}
def pct(x, n): return f"{100*x/n:.0f}%" if n else "–"
def bars(title, S, cls):
    rows = ""; mx = max([S["major"][t] + S["minor"][t] for t in TYPES] + [1])
    for t in TYPES:
        m, n = S["major"][t], S["minor"][t]
        rows += (f'<div class="row"><span class="lb">{RU[t]}</span><span class="tr"><i class="mj" style="width:{100*m/mx:.1f}%"></i>'
                 f'<i class="mn" style="width:{100*n/mx:.1f}%"></i></span><b>{m}+{n}</b></div>')
    return f'<div class="card"><h3>{title}</h3>{rows}</div>'
def kpi(lbl, v, sub=""): return f'<div class="kpi"><div class="v">{v}</div><div class="l">{lbl}</div><div class="s">{sub}</div></div>'
A = SG["all"]; B = SM["all"]
S0 = stats(B0, ids) if B0 else None
def dl(cur, old): return f"было {old}" if old is not None else ""
k = "".join([kpi("судья проверил эталон", A["n"], f"из {len(G)}, без ответа: {A['err']}"),
             kpi("вердикт «ok» на разметке человека", pct(A["ok"], A["n"]), f"{A['ok']} из {A['n']}" + (f" · v1: {pct(S0['ok'], S0['n'])}" if S0 else "")),
             kpi("вердикт «fix» на разметке человека", pct(A["fix"], A["n"]), f"{A['fix']} из {A['n']}" + (f" · v1: {pct(S0['fix'], S0['n'])}" if S0 else "")),
             kpi("«fix» на разборе модели (v6)", pct(B["fix"], B["n"]), f"{B['fix']} из {B['n']}")])
ptab = "".join(f'<tr><td>{n}</td><td>{SG[k]["n"]}</td><td>{pct(SG[k]["fix"],SG[k]["n"])}</td><td>{SM[k]["n"]}</td><td>{pct(SM[k]["fix"],SM[k]["n"])}</td></tr>'
               for k, n in [("A","Часть A (настройка)"),("B","Часть B (контроль)"),("all","Всего")])
# Согласие: на одних и тех же запросах
both = collections.Counter()
for i in common:
    g, m = Jg.get(i), M.get(i)
    if not g or not m or "verdict" not in g or "verdict" not in m: continue
    both[(g["verdict"], m["verdict"])] += 1
cross = (f'<table><tr><th></th><th>модель: ok</th><th>модель: fix</th></tr>'
         f'<tr><th>человек: ok</th><td>{both[("ok","ok")]}</td><td>{both[("ok","fix")]}</td></tr>'
         f'<tr><th>человек: fix</th><td>{both[("fix","ok")]}</td><td>{both[("fix","fix")]}</td></tr></table>')
# список спорных
cases = ""
flag = [i for i in ids if (Jg[i] or {}).get("verdict") == "fix"]
for i in sorted(flag, key=lambda i: -sum(e.get("severity") == "major" for e in Jg[i]["errors"])):
    g = G[i]; errs = "".join(
        f'<li><span class="tag {e.get("severity")}">{e.get("severity")}</span> <b>{RU.get(e.get("type"), e.get("type"))}</b> <i>[{html.escape(str(e.get("rule","")))}]</i> '
        f'«{html.escape(str(e.get("span",""))[:120])}» — {html.escape(str(e.get("note","")))}</li>' for e in Jg[i]["errors"])
    cases += (f'<details><summary><b>{i}</b> · часть {g["part"]} · {html.escape(g["text"][:110].replace(chr(10)," "))}</summary>'
              f'<div class="pr">{html.escape(g["text"][:700])}</div><ul>{errs}</ul></details>')
doc = f"""<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Судья на ручной разметке</title><style>
:root{{--bg:#fafaf7;--fg:#1d1d1b;--mut:#6b6b66;--card:#fff;--bd:#e4e2da;--mj:#c2410c;--mn:#e0a96d;--ac:#2f6f5e}}
@media(prefers-color-scheme:dark){{:root{{--bg:#16171a;--fg:#ececea;--mut:#9a9a94;--card:#1f2024;--bd:#2f3036;--mj:#f08a5d;--mn:#a9783f;--ac:#6cc3a8}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:24px 16px 60px}}h1{{font-size:26px;margin:0 0 4px}}.sub{{color:var(--mut);margin-bottom:20px}}
.kp{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:18px}}
.kpi,.card{{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:14px 16px}}
.kpi .v{{font-size:34px;font-weight:700;color:var(--ac)}}.kpi .l{{font-size:13px}}.kpi .s{{font-size:12px;color:var(--mut)}}
.g2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin-bottom:18px}}h3{{margin:0 0 10px;font-size:16px}}
.row{{display:flex;align-items:center;gap:8px;margin:5px 0;font-size:13px}}.lb{{width:150px}}.tr{{flex:1;display:flex;background:var(--bd);height:12px;border-radius:6px;overflow:hidden}}
.mj{{background:var(--mj)}}.mn{{background:var(--mn)}}b{{min-width:36px;text-align:right}}
table{{border-collapse:collapse;width:100%}}th,td{{border-bottom:1px solid var(--bd);padding:6px 8px;text-align:center;font-size:13px}}
details{{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:8px 12px;margin:6px 0}}summary{{cursor:pointer;font-size:14px}}
.pr{{white-space:pre-wrap;color:var(--mut);font-size:13px;margin:8px 0;border-left:3px solid var(--bd);padding-left:10px}}
li{{margin:4px 0;font-size:13px}}.tag{{font-size:11px;padding:1px 6px;border-radius:8px;color:#fff}}.tag.major{{background:var(--mj)}}.tag.minor{{background:var(--mn)}}
.leg{{font-size:12px;color:var(--mut)}}.leg i{{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 10px}}</style><main>
<h1>Судья на ручной разметке</h1>
<div class="sub">Эталон (разметка человека) подан судье S4 как «разбор». Если судья находит ошибки — либо в разметке есть неточности, либо судья трактует правила иначе, чем мы.</div>
<div class="kp">{k}</div>
<div class="g2">{bars("Что судья нашёл в разметке человека" + (" (новый промпт)" if S0 else ""), SG["all"], "g")}{bars("То же, старый промпт (v1)", S0, "o") if S0 else ""}{bars("Что судья находит в разборе модели (v6, те же запросы)", SM["all"], "m")}</div>
<div class="leg"><i style="background:var(--mj)"></i>major<i style="background:var(--mn)"></i>minor (число ошибок типа)</div>
<div class="g2" style="margin-top:14px"><div class="card"><h3>Доля «fix» по частям</h3><table><tr><th></th><th>человек, n</th><th>fix</th><th>модель, n</th><th>fix</th></tr>{ptab}</table></div>
<div class="card"><h3>Согласие вердиктов на одних запросах</h3>{cross}</div></div>
<h3>Запросы, где судья нашёл major-ошибку в разметке человека ({len(flag)})</h3>{cases or "<div class=sub>нет</div>"}
</main></html>"""
open(a.out, "w", encoding="utf-8").write(doc)
print("Записано:", a.out, "| fix на эталоне:", f'{A["fix"]}/{A["n"]}', "| на модели:", f'{B["fix"]}/{B["n"]}')
