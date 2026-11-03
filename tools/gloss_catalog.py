#!/usr/bin/env python3
"""Word data for the built-in Chinese texts (catalog/zh_cn).

kit/zh_catalog.jsonl (tools/catalog_texts.py) says which texts the game has
compiled in and under which hash it looks them up. This adds the words of
those texts, with the same checks as the dialogue route:

  tools/gloss_catalog.py status
  tools/gloss_catalog.py names --context move_names
  tools/gloss_catalog.py ask --estimate
  tools/gloss_catalog.py ask --context battle_message
  tools/gloss_catalog.py todo --context battle_message --limit 30 > ask.json
  tools/gloss_catalog.py accept answer.json

`ask` lets the language model do it (DEEPSEEK_API_KEY in the environment,
never in a file here); `todo` and `accept` do the same by hand. Either way
the answer is checked that the words together form the paragraph,
that the pinyin fits the characters, and repairs tones with CC-CEDICT where
that is free. `names` does single-word texts without asking anyone: the word
is the whole text, the meaning its English name.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit"))
import zh_gloss
from zh_pinyin import han_count, to_marks

TEXTS = ROOT / "kit/zh_catalog.jsonl"
GLOSS = ROOT / "kit/zh_catalog_gloss.json"
CEDICT = ROOT / "kit/cedict_ts.u8"


def load_texts(context=None, only=None):
    if not TEXTS.exists():
        sys.exit("%s is missing: run tools/catalog_texts.py (or scripts/build.sh)" % TEXTS)
    rows = [json.loads(line) for line in TEXTS.open(encoding="utf-8")]
    for r in rows:
        r["paras"] = zh_gloss.paragraphs(r["zh"])
    rows = [r for r in rows if any(han_count(p) for p in r["paras"])]
    if context:
        rows = [r for r in rows if r["context"] in context.split(",")]
    if only:
        rows = [r for r in rows if only in r["id"]]
    return rows


def load_gloss() -> dict:
    return json.loads(GLOSS.read_text(encoding="utf-8")) if GLOSS.exists() else {}


def save_gloss(gloss: dict):
    GLOSS.write_text(json.dumps(gloss, ensure_ascii=False, indent=0, sort_keys=True),
                     encoding="utf-8")


def pending(rows, gloss):
    return [r for r in rows if gloss.get(r["hash"], {}).get("zh") != zh_gloss.zh_key(r["paras"])]


def cmd_status(args):
    rows = load_texts(args.context)
    gloss = load_gloss()
    todo = pending(rows, gloss)
    per = {}
    for r in rows:
        done = gloss.get(r["hash"], {}).get("zh") == zh_gloss.zh_key(r["paras"])
        a, b = per.get(r["context"], (0, 0))
        per[r["context"]] = (a + done, b + 1)
    for context, (done, total) in sorted(per.items(), key=lambda kv: kv[1][1] - kv[1][0], reverse=True):
        print("%-22s %5d / %-5d" % (context, done, total))
    print("%-22s %5d / %-5d" % ("total", len(rows) - len(todo), len(rows)))


def cmd_todo(args):
    rows = pending(load_texts(args.context, args.only), load_gloss())
    rows = rows[args.skip:args.skip + args.limit] if args.limit else rows[args.skip:]
    items = [{"id": r["hash"], "en": r["en"], "zh": r["paras"]} for r in rows]
    print(json.dumps(items, ensure_ascii=False, separators=(",", ":")))


def cmd_ask(args):
    """The same question as the dialogue route, for the built-in texts."""
    sys.path.insert(0, str(ROOT / "kit"))
    import translate_dialogue as td
    import llm

    rows = pending(load_texts(args.context, args.only), load_gloss())
    if args.limit:
        rows = rows[:args.limit]
    todo = list(td.batches(rows, args.batch, 4000))
    print("%d texts to annotate in %d requests" % (len(rows), len(todo)))
    if args.estimate:
        td.estimate("gloss", rows, args)
        return 0
    if not todo:
        return 0
    llm.resolve(args)
    cedict = zh_gloss.load_cedict(CEDICT)
    glossary = json.loads((ROOT / "kit/glossary.json").read_text(encoding="utf-8"))
    gloss = load_gloss()
    failed = []

    def names_for(group):
        text = " ".join(" ".join(r["paras"]) for r in group)
        return {zh: en for en, zh in glossary.items() if zh and zh in text}

    def build(group):
        items = [{"id": r["hash"], "en": r["en"], "zh": r["paras"]} for r in group]
        return ("Official names in these texts (Chinese -> English):\n"
                + json.dumps(names_for(group), ensure_ascii=False, separators=(",", ":"))
                + "\n\nTexts:\n" + json.dumps(items, ensure_ascii=False, separators=(",", ":")))

    def accept(group, answer):
        done = 0
        for r in group:
            paras, errors = zh_gloss.check_answer(r["paras"], answer.get(r["hash"]))
            if errors:
                failed.append((r["id"], errors))
                continue
            warn = zh_gloss.apply_cedict(paras, cedict) if cedict else []
            gloss[r["hash"]] = {"zh": zh_gloss.zh_key(r["paras"]), "w": paras, "warn": warn}
            done += 1
        save_gloss(gloss)
        return done

    td.run(args, "gloss-catalog", zh_gloss.SYSTEM, todo, build, accept, failed)
    return 0


def cmd_accept(args):
    answer = json.loads(Path(args.answer).read_text(encoding="utf-8"))
    rows = {r["hash"]: r for r in load_texts()}
    gloss = load_gloss()
    cedict = zh_gloss.load_cedict(CEDICT)
    done, failed = 0, []
    for key, value in answer.items():
        r = rows.get(key)
        if r is None:
            failed.append((key, ["unknown text"]))
            continue
        paras, errors = zh_gloss.check_answer(r["paras"], value)
        if errors:
            failed.append((r["id"], errors))
            continue
        warn = zh_gloss.apply_cedict(paras, cedict) if cedict else []
        gloss[r["hash"]] = {"zh": zh_gloss.zh_key(r["paras"]), "w": paras, "warn": warn}
        done += 1
    save_gloss(gloss)
    print("accepted %d, failed %d" % (done, len(failed)))
    for name, errors in failed[:20]:
        print("  %s: %s" % (name, "; ".join(errors)[:160]), file=sys.stderr)
    return 1 if failed else 0


def cmd_names(args):
    """Texts that are one name: the whole text is the word, pinyin from CC-CEDICT."""
    rows = pending(load_texts(args.context, args.only), load_gloss())
    gloss = load_gloss()
    cedict = zh_gloss.load_cedict(CEDICT)
    done, skipped = 0, []
    for r in rows:
        if len(r["paras"]) != 1:
            skipped.append(r["id"])
            continue
        word = r["paras"][0]
        if word != "".join(c for c in word if han_count(c)) or not han_count(word):
            skipped.append(r["id"])      # punctuation, tokens or Latin letters: not one name
            continue
        pinyin = reading(cedict, word)
        if pinyin is None:
            skipped.append(r["id"])
            continue
        meaning = args.meaning or r["en"].strip().lower()
        items = [[word, to_marks(pinyin), meaning, 0]]
        paras, errors = zh_gloss.check_answer([word], [items])
        if errors:
            skipped.append(r["id"])
            continue
        gloss[r["hash"]] = {"zh": zh_gloss.zh_key(r["paras"]), "w": paras, "warn": []}
        done += 1
    save_gloss(gloss)
    print("named %d, left for a reader %d" % (done, len(skipped)))
    for name in skipped[:10]:
        print("  " + name, file=sys.stderr)


def reading(cedict, word: str):
    """One reading for the whole word, or per character when each has only one."""
    if cedict is None:
        return None
    known = cedict.readings.get(word)
    if known and len(known) == 1:
        return next(iter(known))
    out = []
    for ch in word:
        per = cedict.readings.get(ch)
        if not per or len({r.lower() for r in per}) != 1:
            return None      # a character with more than one reading: not safe
        out.append(next(iter(per)))
    return " ".join(out)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("status", "todo", "accept", "names", "ask"):
        q = sub.add_parser(name)
        q.add_argument("--context", help="only these catalogs, comma separated")
        q.add_argument("--only", help="only texts whose id contains this")
        if name == "ask":
            q.add_argument("--limit", type=int, default=0)
            q.add_argument("--batch", type=int, default=20)
            q.add_argument("--workers", type=int, default=4)
            q.add_argument("--estimate", action="store_true")
            q.add_argument("--provider", default="deepseek",
                           choices=("deepseek", "openai", "anthropic"))
            q.add_argument("--model")
            q.add_argument("--base-url", dest="base_url")
            q.add_argument("--key")
            q.add_argument("--allow-peak", action="store_true", dest="allow_peak")
            q.add_argument("--cedict")
        if name == "todo":
            q.add_argument("--limit", type=int, default=0)
            q.add_argument("--skip", type=int, default=0)
        if name == "accept":
            q.add_argument("answer")
        if name == "names":
            q.add_argument("--meaning", help="the same meaning for all of them")
    args = p.parse_args()
    return {"status": cmd_status, "todo": cmd_todo, "accept": cmd_accept,
            "names": cmd_names, "ask": cmd_ask}[args.command](args) or 0


if __name__ == "__main__":
    sys.exit(main())
