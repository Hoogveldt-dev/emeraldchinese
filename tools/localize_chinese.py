#!/usr/bin/env python3
"""Stage the Simplified Chinese texts into a bootstrapped tree.

    python localize_chinese.py --tree build/upstream --catalog zh_cn --table cjk_table.json
    python localize_chinese.py ... --check

The catalogs have the format of tools/locales/pt_br (see localize_portuguese.py):
    [LABEL] <hash of the English text>
    <text, written as in the source>

CJK characters are encoded as two bytes (lead, trail) from cjk_table.json;
their charmap lines are added to the tree's charmap.txt before staging.
A CJK character is 12 px wide, a CJK name takes 2 bytes per character.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lp  # localize_portuguese, copied next to this file

CJK_WIDTH = 12
MESSAGE_BOX_WIDTH = 208
NAME_BYTES = {"src/data/items.h": 13, "src/data/text/move_names.h": 12,
              "src/data/text/species_names.h": 10, "src/data/pokemon/pokedex_entries.h": 11,
              "src/data/text/trainer_class_names.h": 12}
NAME_PREFIX_BYTES = {"src/data/text/abilities.h": ("ABILITY_", 12), "src/battle_main.c": ("TYPE_", 6)}
CHARMAP_MARK = "@ --- Chinese build (localize_chinese.py) ---"


def is_cjk(c: str) -> bool:
    return ord(c) > 0x2000


class Charset(lp.Charset):
    def __init__(self, tree: Path, table: dict):
        super().__init__(tree)
        self.cjk = table

    def check(self, text):
        problems = []
        for line in self.lines(text):
            for item in line:
                if item.startswith("{"):
                    words = item[1:-1].split()
                    if not words or words[0] not in self.names:
                        problems.append("unknown placeholder " + item)
                elif is_cjk(item):
                    if item not in self.cjk:
                        problems.append("no glyph for %r" % item)
                elif item not in self.codes and item != "$":
                    problems.append("character not in the charmap: %r" % item)
        return problems

    def width(self, line):
        total = 0
        for item in line:
            if item.startswith("{"):
                total += lp.placeholder_width(item[1:-1].split()[0])
            elif item == "$":
                pass
            elif is_cjk(item):
                total += CJK_WIDTH
            else:
                total += self.widths[self.codes[item]]
        return total

    def size(self, text):
        total = len(re.findall(r"\\[nlp]", text))
        for line in self.lines(text):
            for item in line:
                if item.startswith("{"):
                    total += sum(self.sizes.get(w, 1) for w in item[1:-1].split())
                elif item != "$":
                    total += 2 if is_cjk(item) else 1
        return total


def add_charmap(tree: Path, table: dict, used: set[str]) -> None:
    path = tree / "charmap.txt"
    text = path.read_text(encoding="utf-8")
    if CHARMAP_MARK in text:
        text = text[:text.index(CHARMAP_MARK)]
    keep = []
    for line in text.splitlines():
        m = re.match(r"^'(.)'\s*=", line.strip())
        if m and m.group(1) in used:
            continue  # a Japanese code for a character the Chinese text uses
        keep.append(line)
    keep.append(CHARMAP_MARK)
    for ch in sorted(used):
        lead, trail = table[ch]
        keep.append("'%s' = %02X %02X" % (ch, lead, trail))
    path.write_text("\n".join(keep) + "\n", encoding="utf-8")


def localize(tree, catalog_dir, relative, charset, write):
    catalog = catalog_dir / (relative + ".txt")
    entries = lp.read_catalog(catalog)
    path = tree / relative
    source = path.read_text(encoding="utf-8")
    is_inc = lp.is_script(relative)
    texts = lp.inc_texts(source) if is_inc else lp.c_texts(source)
    problems, warnings, edits, seen = [], [], [], set()
    prefix, prefix_bytes = NAME_PREFIX_BYTES.get(relative, (None, 0))
    for e in entries:
        where = "%s [%s]" % (relative, e.label)
        if e.label in seen:
            problems.append(where + ": listed twice"); continue
        seen.add(e.label)
        if e.label not in texts:
            problems.append(where + ": no such text"); continue
        start, end, english = texts[e.label]
        if english == e.text:
            continue  # staged before
        if lp.text_hash(english) != e.digest:
            problems.append(where + ": English text changed (%s)" % lp.text_hash(english)); continue
        local = [where + ": " + p for p in charset.check(e.text)]
        if is_inc and not e.text.endswith("$"):
            local.append(where + ": must end in $")
        glyphs = ("{PKMN}", "{POKEBLOCK}")
        if [x for x in lp.placeholders(e.text) if x not in glyphs] != [x for x in lp.placeholders(english) if x not in glyphs]:
            local.append(where + ": placeholders %s vs %s" % (lp.placeholders(e.text), lp.placeholders(english)))
        limit = NAME_BYTES.get(relative)
        if prefix and e.label.startswith(prefix):
            limit = prefix_bytes
        if not local and limit and charset.size(e.text) > limit:
            local.append(where + ": %d bytes, at most %d" % (charset.size(e.text), limit))
        if not local and relative not in NAME_BYTES and relative not in NAME_PREFIX_BYTES:
            room = e.width or max(charset.widest(english), MESSAGE_BOX_WIDTH if (is_inc or relative == "src/battle_message.c") else 0)
            for n, line in enumerate(charset.lines(e.text), 1):
                if charset.width(line) > room:
                    warnings.append(where + ": line %d %d px > %d" % (n, charset.width(line), room))
        problems += local
        edits.append((start, end, e.text))
    if write and not problems:
        if is_inc:
            lines = source.split("\n")
            for start, end, text in sorted(edits, reverse=True):
                lines[start:end] = lp.inc_lines(text)
            source = "\n".join(lines)
        else:
            for start, end, text in sorted(edits, reverse=True):
                source = source[:start] + '"' + text + '"' + source[end:]
        path.write_text(source, encoding="utf-8", newline="")
    return len(edits), problems, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, required=True)
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--table", type=Path, required=True)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    t = json.loads(a.table.read_text(encoding="utf-8"))
    table = {}
    for i, ch in enumerate(t["chars"]):
        table[ch] = (t["leads"][i // t["trails"]], t["trail_min"] + i % t["trails"])
    rels = sorted(str(p.relative_to(a.catalog).with_suffix("")).replace("\\", "/")
                  for p in a.catalog.rglob("*.txt"))
    used = set()
    for r in rels:
        for e in lp.read_catalog(a.catalog / (r + ".txt")):
            used.update(c for c in e.text if is_cjk(c))
    missing = sorted(c for c in used if c not in table)
    if missing:
        raise SystemExit("no glyph for: " + "".join(missing))
    if not a.check:
        add_charmap(a.tree, table, used)
    charset = Charset(a.tree, table)
    for c in used:  # the charmap check of plain characters must accept them
        charset.codes.setdefault(c, 0)
    total, probs, warns = 0, [], []
    for r in rels:
        n, p, w = localize(a.tree, a.catalog, r, charset, write=False)
        total += n; probs += p; warns += w
    for w in warns:
        print("warning:", w, file=sys.stderr)
    if probs:
        print("\n".join(probs), file=sys.stderr)
        raise SystemExit("localize_chinese: %d problem(s), nothing staged" % len(probs))
    if a.check:
        print("localize_chinese: %d texts check out (%d width warnings)" % (total, len(warns)))
        return
    for r in rels:
        localize(a.tree, a.catalog, r, charset, write=True)
    print("localize_chinese: %d texts staged from %d files, %d CJK characters (%d width warnings)"
          % (total, len(rels), len(used), len(warns)))


if __name__ == "__main__":
    main()
