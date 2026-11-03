#!/usr/bin/env python3
"""The built-in Chinese texts (catalog/zh_cn) with the key the game uses.

A catalog text is compiled into the game as Chinese, so the game does not look
it up in zh_dialog.bin: Cjk_TextKey hashes the bytes it has in front of it.
This writes those hashes, so the word data for the dictionary can be keyed the
same way (kit/zh_catalog.jsonl, read by translate_dialogue.py build).

Run after the port's bootstrap and before tools/localize_chinese.py, when the
tree still holds the English.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kit"))
import lp
from zh_text import Encoder, fnv1a64

ROOT = Path(__file__).resolve().parents[1]


def rows(tree: Path, catalog_dir: Path, enc: Encoder):
    out, problems = [], []
    for catalog in sorted(catalog_dir.rglob("*.txt")):
        relative = catalog.relative_to(catalog_dir).as_posix()[:-len(".txt")]
        source = tree / relative
        if not source.exists():
            problems.append("%s: no such file in the tree" % relative)
            continue
        is_inc = lp.is_script(relative)
        texts = lp.inc_texts(source.read_text(encoding="utf-8")) if is_inc \
            else lp.c_texts(source.read_text(encoding="utf-8"))
        for e in lp.read_catalog(catalog):
            english = texts.get(e.label)
            if english is None:
                problems.append("%s [%s]: no such text" % (relative, e.label))
                continue
            english = english[2]
            if lp.text_hash(english) != e.digest:
                problems.append("%s [%s]: English text changed" % (relative, e.label))
                continue
            try:
                data = enc.encode(e.text, terminate=not is_inc)
            except ValueError as problem:
                problems.append("%s [%s]: %s" % (relative, e.label, problem))
                continue
            if 0xFF not in data:
                continue
            data = data[:data.index(0xFF) + 1]
            out.append({"id": relative + ":" + e.label, "hash": "%016x" % fnv1a64(data),
                        "context": Path(relative).stem, "kind": "c",
                        "en": english, "zh": e.text})
    return out, problems


def main():
    tree = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "kit/zh_catalog.jsonl"
    enc = Encoder(tree / "charmap.txt", ROOT / "out/cjk_table.json")
    found, problems = rows(tree, ROOT / "catalog/zh_cn", enc)
    seen = {}
    with out.open("w", encoding="utf-8") as f:
        for r in found:
            # The same text twice (two labels, one string): one entry is enough.
            if r["hash"] in seen:
                continue
            seen[r["hash"]] = r
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("%s: %d texts (%d duplicates)" % (out, len(seen), len(found) - len(seen)))
    for p in problems[:10]:
        print("  " + p, file=sys.stderr)
    if problems:
        print("  %d problems" % len(problems), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
