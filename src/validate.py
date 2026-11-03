"""Проверка разбора без модели: спаны дословные, не пересекаются, покрытие символов."""

def collect(parsed):
    items = []
    for t in parsed.get("tasks", []):
        for f in (t.get("frags") or ([t["span"]] if t.get("span") else [])):
            if f: items.append(("tasks", f))
    for k in ("task_constraints", "format_constraints"):
        items += [(k, s) for s in parsed.get(k, []) if s]
    for k, v in parsed.get("context", {}).items():
        items += [("context." + k, s) for s in v if s]
    return items

def validate(prompt, parsed):
    sp = []
    for k, s in collect(parsed):
        i = prompt.find(s)
        sp.append((k, s, i, i + len(s) if i >= 0 else -1))
    missing = [s for _, s, a, _ in sp if a < 0]
    found = sorted((a, b) for _, _, a, b in sp if a >= 0)
    overlaps = sum(1 for x, y in zip(found, found[1:]) if y[0] < x[1])
    covered, last = 0, 0
    for a, b in found:
        a = max(a, last)
        if b > a: covered += b - a; last = b
    return {"all_exact": not missing, "missing": missing, "overlaps": overlaps,
            "coverage": round(covered / max(len(prompt), 1), 3),
            "n_atoms": len(sp), "implicit_task": any(not (t.get("frags") or t.get("span")) for t in parsed.get("tasks", []))}
