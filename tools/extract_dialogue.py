#!/usr/bin/env python3
"""List the English texts the runtime table can replace, with their hashes."""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kit"))
import lp
from zh_text import Encoder, fnv1a64

tree, out = Path(sys.argv[1]), Path(sys.argv[2])
enc = Encoder(tree / "charmap.txt", Path(__file__).resolve().parents[1] / "out/cjk_table.json")
files = sorted(tree.glob("data/text/*.inc")) + sorted(tree.glob("data/maps/*/scripts.inc"))
files += sorted(tree.glob("data/scripts/*.inc")) + [tree / "data/event_scripts.s"]
# C-bronnen met echte zinnen. De catalogi (catalog/zh_cn) staan al Chinees in
# de boom; die teksten slaat de lus hieronder over. Namenlijsten (trainers,
# easy chat, decoraties) staan er bewust niet in: die hebben een strakke
# bytegrens en gaan via een catalogus.
C_SOURCES = [
    "src/strings.c",
    "src/battle_message.c",
    "src/berry.c",
    "src/berry_blender.c",
    "src/mystery_event_msg.c",
    "src/data/text/match_call_messages.h",
    "src/data/text/abilities.h",
    "src/data/text/ribbon_descriptions.h",
    "src/data/text/gift_ribbon_descriptions.h",
    "src/data/items.h",
    "src/data/union_room.h",
]
cfiles = [tree / name for name in C_SOURCES if (tree / name).exists()]
rows, seen, skipped = [], set(), 0
for path in files + cfiles:
    rel = path.relative_to(tree).as_posix()
    src = path.read_text(encoding="utf-8")
    is_inc = lp.is_script(rel)
    texts = lp.inc_texts(src) if is_inc else lp.c_texts(src)
    ctx = rel.split("/")[2] if rel.startswith("data/maps/") else Path(rel).stem
    for label, (_, _, text) in texts.items():
        if any(ord(c) > 0x2000 for c in text):
            continue  # already Chinese in the build
        try:
            data = enc.encode(text, terminate=not is_inc, cjk=False)
        except ValueError as e:
            skipped += 1
            continue
        if 0xFF not in data:
            continue
        data = data[:data.index(0xFF) + 1]
        if len(data) < 3:
            continue
        h = fnv1a64(data)
        if h in seen:
            continue
        seen.add(h)
        rows.append({"id": rel + ":" + label, "hash": "%016x" % h, "context": ctx,
                     "kind": "box" if is_inc else "c", "en": text})
with out.open("w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(len(rows), "texts,", skipped, "skipped")
