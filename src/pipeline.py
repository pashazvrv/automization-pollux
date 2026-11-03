"""Многостадийная атомизация. S1 материал -> S2 разбор -> S3 классификация -> (S4 судья) -> (S5 неделимые)."""
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

def parse_json(txt):
    txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S).strip()
    a, b = txt.find("{"), txt.rfind("}")
    if a < 0 or b < a:
        raise ValueError("в ответе нет JSON; начало ответа: " + repr(txt[:150]))
    return json.loads(txt[a:b + 1])

def ask(model, system_file, user, max_tokens=8192, tries=3):
    system = prompt_file(system_file)
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
    """Разбор в схеме v3 для судьи: задачи с frags, ограничения с attach и check."""
    U = parsed["units"]; c = parsed["context"]
    v = {"tasks": [{"id": u["uid"], "frags": [short(x) for x in u["frags"]], "norm": u.get("norm", "")} for u in U if u["cls"] == "task"],
         "task_constraints": [{"span": u["frags"][0], "attach": u.get("attach")} for u in U if u["cls"] == "tc"],
         "format_constraints": [{"span": u["frags"][0], "attach": u.get("attach"), "check": u.get("check")} for u in U if u["cls"] == "fc"],
         "context": {"data": [short(x) for x in c["data"]], "text": [short(x) for x in c["text"]],
                     "background": c["background"], "role": c["role"]}}
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

def atomize(rec, model, judge_model=None):
    p = rec["instruction"]; out = {"id": rec["id"], "model": model, "stages": {}, "errors": []}
    # S1
    r1, raw1, e1 = ask(model, "s1_material.txt", p)
    if r1 is None:
        out["errors"].append(f"s1: {e1}"); return out
    data, bad_d = clean_list(p, r1.get("data")); text, bad_t = clean_list(p, r1.get("text"))
    out["stages"]["s1"] = r1
    if bad_d or bad_t: out["errors"].append(f"s1 неточные спаны: {bad_d + bad_t}")
    masked = mask(p, data + text)
    # S2
    r2, raw2, e2 = ask(model, "s2_extract.txt", masked)
    if r2 is None:
        out["errors"].append(f"s2: {e2}"); return out
    out["stages"]["s2"] = r2
    # S2 v3: задачи с frags, кандидаты с attach
    cand_objs = []
    for c in r2.get("candidates") or []:
        sp = as_text(c); at = c.get("attach") if isinstance(c, dict) else None
        e = expand(p, sp) if sp.strip() else None
        if sp.strip(): cand_objs.append({"span": e or sp, "attach": at if isinstance(at, list) and at else ["*"]})
    cands = [c["span"] for c in cand_objs]
    role, bad_r = clean_list(p, r2.get("role")); bg, bad_b = clean_list(p, r2.get("background"))
    tasks = []
    for i, t in enumerate(r2.get("tasks", []), 1):
        if not isinstance(t, dict): continue
        fr = t.get("frags") if isinstance(t.get("frags"), list) else ([t["span"]] if t.get("span") else [])
        fr = [expand(p, f) or f for f in fr if isinstance(f, str) and f.strip()]
        tasks.append({"id": t.get("id") or f"t{i}", "frags": fr, "span": fr[0] if fr else "", "norm": t.get("norm", "")})
    # S3
    fmt, tsk, drop, units_c = [], [], [], []
    if cands:
        lst = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(cands))
        r3, raw3, e3 = ask(model, "s3_classify.txt", f"Промпт:\n{masked}\n\nКандидаты:\n{lst}")
        if r3 is None:
            out["errors"].append(f"s3: {e3}")
        else:
            out["stages"]["s3"] = r3
            for it in r3.get("items", []):
                c = it.get("class")
                try: k = int(it.get("id")) - 1; sp = cands[k]
                except Exception: k = None; sp = expand(p, as_text(it.get("span"))) or as_text(it.get("span"))
                at = cand_objs[k]["attach"] if k is not None else ["*"]
                if c == "format":
                    fmt.append(sp); units_c.append({"cls": "fc", "frags": [sp], "attach": at, "check": it.get("check")})
                elif c == "task":
                    tsk.append(sp); units_c.append({"cls": "tc", "frags": [sp], "attach": at})
                else: drop.append(sp)
    units = [{"cls": "task", "uid": t["id"], "order": i + 1, "frags": t["frags"], "norm": t["norm"]} for i, t in enumerate(tasks)]
    units += units_c
    units += [{"cls": "role", "frags": [x]} for x in role + bad_r] + [{"cls": "bg", "frags": [x]} for x in bg + bad_b]
    units += [{"cls": "mat", "frags": [x]} for x in data + text]
    parsed = {"tasks": tasks,
              "task_constraints": tsk, "format_constraints": fmt,
              "context": {"data": data, "text": text,
                          "background": bg + bad_b, "role": role + bad_r},
              "units": units, "indivisible": None}
    parsed["_entangled_hints"] = r2.get("entangled", [])
    parsed["_dropped"] = drop  # кандидаты, которые S3 счёл не ограничениями
    out["parsed"] = parsed; out["validation"] = validate(p, parsed)
    # S4 / S5
    if judge_model:
        view = judge_view(parsed)
        r4, _, e4 = ask(judge_model, "s4_judge.txt", f"Промпт:\n{p}\n\nРазбор:\n{view}")
        out["stages"]["s4"] = r4 if r4 else {"error": e4}
        hints = json.dumps(parsed["_entangled_hints"], ensure_ascii=False)
        r5, _, e5 = ask(judge_model, "s5_indivisible.txt",
                        f"Промпт:\n{p}\n\nРазбор:\n{view}\n\nПодсказки разметчика о вплетённых требованиях:\n{hints}")
        out["stages"]["s5"] = r5 if r5 else {"error": e5}
        if r5 and r5.get("indivisible"):
            parsed["indivisible"] = {"reason": r5.get("reason"), "evidence": r5.get("evidence"), "note": r5.get("note")}
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
