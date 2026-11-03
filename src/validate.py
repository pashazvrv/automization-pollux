"""Проверка разбора без модели (схема v4).
- дословность: frags задач, src атомов и контекст — точные подстроки промпта;
- покрытие символов промпта;
- полнота атомизации: каждое содержательное слово кандидата попало в src хотя бы одного его атома;
- форма записи: norm задачи — инфинитив, norm атома — с маленькой буквы; подозрение на недодробление."""
import re

STOP = {"если", "чтобы", "также", "который", "которая", "которые", "которых", "котором", "должен", "должна", "должны",
        "нужно", "нужен", "нужна", "будет", "будут", "меня", "тебе", "твой", "этот", "этого", "этой", "этих", "такие",
        "такой", "только", "можно", "очень", "более", "менее", "при", "этом", "свой", "свои", "своей", "учти", "важно"}

def _spans(t):
    return t.get("frags") or ([t["span"]] if t.get("span") else [])

def _atom_src(a):
    return a.get("src") or [] if isinstance(a, dict) else [a]

def collect(parsed):
    items = []
    for t in parsed.get("tasks", []):
        items += [("tasks", f) for f in _spans(t) if f]
    for k in ("task_constraints", "format_constraints"):
        for a in parsed.get(k, []):
            items += [(k, s) for s in _atom_src(a) if s]
    for k, v in parsed.get("context", {}).items():
        items += [("context." + k, s) for s in v if s]
    return items

def words(s):
    return {w for w in re.findall(r"[а-яёa-z0-9]+", s.lower()) if len(w) >= 4 and w not in STOP}

def validate(prompt, parsed):
    sp = []
    for k, s in collect(parsed):
        i = prompt.find(s)
        sp.append((k, s, i, i + len(s) if i >= 0 else -1))
    missing = [s for _, s, a, _ in sp if a < 0]
    found = sorted({(a, b) for _, _, a, b in sp if a >= 0})
    overlaps = sum(1 for x, y in zip(found, found[1:]) if y[0] < x[1])
    covered, last = 0, 0
    for a, b in found:
        a = max(a, last)
        if b > a: covered += b - a; last = b
    # полнота атомизации по кандидатам S2
    uncovered = []
    by_cand = {}
    for k in ("task_constraints", "format_constraints"):
        for a in parsed.get(k, []):
            if isinstance(a, dict): by_cand.setdefault("*", []).extend(a.get("src") or [])
    srcw = set().union(*[words(s) for s in by_cand.get("*", [])]) if by_cand.get("*") else set()
    moved = " ".join(parsed.get("context", {}).get("background", []) + parsed.get("context", {}).get("role", []))
    for c in parsed.get("_candidates", []):
        lost = sorted(words(c["span"]) - srcw - words(moved))
        if lost: uncovered.append({"candidate": c["span"], "words": lost})
    # форма записи
    lint = []
    for t in parsed.get("tasks", []):
        w = (t.get("norm") or "").split()
        if not w: lint.append(("task_norm_empty", t.get("id")))
        elif not re.search(r"(ть|ти|чь)(ся)?,?$", w[0]): lint.append(("task_not_infinitive", t["norm"]))
    for k in ("task_constraints", "format_constraints"):
        for a in parsed.get(k, []):
            n = a.get("norm", "") if isinstance(a, dict) else ""
            if not n: continue
            if n[:1].isupper() and not re.match(r"[A-Z]", n): lint.append(("atom_uppercase", n))
            if re.search(r", [а-яё]+(ми|ями|ами)? и |; ", n) and not n.startswith("шкала"): lint.append(("maybe_not_atomic", n))
    return {"all_exact": not missing, "missing": missing, "overlaps": overlaps,
            "coverage": round(covered / max(len(prompt), 1), 3), "n_atoms": len(sp),
            "uncovered": uncovered, "lint": lint,
            "implicit_task": any(not _spans(t) for t in parsed.get("tasks", []))}
