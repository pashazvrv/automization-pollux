import os, json, shutil, subprocess, time, requests
from dotenv import load_dotenv
load_dotenv()

def _extract(data):
    """Достаёт текст ответа; пустой или обрезанный ответ — ошибка с диагнозом."""
    ch = data["choices"][0]; msg = ch["message"]
    content = msg.get("content") or ""
    fin = ch.get("finish_reason")
    thinking = bool(msg.get("reasoning_content") or msg.get("reasoning"))
    if not content.strip():
        raise RuntimeError(f"пустой content; finish_reason={fin}; рассуждение={'есть' if thinking else 'нет'}; usage={data.get('usage')}")
    if fin == "length":
        raise RuntimeError(f"length: ответ обрезан по max_tokens; usage={data.get('usage')}")
    return content

def _post(url, headers, payload, retries=2):
    for i in range(retries):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=300)
            r.raise_for_status()
            return _extract(r.json())
        except requests.RequestException:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)

def _post_curl(url, headers, payload, retries=2):
    """Вызов через системный curl: у части сетей Python-SSL к tuna.am обрывается.
    Повторяет только сетевые сбои; пустой/обрезанный ответ поднимается наверх сразу."""
    curl = shutil.which("curl.exe") or shutil.which("curl")
    cmd = [curl, "-sS", "-m", "300", "-X", "POST", url]
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    cmd += ["--data-binary", "@-"]
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for i in range(retries):
        r = subprocess.run(cmd, input=body, capture_output=True, timeout=320)
        if r.returncode == 0:
            return _extract(json.loads(r.stdout.decode("utf-8")))
        if i == retries - 1:
            raise RuntimeError("curl: " + r.stderr.decode("utf-8", "replace")[:300])
        time.sleep(2 ** i)

def glm(messages, max_tokens=2048, temperature=0.0):
    payload = {"model": os.environ["GLM_MODEL"], "messages": messages,
               "max_tokens": max_tokens, "temperature": temperature}
    if os.environ.get("GLM_NO_THINK", "1") == "1":
        payload["chat_template_kwargs"] = {"enable_thinking": False}  # отключить рассуждение (если сервер поддерживает)
    post = _post if os.environ.get("GLM_USE_CURL", "1") == "0" else _post_curl
    return post(os.environ["GLM_URL"],
                {"X-Token": os.environ["GLM_TOKEN"], "Content-Type": "application/json"}, payload)

def _openrouter(model_env, messages, max_tokens, temperature):
    return _post("https://openrouter.ai/api/v1/chat/completions",
                 {"Authorization": "Bearer " + os.environ["OPENROUTER_KEY"]},
                 {"model": os.environ[model_env], "messages": messages,
                  "max_tokens": max_tokens, "temperature": temperature})

def gpt(messages, max_tokens=2048, temperature=0.0):
    """Основная модель OpenRouter (OPENROUTER_MODEL)."""
    return _openrouter("OPENROUTER_MODEL", messages, max_tokens, temperature)

def gpt2(messages, max_tokens=2048, temperature=0.0):
    """Вторая модель OpenRouter (OPENROUTER_MODEL_2) — другая модель для судьи."""
    return _openrouter("OPENROUTER_MODEL_2", messages, max_tokens, temperature)
