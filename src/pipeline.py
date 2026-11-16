"""Многостадийная атомизация (v4).
S1 материал -> S2 задачи/роль/фон/кандидаты -> S3 атомизация кандидатов -> S4 классификация атомов
-> (S5 судья) -> (S6 фиксер + неделимость).
Задачи и ограничения хранятся в согласованной форме (norm); дословные frags/src — внутренняя ссылка
для проверки (нет выдумок, ничего не потеряно). Контекст (data, background, role) — дословно."""
import json, re, os, time, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from llm import glm, gpt, gpt2
from validate import validate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALL = {"glm": glm, "gpt": gpt, "gpt2": gpt2}
try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

def log(msg):
    line = time.strftime("%H:%M:%S") + " " + msg
    if tqdm: tqdm.write(line)
    else: print(line, flush=True)

VERBOSE = os.environ.get("PIPE_VERBOSE", "1") == "1"
MASK = "<Материал>"
ANCHOR = "……"

def prompt_file(name):
    return open(os.path.join(ROOT, "prompts", name), encoding="utf-8").read()

def fewshot_file(name):
    """Few-shot примеры к промпту (prompts/fewshot/<имя>); пустая строка, если файла нет."""
    p = os.path.join(ROOT, "prompts", "fewshot", name)
    return open(p, encoding="utf-8").read().strip() if os.path.exists(p) else ""

def assemble(system_file, user):
    """Собирает user-сообщение: few-shot примеры отделены рамками от рабочего входа,
    чтобы модель не принимала пример за разбираемый запрос."""
    few = fewshot_file(system_file)
    if not few:
        return user
    return ("Ниже — обучающие примеры правильных разборов. Это ПРИМЕРЫ, их разбирать не нужно.\n\n"
            "════ НАЧАЛО ПРИМЕРОВ ════\n\n" + few + "\n\n════ КОНЕЦ ПРИМЕРОВ ════\n\n"
            "Теперь выполни ту же работу для нового запроса (это НЕ пример):\n\n" + user)

def parse_json(txt):
    txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S).strip()
    a, b = txt.find("{"), txt.rfind("}")
    if a < 0 or b < a:
        raise ValueError("в ответе нет JSON; начало ответа: " + repr(txt[:150]))
    return json.loads(txt[a:b + 1])

def ask(model, system_file, user, max_tokens=8192, tries=3):
    system = prompt_file(system_file)
    user = assemble(system_file, user)
    last = None
    for n in range(1, tries + 1):
        t0 = time.time()
        try:
            raw = CALL[model]([{"role": "system", "content": system}, {"role": "user", "content": user}],
                              max_tokens=max_tokens)
            res = parse_json(raw)
            if VERBOSE: log(f"  {model} {system_file} ок за {time.time() - t0:.0f} с")
            return res, raw, None
        except Exception as e:
            last = str(e)[:400]
            log(f"  {model} {system_file} попытка {n}/{tries} ошибка за {time.time() - t0:.0f} с: {last[:200]}")
            if "length" in last or "пустой content" in last:
                max_tokens = min(max_tokens * 2, 32768)   # рассуждение съело лимит — даём больше
    return None, "", last

def _find(prompt, s, start=0):
    """Позиции (i, j) фрагмента s в prompt. Сначала точно, затем с допуском на пробелы/переносы строк
    (модели часто склеивают переносы в пробел). Возвращает исходный текст из prompt."""
    i = prompt.find(s, start)
    if i >= 0:
        return i, i + len(s)
    toks = s.split()
    if not toks:
        return None
    m = re.compile(r"\s+".join(re.escape(t) for t in toks)).search(prompt, start)
    return (m.start(), m.end()) if m else None

def expand(prompt, s):
    """Якорь «начало……конец» -> полный фрагмент; обычный спан приводится к точной подстроке prompt."""
    if not isinstance(s, str) or not s.strip():
        return None
    if ANCHOR in s:
        a, b = s.split(ANCHOR, 1)
        pa = _find(prompt, a.strip())
        if not pa:
            return None
        pb = _find(prompt, b.strip(), pa[1])
        return prompt[pa[0]:pb[1]] if pb else None
    pos = _find(prompt, s)
    return prompt[pos[0]:pos[1]] if pos else None

def short(t, limit=200):
    """Длинный фрагмент -> якорь «5 слов……5 слов» (для судьи, чтобы не раздувать вход)."""
    w = t.split()
    return t if len(t) <= limit or len(w) <= 12 else " ".join(w[:5]) + ANCHOR + " ".join(w[-5:])

def judge_view(parsed):
    """Разбор в схеме v4 для судьи и фиксера: задачи (frags, norm), атомы (norm, src, attach, check), контекст."""
    c = parsed["context"]
    v = {"tasks": [{"id": t["id"], "frags": [short(x) for x in t["frags"]], "norm": t.get("norm", "")} for t in parsed["tasks"]],
         "task_constraints": [{"norm": a["norm"], "src": a["src"], "attach": a["attach"]} for a in parsed["task_constraints"]],
         "format_constraints": [{"norm": a["norm"], "src": a["src"], "attach": a["attach"], "check": a.get("check")}
                                for a in parsed["format_constraints"]],
         "context": {"data": [short(x) for x in c["data"]], "background": c["background"], "role": c["role"]}}
    return json.dumps(v, ensure_ascii=False)

def as_text(x):
    """Модель иногда возвращает {'span': ...} вместо строки."""
    if isinstance(x, dict):
        x = x.get("span") or x.get("text") or ""
    return x if isinstance(x, str) else ""

def mask(prompt, spans):
    pos = sorted({(prompt.find(s), prompt.find(s) + len(s)) for s in spans if s and s in prompt})
    out, last = [], 0
    for a, b in pos:
        if a < last:
            continue
        out.append(prompt[last:a]); out.append(MASK); last = b
    out.append(prompt[last:])
    return "".join(out)

def clean_list(prompt, items):
    ok, bad = [], []
    for x in items or []:
        t = as_text(x)
        if not t.strip():
            continue
        e = expand(prompt, t)
        (ok if e else bad).append(e or t)
    return ok, bad

def make_units(parsed):
    """Плоский список юнитов (совместимость со скриптами отчётов и разметчика)."""
    U = [{"cls": "task", "uid": t["id"], "order": i + 1, "frags": t["frags"], "norm": t["norm"]} for i, t in enumerate(parsed["tasks"])]
    U += [{"cls": "tc", "frags": a["src"], "norm": a["norm"], "attach": a["attach"]} for a in parsed["task_constraints"]]
    U += [{"cls": "fc", "frags": a["src"], "norm": a["norm"], "attach": a["attach"], "check": a.get("check")} for a in parsed["format_constraints"]]
    c = parsed["context"]
    U += [{"cls": "role", "frags": [x]} for x in c["role"]] + [{"cls": "bg", "frags": [x]} for x in c["background"]]
    U += [{"cls": "mat", "frags": [x]} for x in c["data"]]
    return U

def _src(prompt, xs):
    return [expand(prompt, x) or x for x in (xs if isinstance(xs, list) else [xs]) if isinstance(x, str) and x.strip()]

def _attach(at):
    return at if isinstance(at, list) and at else ["*"]

def from_model_parse(prompt, P, old=None):
    """Нормализует разбор, который вернул фиксер (S6): спаны -> точные подстроки, якоря материала раскрываются."""
    c = P.get("context") or {}
    tasks = []
    for i, t in enumerate(P.get("tasks") or [], 1):
        if isinstance(t, dict):
            tasks.append({"id": t.get("id") or f"t{i}", "frags": _src(prompt, t.get("frags") or []), "norm": (t.get("norm") or "").strip()})
    def atoms(k, fmt):
        out = []
        for a in P.get(k) or []:
            if isinstance(a, dict) and (a.get("norm") or "").strip():
                x = {"norm": a["norm"].strip(), "src": _src(prompt, a.get("src") or []), "attach": _attach(a.get("attach"))}
                if fmt: x["check"] = a.get("check")
                out.append(x)
        return out
    data = [expand(prompt, as_text(x)) or as_text(x) for x in c.get("data") or [] if as_text(x).strip()]
    return {"tasks": tasks, "task_constraints": atoms("task_constraints", False), "format_constraints": atoms("format_constraints", True),
            "context": {"data": data or (old or {}).get("context", {}).get("data", []),
                        "background": _src(prompt, [as_text(x) for x in c.get("background") or []]),
                        "role": _src(prompt, [as_text(x) for x in c.get("role") or []])},
            "indivisible": None}

def export_record(rec_id, prompt, parsed):
    """Запись в формате разметчика: задачи и ограничения — только norm, привязка — индексы задач."""
    ids = {t["id"]: i for i, t in enumerate(parsed["tasks"])}
    att = lambda a: [x if x == "*" else ids.get(x, "*") for x in a]
    ind = parsed.get("indivisible") or {}
    return {"id": rec_id, "text": prompt, "source": "пайплайн v4",
            "tasks": [t["norm"] for t in parsed["tasks"]] if not ind else [],
            "context": {"role": parsed["context"]["role"], "data": parsed["context"]["data"], "text": [],
                        "background": parsed["context"]["background"]},
            "constraints": {"format_constraints": [a["norm"] for a in parsed["format_constraints"]],
                            "task_constraints": [a["norm"] for a in parsed["task_constraints"]]},
            "attach": {"format_constraints": [att(a["attach"]) for a in parsed["format_constraints"]],
                       "task_constraints": [att(a["attach"]) for a in parsed["task_constraints"]]},
            "checks": [a.get("check") for a in parsed["format_constraints"]],
            "indivisible": bool(ind), "note": ((ind.get("reason") or "") + ": " + (ind.get("note") or "")) if ind else "", "done": False}

def atomize(rec, model, judge_model=None):
    p = rec["instruction"]; out = {"id": rec["id"], "model": model, "stages": {}, "errors": []}
    # S1 — материал (весь в data; старое поле text тоже принимаем)
    r1, raw1, e1 = ask(model, "s1_material.txt", p)
    if r1 is None:
        out["errors"].append(f"s1: {e1}"); return out
    data, bad_d = clean_list(p, (r1.get("data") or []) + (r1.get("text") or []))
    out["stages"]["s1"] = r1
    if bad_d: out["errors"].append(f"s1 неточные спаны: {bad_d}")
    masked = mask(p, data)
    # S2 — задачи (frags + norm), роль, фон, кандидаты с привязкой
    r2, raw2, e2 = ask(model, "s2_extract.txt", masked)
    if r2 is None:
        out["errors"].append(f"s2: {e2}"); return out
    out["stages"]["s2"] = r2
    cands = []
    for c in r2.get("candidates") or []:
        sp = as_text(c); at = c.get("attach") if isinstance(c, dict) else None
        if sp.strip(): cands.append({"span": expand(p, sp) or sp, "attach": _attach(at)})
    role, bad_r = clean_list(p, r2.get("role")); bg, bad_b = clean_list(p, r2.get("background"))
    role += bad_r; bg += bad_b
    tasks = []
    for i, t in enumerate(r2.get("tasks", []), 1):
        if not isinstance(t, dict): continue
        fr = t.get("frags") if isinstance(t.get("frags"), list) else ([t["span"]] if t.get("span") else [])
        tasks.append({"id": t.get("id") or f"t{i}", "frags": _src(p, fr), "norm": (t.get("norm") or "").strip()})
    # S3 — атомизация кандидатов: атомарные условия в согласованной форме со ссылкой на src
    atoms, seen = [], set()
    if cands:
        tl = "\n".join(f"{t['id']} {t['norm']}" for t in tasks) or "(задач нет)"
        lst = "\n".join(f"{i + 1}. [{', '.join(c['attach'])}] {c['span']}" for i, c in enumerate(cands))
        r3, raw3, e3 = ask(model, "s3_atomize.txt", f"Промпт:\n{masked}\n\nЗадачи:\n{tl}\n\nКандидаты:\n{lst}")
        if r3 is None:
            out["errors"].append(f"s3: {e3}")
        else:
            out["stages"]["s3"] = r3
            for it in r3.get("items", []):
                try: k = int(it.get("id")) - 1; c = cands[k]
                except Exception: continue
                seen.add(k); mv = it.get("move_to")
                if mv == "background": bg.append(c["span"]); continue
                if mv == "role": role.append(c["span"]); continue
                if mv == "task":
                    tasks.append({"id": f"t{len(tasks) + 1}", "frags": [c["span"]], "norm": c["span"]}); continue
                for a in it.get("atoms") or []:
                    if isinstance(a, dict) and (a.get("norm") or "").strip():
                        atoms.append({"norm": a["norm"].strip(), "src": _src(p, a.get("src") or []), "attach": c["attach"], "cand": k})
        for k, c in enumerate(cands):   # кандидат, который S3 пропустил, идёт дальше как один атом
            if k not in seen:
                atoms.append({"norm": c["span"], "src": [c["span"]], "attach": c["attach"], "cand": k})
                out["errors"].append(f"s3 пропустил кандидата {k + 1}")
    # S4 — классификация атомов: format (с check) / task / not_constraint
    tcs, fcs, drop = [], [], []
    if atoms:
        lst = "\n".join(f"{i + 1}. {a['norm']}  (из: «{' / '.join(a['src'])}»)" for i, a in enumerate(atoms))
        r4, raw4, e4 = ask(model, "s4_classify.txt", f"Промпт:\n{masked}\n\nУсловия:\n{lst}")
        cls = {}
        if r4 is None:
            out["errors"].append(f"s4: {e4}")
        else:
            out["stages"]["s4"] = r4
            for it in r4.get("items", []):
                try: cls[int(it.get("id")) - 1] = it
                except Exception: pass
        for i, a in enumerate(atoms):
            it = cls.get(i, {"class": "task"}); a2 = {k: a[k] for k in ("norm", "src", "attach")}
            if it.get("class") == "format": a2["check"] = it.get("check"); fcs.append(a2)
            elif it.get("class") == "not_constraint": drop.append(a2)
            else: tcs.append(a2)
    parsed = {"tasks": tasks, "task_constraints": tcs, "format_constraints": fcs,
              "context": {"data": data, "background": bg, "role": role}, "indivisible": None,
              "_candidates": cands, "_atoms_by_cand": {}, "_entangled_hints": r2.get("entangled", []), "_dropped": drop}
    for a in atoms: parsed["_atoms_by_cand"].setdefault(a["cand"], []).append(a["norm"])
    parsed["units"] = make_units(parsed)
    out["parsed"] = parsed; out["validation"] = validate(p, parsed)
    # S5 судья / S6 фиксер + неделимость
    if judge_model:
        view = judge_view(parsed)
        r5, _, e5 = ask(judge_model, "s5_judge.txt", f"Промпт:\n{p}\n\nРазбор:\n{view}")
        out["stages"]["s5"] = r5 if r5 else {"error": e5}
        errs = (r5 or {}).get("errors") or []
        hints = json.dumps(parsed["_entangled_hints"], ensure_ascii=False)
        r6, _, e6 = ask(judge_model, "s6_fix.txt",
                        f"Промпт:\n{p}\n\nРазбор:\n{view}\n\nЗамечания судьи:\n{json.dumps(errs, ensure_ascii=False)}"
                        f"\n\nПодсказки разметчика о вплетённых требованиях:\n{hints}")
        out["stages"]["s6"] = r6 if r6 else {"error": e6}
        if r6:
            if r6.get("fixed") and isinstance(r6.get("parse"), dict):
                before = {k: parsed[k] for k in ("tasks", "task_constraints", "format_constraints", "context")}
                fixed = from_model_parse(p, r6["parse"], parsed)
                for k in ("tasks", "task_constraints", "format_constraints", "context"): parsed[k] = fixed[k]
                parsed["_before_fix"] = before; parsed["units"] = make_units(parsed)
                out["validation"] = validate(p, parsed)
            if r6.get("indivisible"):
                parsed["indivisible"] = {"reason": r6.get("reason"), "evidence": r6.get("evidence"), "note": r6.get("note")}
    out["export"] = export_record(rec["id"], p, parsed)
    return out

def run(records, out_path, model, judge_model=None, workers=8):
    done = set()
    if os.path.exists(out_path):
        for line in open(out_path, encoding="utf-8"):
            try: done.add(json.loads(line)["id"])
            except Exception: pass
    todo = [r for r in records if r["id"] not in done]
    print(f"всего {len(records)}, уже готово {len(done)}, в работе {len(todo)}")
    bar = tqdm(total=len(todo), desc=f"{model}", unit="зап") if tqdm else None
    ok = bad = 0
    with open(out_path, "a", encoding="utf-8") as f, ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(atomize, r, model, judge_model): r["id"] for r in todo}
        for n, fu in enumerate(as_completed(futs), 1):
            try: res = fu.result()
            except Exception as e: res = {"id": futs[fu], "model": model, "errors": [f"crash: {e}"]}
            f.write(json.dumps(res, ensure_ascii=False) + "\n"); f.flush()
            if res.get("parsed") and not res.get("errors"): ok += 1
            else: bad += 1
            if bar:
                bar.set_postfix(ok=ok, с_ошибками=bad); bar.update(1)
            else:
                print(f"{n}/{len(todo)} (ок {ok}, с ошибками {bad})", flush=True)
    if bar: bar.close()
