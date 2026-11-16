"""Стабильность разбора между двумя прогонами одних и тех же запросов.
python scripts/stability.py results/v5_gpt_300.jsonl results/v5rep_100.jsonl
Сравнивает множества атомов (класс, norm) из export и решение о неделимости."""
import json, sys, os

def load(p):
    out = {}
    for l in open(p, encoding="utf-8"):
        try:
            d = json.loads(l); out[d["id"]] = d
        except Exception:
            pass
    return out

def atoms(rec):
    e = rec.get("export") or {}
    A = [("T", t) for t in e.get("tasks", [])]
    for k, c in (("task_constraints", "TC"), ("format_constraints", "FC")):
        for n in (e.get("constraints") or {}).get(k, []):
            A.append((c, n))
    return set(A)

def jaccard(a, b):
    return len(a & b) / len(a | b) if a or b else 1.0

A, B = load(sys.argv[1]), load(sys.argv[2])
ids = sorted(set(A) & set(B))
if not ids:
    sys.exit("нет общих id в файлах")
exact = jac = ind_agree = 0
unstable = []
for i in ids:
    a, b = atoms(A[i]), atoms(B[i])
    j = jaccard(a, b)
    jac += j
    ia, ib = bool((A[i].get("export") or {}).get("indivisible")), bool((B[i].get("export") or {}).get("indivisible"))
    ind_agree += ia == ib
    if j < 1.0 or ia != ib:
        unstable.append((i, round(j, 2), ia, ib))
    exact += j == 1.0
n = len(ids)
print(f"общих запросов: {n}")
print(f"идентичных наборов атомов: {exact}/{n} ({100 * exact / n:.0f}%)")
print(f"средний Jaccard по атомам: {jac / n:.3f}")
print(f"согласие по неделимости: {ind_agree}/{n} ({100 * ind_agree / n:.0f}%)")
print(f"нестабильных запросов: {len(unstable)} ({100 * len(unstable) / n:.0f}%)")
for u in unstable[:25]:
    print("  ", u[0], "jaccard", u[1], "| неделимость:", u[2], "->", u[3])
