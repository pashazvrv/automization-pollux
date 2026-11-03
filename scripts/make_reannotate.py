"""Страница для переразметки: открывается с прежней разметкой, правишь вместо разметки с нуля.
python scripts/make_reannotate.py [--src data/gold/gold_annotations.json] [--tag A2]  ->  tools/annotator_<tag>.html, экспорт gold_annotations_<tag>.json"""
import argparse, json
ap = argparse.ArgumentParser(); ap.add_argument("--src", default="data/gold/gold_annotations.json"); ap.add_argument("--tag", default="A2")
a = ap.parse_args()
src = json.load(open(a.src, encoding="utf-8"))
items = [{"id": x["id"], "text": x["text"]} for x in src]
init = {x["id"]: {"ann": x["annotations"], "indivisible": x["indivisible"], "note": x["note"], "seen": False} for x in src}
RULES = """<details open style="margin:10px 0"><summary style="cursor:pointer;font-weight:600">Правила разметки (v2)</summary>
<ol class="mut" style="padding-left:18px;margin:6px 0">
<li><b>Задача</b> = глагол + прямой объект («Напиши оду», «Исправь ошибки», «придумать слоган»). Всё, что уточняет объект («восхваляющую семью», «в окончаниях…», «для продукции из…», «на тему…», «о случае из жизни…»), — <b>огр. задачи</b>.</li>
<li>Несколько действий над одним объектом в одном предложении — одна задача.</li>
<li>Деепричастие и «используя/заменяя…» — способ: <b>огр.</b>, не отдельная задача.</li>
<li><b>Роль</b>: «Представь, что ты…», «от лица…», «Ты — …» и описание назначенного персонажа (характер, прошлое) — всё в роль.</li>
<li><b>Фон</b>: кто говорит и что случилось. Условия, которые сужают ответ («если у меня нет денег», «учти, что я…»), — <b>огр. задачи</b>.</li>
<li><b>Формат</b>: объём, структура, стиль («в стиле барокко», «в стиле Белого»), тон, язык ответа, адресат, порядок и шкала («по шкале от 1 до 10»). Содержание, привязанное к объекту («превратив плюсы в минусы»), — огр. задачи.</li>
<li>«Переведи на русский»: язык перевода — в задачу.</li>
<li>Вопрос без команды («Почему Италия…?») — задача.</li>
<li>Цитата или текст внутри вопроса — материал.</li>
<li>Нет задачи или нельзя разделить — клавиша <kbd>0</kbd> и причина в заметке.</li>
</ol></details>"""
tpl = open("tools/annotator_template.html", encoding="utf-8").read()
html = (tpl.replace("__ITEMS__", json.dumps(items, ensure_ascii=False)).replace("__INIT__", json.dumps(init, ensure_ascii=False))
        .replace("__RULES__", RULES).replace("__SK__", f"gold_annotations_v1_{a.tag}").replace("__FILE__", f"gold_annotations_{a.tag}.json"))
open(f"tools/annotator_{a.tag}.html", "w", encoding="utf-8").write(html)
print("готово:", len(items), "запросов с прежней разметкой ->", f"tools/annotator_{a.tag}.html")
