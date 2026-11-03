import sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
for f in sorted(glob.glob(os.path.join(lib.OUTDIR, "[bc][0-9][0-9].py"))):
    exec(compile(open(f, encoding="utf-8").read(), f, "exec"), {k: getattr(lib, k) for k in dir(lib) if not k.startswith("__")})
lo, hi = int(sys.argv[1]), int(sys.argv[2])
for k, it in enumerate(lib.items()[lo:hi], lo):
    A = lib.ANN[it["id"]]; t = it["text"]; used = []
    xs = [lib.resolve(t, s, used) for s in A["data"] + A["text"]]
    for x in xs: t = t.replace(x, "‹МАТ: " + x[:35].replace("\n", " ") + "…›", 1)
    t = t.replace("\n", "⏎")
    print("## %d %s%s\n%s" % (k, it["id"], "  [НЕДЕЛИМ " + A["ind"] + "]" if A["ind"] else "", t))
    if A["role"]: print("  role:", A["role"])
    if A["bg"]: print("  bg:", [b[:90] for b in A["bg"]])
