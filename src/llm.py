"""Клиент LLM через LiteLLM-гейтвей (gigagateway).

Эндпоинт OpenAI-совместимый: POST <LLM_URL> с заголовком X-Api-Key.
Провайдер фиксируется полем "provider": {"only": [...]} (LLM_PROVIDER, по умолчанию "alibaba";
пустая строка — поле не отправляется).

Слоты моделей (имя = переменная окружения с именем модели на гейтвее):
  gpt  -> LLM_MODEL         разметчик (S1–S4)
  gpt2 -> LLM_MODEL_JUDGE   судья (S5), фиксер (S6), оценщик в eval_v4
  glm  -> LLM_MODEL_GLM     третья модель для сравнений (по умолчанию = LLM_MODEL)
"""
import os, json, shutil, subprocess, time, requests
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass   # переменные уже в окружении или команда работает без LLM (report)

DEFAULT_URL = "https://gigagateway.eye.salute.ru/litellm/v1/chat/completions"


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
    """Запасной путь через системный curl (на случай проблем Python-SSL в сети очереди)."""
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


def _chat(model, messages, max_tokens, temperature):
    if not model:
        raise RuntimeError("не задано имя модели: проверь LLM_MODEL / LLM_MODEL_JUDGE / LLM_MODEL_GLM в .env")
    url = os.environ.get("LLM_URL", DEFAULT_URL)
    key = os.environ.get("LLM_KEY")
    if not key:
        raise RuntimeError("не задан LLM_KEY (ключ гейтвея) в .env")
    headers = {"X-Api-Key": key, "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages,
               "max_tokens": max_tokens, "temperature": temperature}
    prov = os.environ.get("LLM_PROVIDER", "alibaba").strip()
    if prov:
        payload["provider"] = {"only": [p.strip() for p in prov.split(",") if p.strip()]}
    post = _post_curl if os.environ.get("LLM_USE_CURL", "0") == "1" else _post
    return post(url, headers, payload)


def gpt(messages, max_tokens=2048, temperature=0.0):
    """Основная модель — разметчик (LLM_MODEL)."""
    return _chat(os.environ.get("LLM_MODEL"), messages, max_tokens, temperature)


def gpt2(messages, max_tokens=2048, temperature=0.0):
    """Модель судьи/фиксера/оценщика (LLM_MODEL_JUDGE; по умолчанию = LLM_MODEL)."""
    return _chat(os.environ.get("LLM_MODEL_JUDGE") or os.environ.get("LLM_MODEL"),
                 messages, max_tokens, temperature)


def glm(messages, max_tokens=2048, temperature=0.0):
    """Третья модель для сравнений (LLM_MODEL_GLM; по умолчанию = LLM_MODEL)."""
    return _chat(os.environ.get("LLM_MODEL_GLM") or os.environ.get("LLM_MODEL"),
                 messages, max_tokens, temperature)
