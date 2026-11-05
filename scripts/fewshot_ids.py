"""Какие запросы эталона попали в примеры промптов (few-shot) — их исключают из метрик.
Ищет в prompts/ любой кусок длиной 35 символов из первых 400 символов запроса.
python scripts/fewshot_ids.py  ->  data/gold_v3/fewshot_v4.json"""
import json, re, glob, os
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
norm = lambda s: re.sub(r"\s+", " ", s.replace("\\n", "\n")).strip()
P = {os.path.relpath(f, R): norm(open(f, encoding="utf-8").read()) for f in glob.glob(os.path.join(R, "prompts", "**", "*.txt"), recursive=True)
     if "eval" not in f}
out = {}
for l in open(os.path.join(R, "data", "gold_v3", "items_300.jsonl"), encoding="utf-8"):
    d = json.loads(l); t = norm(d["instruction"])[:400]
    wins = {t[i:i + 35] for i in range(0, max(1, len(t) - 35), 5)}
    fs = sorted(f for f, txt in P.items() if any(w in txt for w in wins))
    if fs: out[d["id"]] = fs
json.dump(out, open(os.path.join(R, "data", "gold_v3", "fewshot_v4.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(out), "запросов эталона используются в промптах:"); [print(" ", k, v) for k, v in out.items()]
