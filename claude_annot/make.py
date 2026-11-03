# -*- coding: utf-8 -*-
import sys, os, glob, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
from lib import *
for f in sorted(glob.glob(os.path.join(lib.OUTDIR, "[bcns][0-9][0-9].py"))):
    exec(compile(open(f, encoding="utf-8").read(), f, "exec"), {k: getattr(lib, k) for k in dir(lib) if not k.startswith("__")})
out, errs = lib.build()
nn=sum(1 for A in lib.ANN.values() if A.get("norm"))
print("нормализовано:", nn)
print("размечено:", len(lib.ANN), "| собрано:", len(out), "| ошибок:", len(errs))
for e in errs[:80]: print("  ERR", e)
if "--write" in sys.argv:
    json.dump(out, open(os.path.join(lib.OUTDIR, "claude_300.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tpl = open(os.path.join(lib.R, "tools", "annotator_v3.html"), encoding="utf-8").read()
    assert "const EMBED=null;" in tpl
    html = tpl.replace("const EMBED=null;", "const EMBED=" + json.dumps(out, ensure_ascii=False).replace("</", "<\\/") + ";", 1)
    import hashlib
    ver = hashlib.md5(json.dumps(out, ensure_ascii=False).encode()).hexdigest()[:8]
    html = html.replace('"annv3b"', '"annv3_claude_' + ver + '"').replace("Разметчик v3", "Разметчик v3 — черновик Claude (норм., " + ver + ")")
    print("ключ хранилища:", "annv3_claude_" + ver)
    open(os.path.join(lib.R, "tools", "annotator_v3_claude.html"), "w", encoding="utf-8").write(html)
    print("записано: claude_annot/claude_300.json, tools/annotator_v3_claude.html")
