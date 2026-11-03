"""Диагностика GLM: какой способ заставляет модель отвечать сразу JSON, без рассуждений.
python scripts/probe_glm.py"""
import os, sys, json, time, subprocess, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import llm  # подтягивает .env
base = os.path.join(os.path.dirname(__file__), "..", "prompts")
SYS = open(os.path.join(base, "s2_extract.txt"), encoding="utf-8").read()
USER = "Привет! Я готовлю доклад для комитета. Представь, что ты юрист. Кратко перескажи <Материал>, не более 50 слов, сохранив имена героев."
SUFFIX = "\n\nОтветь сразу JSON-объектом. Без рассуждений, без анализа, без пояснений."

def call(label, extra=None, suffix=False, max_tokens=1500):
    payload = {"model": os.environ["GLM_MODEL"], "temperature": 0.0, "max_tokens": max_tokens,
               "chat_template_kwargs": {"enable_thinking": False},
               "messages": [{"role": "system", "content": SYS},
                            {"role": "user", "content": USER + (SUFFIX if suffix else "")}]}
    payload.update(extra or {})
    cmd = [shutil.which("curl.exe") or shutil.which("curl"), "-sS", "-m", "200", "-X", "POST", os.environ["GLM_URL"],
           "-H", "X-Token: " + os.environ["GLM_TOKEN"], "-H", "Content-Type: application/json", "--data-binary", "@-"]
    t = time.time()
    r = subprocess.run(cmd, input=json.dumps(payload, ensure_ascii=False).encode("utf-8"), capture_output=True)
    try:
        d = json.loads(r.stdout.decode("utf-8")); ch = d["choices"][0]; c = ch["message"].get("content") or ""
    except Exception:
        print(f"--- {label}: ОШИБКА, ответ сервера: {r.stdout[:300]!r} {r.stderr[:200]!r}"); return
    ok = c.strip().startswith("{")
    print(f"--- {label}: {time.time()-t:.0f} с, finish={ch.get('finish_reason')}, токенов={d.get('usage',{}).get('completion_tokens')}, "
          f"{'JSON СРАЗУ' if ok else 'НЕ JSON'}")
    print("    content[:200]:", repr(c[:200]))

call("A: json_object", {"response_format": {"type": "json_object"}})
call("B: фраза в конце запроса", suffix=True)
call("C: оба способа", {"response_format": {"type": "json_object"}}, suffix=True)
