"""Проверка гейтвея: жив ли эндпоинт и отвечают ли модели из .env.
python scripts/check_endpoints.py"""
import sys
sys.path.insert(0, "src")
from llm import gpt, gpt2, glm
m = [{"role": "user", "content": "Привет! Ответь одним словом: работает?"}]
for name, f in (("разметчик (LLM_MODEL)", gpt), ("судья (LLM_MODEL_JUDGE)", gpt2), ("третья (LLM_MODEL_GLM)", glm)):
    try:
        print(name, "->", f(m, max_tokens=64)[:80])
    except Exception as e:
        print(name, "ОШИБКА:", str(e)[:300])
