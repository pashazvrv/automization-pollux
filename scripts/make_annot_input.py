"""Собирает вход для разметчика v3: 300 промптов; черновик юнитов = старая разметка (100) или прогон GPT (200).
Запуск: python scripts/make_annot_input.py [results/v3_gpt_300.jsonl]
Результат: data/gold_v3/annot_input.json  (его открывает tools/annotator_v3.html)"""
import json, sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(ROOT, *a)
res_path = sys.argv[1] if len(sys.argv) > 1 else P("results", "v3_gpt_300.jsonl")
items = [json.loads(l) for l in open(P("data", "gold_v3", "items_300.jsonl"), encoding="utf-8")]
old = {g["id"]: g for g in json.load(open(P("data", "gold", "gold_all.json"), encoding="utf-8"))}
res = {}
if os.path.exists(res_path):
    for l in open(res_path, encoding="utf-8"):
        r = json.loads(l)
        if r.get("parsed"): res[r["id"]] = r["parsed"]["units"]

def from_old(g):
    anns = sorted(g["annotations"], key=lambda a: a["start"])
    tasks = [a for a in anns if a["cls"] == "task"]
    units, n = [], 0
    for a in anns:
        if a["cls"] == "task":
            n += 1
            units.append({"uid": f"t{n}", "cls": "task", "order": n, "frags": [a["text"]] if a["text"] else [], "norm": ""})
    for a in anns:
        if a["cls"] == "task": continue
        u = {"cls": a["cls"], "frags": [a["text"]]}
        if a["cls"] in ("tc", "fc"):
            u["attach"] = ["t1"] if len(tasks) == 1 else []   # при нескольких задачах привязку ставит человек
            if a["cls"] == "fc": u["check"] = None; u["review"] = "старый fc: проверь, что он программно проверяем, иначе смени на tc"
        units.append(u)
    if not tasks: units.insert(0, {"uid": "t1", "cls": "task", "order": 1, "frags": [], "norm": ""})
    return units

out = []
for it in items:
    if it["id"] in old:
        units, src = from_old(old[it["id"]]), "старая разметка"
        ind, note = old[it["id"]].get("indivisible", False), old[it["id"]].get("note", "")
    else:
        units, src, ind, note = res.get(it["id"], []), "черновик GPT", False, ""
    out.append({"id": it["id"], "split": it["split"], "text": it["instruction"], "units": units,
                "indivisible": ind, "note": note, "source": src, "done": False})
json.dump(out, open(P("data", "gold_v3", "annot_input.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(len(out), "промптов; из старой разметки:", sum(o["source"] == "старая разметка" for o in out),
      "; черновик GPT:", sum(o["source"] == "черновик GPT" and bool(o["units"]) for o in out))
