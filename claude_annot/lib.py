# -*- coding: utf-8 -*-
"""Инструментарий разметки: DSL -> формат разметчика v3. Все спаны дословные (проверяется)."""
import json, os, sys, unicodedata
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(R, "data", "gold_v3", "items_300.jsonl")
OUTDIR = os.path.dirname(os.path.abspath(__file__))

def items():
    out = []
    for l in open(SRC, encoding="utf-8"):
        d = json.loads(l); out.append({"id": d["id"], "text": d["instruction"], "split": d["split"]})
    return out

# ---- проверки формата (check) ----
def L(unit, op, v): return {"type": "length", "unit": unit, "op": op, "value": v}
def MK(v): return {"type": "markup", "value": v}
def ST(el, mode, v=None): return {"type": "structure", "element": el, "mode": mode, "value": v}
def LANG(v): return {"type": "language", "value": v}
def CASE(v): return {"type": "case", "value": v}
def KW(mode, words, count=None): return {"type": "keywords", "mode": mode, "words": list(words), "count": count}
def SE(where, v): return {"type": "startend", "where": where, "value": v}
def VAL(**kw): d = {"type": "value"}; d.update(kw); return d
def N(n): return ST("list", "count", n)
def DD(): return {"type": "dedup"}

ANN = {}
def a(id, t=(), role=(), bg=(), data=(), text=(), tc=(), fc=(), ind=None, note=""):
    assert id not in ANN, "дубль " + id
    ANN[id] = dict(t=list(t), role=list(role), bg=list(bg), data=list(data), text=list(text),
                   tc=list(tc), fc=list(fc), ind=ind, note=note)

def _nz(s):  # NBSP и пр. пробелы -> обычный пробел (длина сохраняется)
    return "".join(" " if unicodedata.category(c) == "Zs" else c for c in s)

def resolve(text, s, used):
    """s: подстрока или якорь 'начало~~конец'. Возвращает точную подстроку text; не пересекается с used."""
    tn = _nz(text)
    if "~~" in s:
        p, q = s.split("~~", 1); p = _nz(p); q = _nz(q)
        st = 0
        while True:
            i = tn.find(p, st)
            if i < 0: raise ValueError("нет начала якоря: " + p[:50])
            j = tn.find(q, i)
            if j < 0: raise ValueError("нет конца якоря: " + q[:50])
            e = j + len(q)
            if not any(i < b and e > a_ for a_, b in used): used.append((i, e)); return text[i:e]
            st = i + 1
    s2 = _nz(s); st = 0
    while True:
        i = tn.find(s2, st)
        if i < 0: raise ValueError("нет в тексте: " + s[:60])
        e = i + len(s2)
        if not any(i < b and e > a_ for a_, b in used): used.append((i, e)); return text[i:e]
        st = i + 1

def _att(at, n):
    if at is None: return [0] if n == 1 else ["*"]
    if at == "*": return ["*"]
    if isinstance(at, int): return [at]
    return list(at)

def build(strict=True):
    start = items(); out = []; errs = []
    for it in start:
        A = ANN.get(it["id"])
        if A is None:
            errs.append((it["id"], "не размечен")); continue
        txt = it["text"]; used = []
        try:
            r = lambda s: resolve(txt, s, used)
            tasks = []
            if A.get("norm"):
                ctx = {"role": [r(s) for s in A["role"]], "data": [r(s) for s in A["data"] + A["text"]],
                       "text": [], "background": [r(s) for s in A["bg"]]}
                n_ = len(A["nt"]); tcs, tca, fcs, fca, chk = [], [], [], [], []
                for e in A["ntc"]:
                    s_, at = (e, None) if isinstance(e, str) else (e[0], e[1])
                    tcs.append(s_); tca.append(_att(at, n_))
                for e in A["nfc"]:
                    fcs.append(e[0]); chk.append(e[1]); fca.append(_att(e[2] if len(e) > 2 else None, n_))
                for g in tca + fca:
                    for x in g:
                        if x != "*" and (not isinstance(x, int) or x >= n_): raise ValueError("привязка к несуществующей задаче %r" % (x,))
                ind = A["ind"]
                note = (ind + (": " if A["note"] else "") + A["note"]) if ind else A["note"]
                out.append({"id": it["id"], "split": it["split"], "text": txt, "source": "черновик Claude (норм.)",
                            "tasks": list(A["nt"]), "context": ctx,
                            "constraints": {"format_constraints": fcs, "task_constraints": tcs},
                            "attach": {"format_constraints": fca, "task_constraints": tca},
                            "checks": chk, "indivisible": bool(ind), "note": note, "done": False})
                continue
            for s in A["t"]:
                parts = [r(x) for x in s.split("|")]
                i0, e0 = used[-1]
                if txt[e0:e0 + 1] == ":" and not any(a_ <= e0 < b for a_, b in used):
                    used[-1] = (i0, e0 + 1); parts[-1] += ":"
                tasks.append(" ".join(parts))
            ctx = {"role": [r(s) for s in A["role"]], "data": [r(s) for s in A["data"] + A["text"]],
                   "text": [], "background": [r(s) for s in A["bg"]]}
            n = len(tasks); tcs, tca, fcs, fca, chk = [], [], [], [], []
            for e in A["tc"]:
                if isinstance(e, str): s, at = e, None
                else: s, at = e[0], e[1]
                tcs.append(r(s)); tca.append(_att(at, n))
            for e in A["fc"]:
                s, c = e[0], e[1]; at = e[2] if len(e) > 2 else None
                fcs.append(r(s)); fca.append(_att(at, n)); chk.append(c)
            for g in tca + fca:
                for x in g:
                    if x != "*" and (not isinstance(x, int) or x >= n): raise ValueError("привязка к несуществующей задаче %r" % (x,))
        except Exception as ex:
            errs.append((it["id"], str(ex))); continue
        ind = A["ind"]
        note = (ind + (": " if A["note"] else "") + A["note"]) if ind else A["note"]
        out.append({"id": it["id"], "split": it["split"], "text": txt, "source": "черновик Claude",
                    "tasks": tasks, "context": ctx,
                    "constraints": {"format_constraints": fcs, "task_constraints": tcs},
                    "attach": {"format_constraints": fca, "task_constraints": tca},
                    "checks": chk, "indivisible": bool(ind), "note": note, "done": False})
    return out, errs

def show(lo, hi, head=520, tail=380, full=1100):
    for k, it in enumerate(items()[lo:hi], lo):
        t = it["text"].replace("\n", "⏎")
        if len(t) > full: t = t[:head] + " ⟨…%d симв…⟩ " % (len(t) - head - tail) + t[-tail:]
        print("## %d %s [%s]  (%d симв)\n%s\n" % (k, it["id"], it["split"], len(it["text"]), t))


def p(id, t=None, tc_add=(), fc_add=(), tc_del=(), bg_add=(), role=None):
    """Правка уже зарегистрированной разметки (слой c*.py)."""
    A = ANN[id]
    if t is not None: A["t"] = list(t)
    for x in tc_del:
        A["tc"] = [e for e in A["tc"] if (e if isinstance(e, str) else e[0]) != x]
    A["tc"] = A["tc"] + list(tc_add); A["fc"] = A["fc"] + list(fc_add); A["bg"] = A["bg"] + list(bg_add)
    if role is not None: A["role"] = list(role)


def n(id, t=(), tc=(), fc=(), ind=None, note=None, bg=None, data=None, role=None):
    """Нормализованная запись: задачи и ограничения — согласованные формулировки (не дословные куски)."""
    A = ANN[id]; A["norm"] = True
    A["nt"] = list(t); A["ntc"] = list(tc); A["nfc"] = list(fc)
    if ind is not None: A["ind"] = ind or None
    if bg is not None: A["bg"] = list(bg)
    if data is not None: A["data"] = list(data); A["text"] = []
    if role is not None: A["role"] = list(role)
    if note is not None: A["note"] = note


def sp(id, old, new, kind="tc"):
    """Разбить одно нормализованное ограничение на несколько атомарных (привязка сохраняется)."""
    A = ANN[id]; key = "ntc" if kind == "tc" else "nfc"; L_ = A[key]
    for i, e in enumerate(L_):
        s = e if isinstance(e, str) else e[0]
        if s == old:
            at = None if isinstance(e, str) else e[1]
            L_[i:i + 1] = [x if at is None else (x, at) for x in new]
            return
    raise KeyError(id + ": нет ограничения " + old)
