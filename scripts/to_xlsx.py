"""Результаты прогона -> Excel для просмотра.
python scripts/to_xlsx.py results/pilot_gpt.jsonl   (-> results/pilot_gpt.xlsx)
Вызывается автоматически в конце scripts/run_pilot.py."""
import json, sys, os, re, time
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ILL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
def cut(x, n=500):
    x = ILL.sub("", str(x)); return x if len(x) <= n else x[:n] + " …[обрезано]"
def lst(x): return "\n".join(f"• {cut(i, 300)}" for i in x) if x else ""

def convert(inp):
    """Возвращает (путь к xlsx, статистика)."""
    out = os.path.splitext(inp)[0] + ".xlsx"
    src = {}
    for l in open(os.path.join(ROOT, "data", "splits", "pool.jsonl"), encoding="utf-8"):
        d = json.loads(l); src[d["id"]] = d
    cols = ["id", "группа", "тип задачи", "длина", "запрос (начало)",
            "TASK: задачи", "TASK CONSTRAINTS: ограничения задачи", "FORMAT CONSTRAINTS: ограничения формата",
            "CONTEXT: фон (background)", "CONTEXT: роль (role)", "CONTEXT: материал (data/text)",
            "неделим", "судья", "ошибки судьи", "спаны точные", "покрытие", "ошибки стадий"]
    wb = Workbook(); ws = wb.active; ws.title = "разбор"; ws.append(cols)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="305496")
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for line in open(inp, encoding="utf-8"):
        r = json.loads(line); p = src.get(r["id"], {}); ps = r.get("parsed") or {}; c = ps.get("context", {})
        s4 = r.get("stages", {}).get("s4") or {}; v = r.get("validation") or {}
        ind = ps.get("indivisible")
        ws.append([r["id"], p.get("group"), p.get("task_type"), len(p.get("instruction", "")), cut(p.get("instruction", ""), 400),
                   lst([t.get("norm") or t.get("span") for t in ps.get("tasks", [])]), lst(ps.get("task_constraints")),
                   lst(ps.get("format_constraints")), lst(c.get("background")), lst(c.get("role")),
                   lst([cut(x, 120) for x in c.get("data", []) + c.get("text", [])]),
                   (ind.get("reason") + ": " + str(ind.get("note"))) if ind else "",
                   s4.get("verdict", s4.get("error", "")),
                   "\n".join(f"[{e.get('severity','')} {e.get('type')}] {e.get('span','')}: {e.get('note','')}" for e in s4.get("errors", [])) if isinstance(s4, dict) else "",
                   v.get("all_exact"), v.get("coverage"), cut("; ".join(r.get("errors", [])), 300)])
    widths = [9, 7, 22, 8, 50, 40, 40, 36, 36, 24, 36, 30, 9, 60, 9, 9, 30]
    for i, w in enumerate(widths, 1): ws.column_dimensions[get_column_letter(i)].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "B2"; ws.auto_filter.ref = ws.dimensions


    stats = {"n": 0, "errors": 0, "exact": 0, "judge_ok": 0, "judge_fix": 0, "judge_none": 0, "indivisible": 0}
    for line in open(inp, encoding="utf-8"):
        r = json.loads(line); stats["n"] += 1
        stats["errors"] += bool(r.get("errors")) and not r.get("parsed")
        stats["exact"] += bool((r.get("validation") or {}).get("all_exact"))
        vd = ((r.get("stages") or {}).get("s4") or {}).get("verdict")
        stats["judge_ok" if vd == "ok" else "judge_fix" if vd == "fix" else "judge_none"] += 1
        stats["indivisible"] += bool((r.get("parsed") or {}).get("indivisible"))
    try:
        wb.save(out)
    except PermissionError:
        out = os.path.splitext(inp)[0] + time.strftime("_%H%M%S") + ".xlsx"
        wb.save(out); print("(основной .xlsx открыт в Excel, сохранил отдельно)")
    return out, stats

if __name__ == "__main__":
    o, st = convert(sys.argv[1] if len(sys.argv) > 1 else "results/pilot_gpt.jsonl")
    print("сохранено:", o, st)
