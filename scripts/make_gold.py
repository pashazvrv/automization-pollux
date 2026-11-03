"""Выбирает N запросов из val для ручной разметки и собирает tools/annotator.html с данными внутри.
python scripts/make_gold.py [--n 50] [--seed 7]"""
import json, random, argparse, collections
ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=50); ap.add_argument("--seed", type=int, default=7)
ap.add_argument("--tag", default="")  # например 2 -> annotator_2.html, gold_items_2.jsonl
ap.add_argument("--exclude", nargs="*", default=[])  # jsonl с уже взятыми запросами
a = ap.parse_args()
val = [json.loads(l) for l in open("data/splits/val.jsonl", encoding="utf-8")]
random.seed(a.seed)
used = {json.loads(l)["id"] for f in a.exclude for l in open(f, encoding="utf-8")}
val = [r for r in val if r["id"] not in used]
by = collections.defaultdict(list)
for r in val: by[r["group"]].append(r)
share = {0: 0.16, 1: 0.56, 2: 0.28}
pick = []
for g, f in share.items():
    k = round(a.n * f); pick += random.sample(by[g], min(k, len(by[g])))
pick = pick[:a.n]; random.shuffle(pick)
items = [{"id": r["id"], "text": r["instruction"]} for r in pick]
with open(f"data/gold/gold_items{'_'+a.tag if a.tag else ''}.jsonl", "w", encoding="utf-8") as f:
    for r in pick: f.write(json.dumps({"id": r["id"], "instruction": r["instruction"], "group": r["group"]}, ensure_ascii=False) + "\n")
tpl = open("tools/annotator_template.html", encoding="utf-8").read()
sfx = f"_{a.tag}" if a.tag else ""
html = tpl.replace("__ITEMS__", json.dumps(items, ensure_ascii=False)).replace("__INIT__", "{}").replace("__RULES__", "").replace("__SK__", "gold_annotations_v1" + sfx).replace("__FILE__", f"gold_annotations{sfx}.json")
open(f"tools/annotator{sfx}.html", "w", encoding="utf-8").write(html)
print(f"готово:", len(items), "запросов -> tools/annotator (см. --tag)", dict(collections.Counter(r["group"] for r in pick)))
