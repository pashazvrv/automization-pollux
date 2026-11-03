import sys; sys.path.insert(0, "src")
from llm import glm, gpt
m = [{"role": "user", "content": "Сколько будет 2+2? Ответь одним числом."}]
for name, f in (("GLM-5.3", glm), ("GPT/OpenRouter", gpt)):
    try:
        print(name, "->", f(m, max_tokens=64))
    except Exception as e:
        print(name, "ОШИБКА:", e)
