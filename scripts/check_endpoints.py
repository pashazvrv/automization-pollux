"""Проверка гейтвея: жив ли эндпоинт и отвечают ли модели из .env.
python scripts/check_endpoints.py
Код выхода 0 — все слоты отвечают; 1 — хотя бы один не отвечает."""
import sys
sys.path.insert(0, "src")
from llm import gpt, gpt2, glm
m = [{"role": "user", "content": "Привет! Ответь одним словом: работает?"}]
bad = 0
for name, f in (("разметчик (LLM_MODEL)", gpt), ("судья (LLM_MODEL_JUDGE)", gpt2), ("третья (LLM_MODEL_GLM)", glm)):
    try:
        print(name, "->", f(m, max_tokens=64)[:80])
    except Exception as e:
        bad += 1
        print(name, "ОШИБКА:", str(e)[:300])
sys.exit(1 if bad else 0)
