"""Оркестратор очереди экспериментов: G0 -> G2 (+G1 регрессия, +G3 судья на эталоне) -> G4 -> G5.
После каждого шага автоматически строится HTML-дашборд (results/dashboards/).

  python scripts/run_queue.py                # вся очередь по порядку
  python scripts/run_queue.py --only g0      # один шаг
  python scripts/run_queue.py --from g2      # начиная с шага
  python scripts/run_queue.py --workers 8 --fresh   # полный перезапуск с чистого листа
  python scripts/run_queue.py --force        # не останавливаться на провале гейта G0
  python scripts/run_queue.py --dry-run      # только показать команды
  python scripts/run_queue.py --open         # открыть index.html в браузере в конце

Прерывать можно в любой момент: прогоны и кэши матчинга дописываются,
повторный запуск продолжит с места остановки (--fresh сбрасывает)."""
import argparse, json, os, subprocess, sys, datetime

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
LOGS = os.path.join(R, "results", "logs")
ITEMS = os.path.join("data", "gold_v3", "items_300.jsonl")
TRAIN = os.path.join("data", "splits", "train.jsonl")
STEPS = ["g0", "g2", "g4", "g5"]

def sh(cmd, tag=None, logname=None, env_extra=None):
    """Запуск команды с живым выводом; лог дублируется в results/logs/."""
    print("\n" + "=" * 70 + "\n$ " + " ".join(cmd) + "\n" + "=" * 70, flush=True)
    if DRY: return 0, ""
    env = dict(os.environ); env.update(env_extra or {})
    p = subprocess.Popen(cmd, cwd=R, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace")
    lines = []
    for l in p.stdout:
        print(l, end="", flush=True); lines.append(l)
    p.wait()
    text = "".join(lines)
    if logname:
        os.makedirs(LOGS, exist_ok=True)
        open(os.path.join(LOGS, logname + ".log"), "w", encoding="utf-8").write(text)
    if p.returncode != 0:
        sys.exit(f"\n!!! команда упала с кодом {p.returncode}: {' '.join(cmd)}\n"
                 f"Исправь причину и перезапусти: python scripts/run_queue.py --from {tag or STEPS[0]}")
    return p.returncode, text

def run_pilot(tag, inp, limit=None):
    cmd = [PY, "scripts/run_pilot.py", "--model", "gpt", "--judge", "gpt2",
           "--in", inp, "--out", f"results/{tag}_gpt_300.jsonl", "--workers", str(WORKERS)]
    if limit: cmd += ["--limit", str(limit)]
    if FRESH: cmd += ["--fresh"]
    sh(cmd, tag=tag, logname=f"{tag}_run")

def dashboard(tag, extra_logs=()):
    extra = [f"--extra={t}=results/logs/{f}.log" for t, f in extra_logs]
    sh([PY, "scripts/dashboard.py", tag] + extra, tag=tag, logname=f"{tag}_dashboard")

def gate_g0():
    """Гейт дымового прогона: ошибки стадий <5%, точные спаны >95%."""
    if DRY: return
    path = os.path.join(R, "results", "g0_gpt_300.jsonl")
    recs = [json.loads(l) for l in open(path, encoding="utf-8")]
    n = max(len(recs), 1)
    err = sum(bool(r.get("errors")) for r in recs)
    exact = sum(bool((r.get("validation") or {}).get("all_exact")) for r in recs)
    print(f"\n--- ГЕЙТ G0: ошибок {err}/{len(recs)} ({100*err/n:.1f}%), точные спаны {exact}/{len(recs)} ({100*exact/n:.1f}%)")
    ok = err / n < 0.05 and exact / n > 0.95
    if not ok and not FORCE:
        sys.exit("!!! ГЕЙТ G0 НЕ ПРОЙДЕН. Смотри results/dashboards/g0.html и results/g0_gpt_300.xlsx,\n"
                 "    чини промпты под GLM, затем: python scripts/run_queue.py --only g0 --fresh\n"
                 "    (или --force, чтобы идти дальше несмотря ни на что)")
    print("--- ГЕЙТ G0:", "ПРОЙДЕН" if ok else "ПРОВАЛЕН, но --force — идём дальше", flush=True)

def step_g0():
    run_pilot("g0", ITEMS, limit=30)
    gate_g0()
    dashboard("g0")

def step_g2():
    run_pilot("g2", ITEMS)
    sh([PY, "scripts/eval_v4.py", "match"], tag="g2", logname="g2_match", env_extra={"TAG": "g2"})
    sh([PY, "scripts/eval_v4.py", "judge-gold"], tag="g2", logname="g2_judge_gold", env_extra={"TAG": "g2"})
    sh([PY, "scripts/eval_v4.py", "report"], tag="g2", logname="g2_report", env_extra={"TAG": "g2"})
    sh([PY, "scripts/regression_check.py", "v4a", "g2"], tag="g2", logname="g2_regression")
    dashboard("g2", extra_logs=[("G1: регрессия правил v5 (v4a → g2)", "g2_regression")])

def step_g4():
    run_pilot("g4", ITEMS, limit=100)
    sh([PY, "scripts/stability.py", "results/g2_gpt_300.jsonl", "results/g4_gpt_300.jsonl"],
       tag="g4", logname="g4_stability")
    dashboard("g4", extra_logs=[("G4: стабильность (g2 → g4)", "g4_stability")])

def step_g5():
    cmd = [PY, "scripts/run_pilot.py", "--model", "gpt", "--judge", "gpt2",
           "--in", TRAIN, "--out", "results/g5_heldout_150.jsonl", "--workers", str(WORKERS),
           "--limit", "150"] + (["--fresh"] if FRESH else [])
    sh(cmd, tag="g5", logname="g5_run")
    dashboard("g5")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=STEPS)
    ap.add_argument("--from", dest="from_step", choices=STEPS)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()
    WORKERS, FRESH, FORCE, DRY = a.workers, a.fresh, a.force, a.dry_run
    if not os.path.exists(os.path.join(R, ".env")):
        sys.exit("Нет .env — скопируй .env.example в .env и впиши LLM_KEY и имена моделей (LLM_MODEL, LLM_MODEL_JUDGE).")
    steps = [a.only] if a.only else STEPS[STEPS.index(a.from_step):] if a.from_step else STEPS
    print(f"очередь: {steps} | workers={WORKERS} fresh={FRESH} force={FORCE}")
    started = datetime.datetime.now()
    for s in steps:
        {"g0": step_g0, "g2": step_g2, "g4": step_g4, "g5": step_g5}[s]()
    print(f"\nВСЁ ГОТОВО за {datetime.datetime.now() - started}. Дашборды: results/dashboards/index.html")
    if a.open and not DRY:
        os.startfile(os.path.join(R, "results", "dashboards", "index.html"))
