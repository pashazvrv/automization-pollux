"""Отбор 300 запросов для эталона v3 (все из POLLUX).
100 старых (часть A -> dev, часть B -> test) + 200 новых:
  ~140 из оставшейся валидационной части, добор до 7 на каждый тип задания, остальное случайно;
  ~60 прицельно из обучающей части: запросы с проверяемым форматом и с несколькими командами
  (эти id потом исключаются из обучения: data/gold_v3/exclude_from_train.json).
python scripts/select_300.py [--seed 42]"""
import argparse, json, random, re, collections
ap = argparse.ArgumentParser(); ap.add_argument("--seed", type=int, default=42)
ap.add_argument("--n_val", type=int, default=140); ap.add_argument("--n_fmt", type=int, default=30); ap.add_argument("--n_multi", type=int, default=30)
ap.add_argument("--per_type", type=int, default=7); ap.add_argument("--n_dev_new", type=int, default=50)
a = ap.parse_args(); rnd = random.Random(a.seed)
P = [json.loads(l) for l in open("data/splits/pool.jsonl", encoding="utf-8")]
byid = {p["id"]: p for p in P}
G = json.load(open("data/gold/gold_all.json", encoding="utf-8"))
old = {g["id"]: ("dev" if g["part"] in ("A", "S") else "test") for g in G}

FMT = re.compile(r"(\.md\b|markdown|\bjson\b|\bcsv\b|в виде таблиц|таблицей|в таблиц|списком|маркированн|нумерованн|не более \d+|не менее \d+|не больше \d+|до \d+ (слов|символ|предлож|строк)|\b\d+ (слов|предложени|абзац|строк|символ)|в (одн|дв|тр|четыр|пят)\w* (предлож|абзац|строк)|одним словом|на английском языке|ответь на английском|заглавными|без эмодзи|без смайл|в формате|по шкале)", re.I)
VERB = r"(напиши|составь|придумай|объясни|переведи|перескажи|выпиши|предложи|исправь|оцени|опиши|сравни|найди|дай|расскажи|проанализируй|приведи|укажи|определи|сделай|перепиши|добавь|посоветуй|порекомендуй|сформулируй|выдели)"
MULTI = re.compile(r"(?:^|[.!?\n]\s*|,\s*(?:а\s+)?(?:затем|потом|также|после этого)?\s*)" + VERB + r"\b", re.I)
def is_fmt(t): return bool(FMT.search(t))
def is_multi(t): return len(set(m.lower() for m in MULTI.findall(t))) >= 2

have = collections.Counter(byid[i]["task_type"] for i in old)
val_left = [p for p in P if p["split"] == "val" and p["id"] not in old]
rnd.shuffle(val_left)
new_val = []
for p in val_left:                                   # добор до per_type по каждому типу
    if have[p["task_type"]] < a.per_type: new_val.append(p); have[p["task_type"]] += 1
rest = [p for p in val_left if p not in new_val]
new_val += rest[:max(0, a.n_val - len(new_val))]
train = [p for p in P if p["split"] == "train"]; rnd.shuffle(train)
multi = [p for p in train if is_multi(p["instruction"])][:a.n_multi]
fmt = [p for p in train if is_fmt(p["instruction"]) and p not in multi][:a.n_fmt]
new = [(p, "val") for p in new_val] + [(p, "target_multi") for p in multi] + [(p, "target_fmt") for p in fmt]
rnd.shuffle(new)
items = []
for i, g in enumerate(G):
    p = byid[g["id"]]; items.append({"id": g["id"], "instruction": p["instruction"], "split": old[g["id"]], "origin": "old_" + g["part"], "task_type": p["task_type"]})
nd = 0
for p, src in new:
    s = "dev" if nd < a.n_dev_new else "test"; nd += 1
    items.append({"id": p["id"], "instruction": p["instruction"], "split": s, "origin": src, "task_type": p["task_type"]})
with open("data/gold_v3/items_300.jsonl", "w", encoding="utf-8") as f:
    for it in items: f.write(json.dumps(it, ensure_ascii=False) + "\n")
json.dump([p["id"] for p, s in new if s.startswith("target")], open("data/gold_v3/exclude_from_train.json", "w"), indent=0)
tt = collections.Counter(it["task_type"] for it in items)
print("всего", len(items), collections.Counter(it["split"] for it in items), collections.Counter(it["origin"] for it in items))
print("типов", len(tt), "минимум на тип", min(tt.values()))
print("с признаками формата", sum(is_fmt(it["instruction"]) for it in items), "с несколькими командами", sum(is_multi(it["instruction"]) for it in items))
