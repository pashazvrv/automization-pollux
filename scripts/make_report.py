"""Красивый отчёт по результатам сравнения с эталоном.
python scripts/make_report.py --tag v5 [--base old]   ->  results/gold/report_<tag>.html (открывается двойным кликом)"""
import argparse, json, os
ap = argparse.ArgumentParser(); ap.add_argument("--tag", required=True); ap.add_argument("--base", default="old"); ap.add_argument("--merged", default=None)
a = ap.parse_args()
cur = json.load(open(f"results/gold/eval_{a.tag}.json", encoding="utf-8"))
bp = f"results/gold/eval_{a.base}.json"
base = json.load(open(bp, encoding="utf-8")) if os.path.exists(bp) and a.base != a.tag else None
mp = f"results/gold/eval_{a.merged or a.tag + '_merged'}.json"
merged = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else None
html = TEMPLATE = open(os.path.join(os.path.dirname(__file__), "report_template.html"), encoding="utf-8").read()
html = html.replace("__CUR__", json.dumps(cur, ensure_ascii=False)).replace("__BASE__", json.dumps(base, ensure_ascii=False)).replace("__MERGED__", json.dumps(merged, ensure_ascii=False)).replace("__TAG__", a.tag)
out = f"results/gold/report_{a.tag}.html"
open(out, "w", encoding="utf-8").write(html); print("Отчёт:", out)
