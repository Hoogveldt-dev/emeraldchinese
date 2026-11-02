#!/usr/bin/env python3
"""label<TAB>chinese -> catalog with the English hashes (from --show output of the source)."""
import re, sys
sys.path.insert(0, __import__("os").path.dirname(__file__))
import lp
from pathlib import Path
tree, rel, tsv, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
src = (tree / rel).read_text(encoding="utf-8")
texts = lp.inc_texts(src) if lp.is_script(rel) else lp.c_texts(src)
lines = ["# Chinese (zh-Hans) for %s" % rel, ""]
miss = 0
for raw in tsv.read_text(encoding="utf-8").splitlines():
    if not raw.strip() or raw.startswith("#"):
        continue
    label, zh = raw.split("\t", 1)
    if label not in texts:
        print("missing label", label); miss += 1; continue
    lines += ["[%s] %s" % (label, lp.text_hash(texts[label][2])), zh, ""]
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(lines), encoding="utf-8")
print(rel, len(lines) // 3, "entries,", miss, "missing")
