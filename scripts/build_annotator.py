"""Собирает tools/annotator_v3_data.html: разметчик со встроенными данными (annot_input.json -> формат с tasks/context/constraints)."""
import json, os
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def convert(it):
    U = it.get("units", [])
    tasks = [u for u in U if u["cls"] == "task"]
    uid2i = {u["uid"]: i for i, u in enumerate(tasks)}
    out = {"id": it["id"], "split": it["split"], "text": it["text"], "source": it.get("source", ""),
           "tasks": [(u.get("norm") or " ".join(u["frags"])).strip() for u in tasks],
           "context": {"role": [], "data": [], "text": [], "background": []},
           "constraints": {"format_constraints": [], "task_constraints": []},
           "attach": {"format_constraints": [], "task_constraints": []}, "checks": [],
           "indivisible": it.get("indivisible", False), "note": it.get("note", ""), "done": False}
    for u in U:
        c = u["cls"]; t = " ".join(u["frags"]).strip()
        if c in ("tc", "fc"):
            g = "task_constraints" if c == "tc" else "format_constraints"
            at = [uid2i[a] if a in uid2i else a for a in (u.get("attach") or [])]
            out["constraints"][g].append(t); out["attach"][g].append(at)
            if c == "fc": out["checks"].append(u.get("check"))
        elif c in ("role", "bg", "mat"):
            k = {"role": "role", "bg": "background", "mat": "data"}[c]
            out["context"][k].append(t)
    return out

if __name__ == "__main__":
    data = [convert(x) for x in json.load(open(os.path.join(R, "data", "gold_v3", "annot_input.json"), encoding="utf-8"))]
    json.dump(data, open(os.path.join(R, "data", "gold_v3", "annot_start.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    html = open(os.path.join(R, "tools", "annotator_v3.html"), encoding="utf-8").read()
    emb = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace("const EMBED=null;", "const EMBED=" + emb + ";", 1)
    open(os.path.join(R, "tools", "annotator_v3_data.html"), "w", encoding="utf-8").write(html)
    print("ok", len(data), "промптов")
