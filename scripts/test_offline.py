"""Офлайн-тесты без доступа к гейтвею: клиент, сборка few-shot, сквозной пайплайн на заглушках.
python scripts/test_offline.py"""
import os, sys, json, types

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(R, "src"))
os.environ.update({"LLM_KEY": "test-key", "LLM_MODEL": "model-a",
                   "LLM_MODEL_JUDGE": "model-b", "LLM_PROVIDER": "alibaba"})
os.environ.pop("LLM_URL", None)

import llm

# ---------- 1. клиент гейтвея ----------
calls = []
class FakeResp:
    def raise_for_status(self): pass
    def json(self):
        return {"choices": [{"message": {"content": "ok-ответ"}, "finish_reason": "stop"}], "usage": {}}
def fake_post(url, headers, json, timeout):
    calls.append({"url": url, "headers": headers, "json": json})
    return FakeResp()
llm.requests.post = fake_post

out = llm.gpt([{"role": "user", "content": "Привет!"}], max_tokens=10)
c = calls[-1]
assert out == "ok-ответ"
assert c["url"] == llm.DEFAULT_URL, c["url"]
assert c["headers"]["X-Api-Key"] == "test-key"
assert c["headers"]["Content-Type"] == "application/json"
assert c["json"]["model"] == "model-a"
assert c["json"]["provider"] == {"only": ["alibaba"]}
print("1. gpt: url, X-Api-Key, provider, модель из env — ОК")

llm.gpt2([{"role": "user", "content": "x"}])
assert calls[-1]["json"]["model"] == "model-b"
print("2. gpt2: слот судьи берёт LLM_MODEL_JUDGE — ОК")

os.environ.pop("LLM_MODEL_GLM", None)
llm.glm([{"role": "user", "content": "x"}])
assert calls[-1]["json"]["model"] == "model-a"   # fallback на основную
print("3. glm: fallback на LLM_MODEL — ОК")

os.environ["LLM_PROVIDER"] = ""
llm.gpt([{"role": "user", "content": "x"}])
assert "provider" not in calls[-1]["json"]
os.environ["LLM_PROVIDER"] = "alibaba"
print("4. пустой LLM_PROVIDER — поле provider не отправляется — ОК")

# пустой/обрезанный ответ — ошибка
class BadResp(FakeResp):
    def json(self): return {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
llm.requests.post = lambda *a, **kw: BadResp()
try:
    llm.gpt([{"role": "user", "content": "x"}]); raise AssertionError("ждали ошибку")
except RuntimeError as e:
    assert "length" in str(e) or "пустой" in str(e)
print("5. обрезанный/пустой ответ — диагностируемая ошибка — ОК")
llm.requests.post = fake_post

# ---------- 2. сборка few-shot ----------
import pipeline
few = pipeline.fewshot_file("s2_extract.txt")
assert "ПРИМЕРЫ" in few
msg = pipeline.assemble("s2_extract.txt", "ТЕСТОВЫЙ ВХОД 123")
assert "НАЧАЛО ПРИМЕРОВ" in msg and "КОНЕЦ ПРИМЕРОВ" in msg
assert msg.endswith("ТЕСТОВЫЙ ВХОД 123")
assert msg.index("КОНЕЦ ПРИМЕРОВ") < msg.index("ТЕСТОВЫЙ ВХОД 123")
assert "ПРИМЕРЫ" in msg
plain = pipeline.assemble("s1_material.txt", "ВХОД БЕЗ ПРИМЕРОВ")
assert plain == "ВХОД БЕЗ ПРИМЕРОВ"
print("6. few-shot отделён рамками от входа; у S1 примеров нет — ОК")

# правила больше не содержат примеров
rules = pipeline.prompt_file("s2_extract.txt")
assert "ПРИМЕРЫ" not in rules
print("7. в системном промпте остались только правила — ОК")

# ---------- 3. сквозной пайплайн на заглушках ----------
STUBS = {
    "s1_material.txt": {"data": []},
    "s2_extract.txt": {"tasks": [{"id": "t1", "frags": ["Напиши", "план"], "norm": "Написать план"}],
                       "role": [], "background": [],
                       "candidates": [{"span": "подробный", "attach": ["t1"]}], "entangled": []},
    "s3_atomize.txt": {"items": [{"id": 1, "atoms": [{"norm": "подробный план", "src": ["подробный"]}], "move_to": None}]},
    "s4_classify.txt": {"items": [{"id": 1, "class": "task", "check": None}]},
    "s5_judge.txt": {"verdict": "ok", "errors": []},
    "s6_fix.txt": {"fixed": False, "parse": None, "applied": [], "rejected": [],
                   "indivisible": False, "reason": None, "evidence": "", "note": "обычная просьба"},
}
seen_users = []
def stub(messages, max_tokens=2048, temperature=0.0):
    sysmsg = messages[0]["content"]
    seen_users.append(messages[1]["content"])
    for name, resp in STUBS.items():
        if pipeline.prompt_file(name) == sysmsg:
            return json.dumps(resp, ensure_ascii=False)
    raise AssertionError("неизвестный стейдж")
for k in pipeline.CALL:
    pipeline.CALL[k] = stub

rec = {"id": "test1", "instruction": "Будь другом, напиши мне подробный план."}
out = pipeline.atomize(rec, "gpt", "gpt2")
assert not out["errors"], out["errors"]
e = out["export"]
assert e["tasks"] == ["Написать план"], e["tasks"]
assert e["constraints"]["task_constraints"] == ["подробный план"]
assert e["indivisible"] is False
# во входе S2 и S3 лежат примеры с рамками, во входе S1 — нет
assert any("НАЧАЛО ПРИМЕРОВ" in u and "напиши мне подробный план" in u for u in seen_users)
assert seen_users[0] == rec["instruction"]
print("8. сквозной прогон S1→S6 на заглушках: export корректен, рамки на месте — ОК")

print("\nВСЕ ТЕСТЫ ПРОШЛИ")
