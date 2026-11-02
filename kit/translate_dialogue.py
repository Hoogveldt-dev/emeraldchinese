#!/usr/bin/env python3
"""Vertaal de dialogen van Pokémon Emerald 3DS (Chinese build) naar Mandarijn.

Stappen:
  1. translate  stuurt de Engelse teksten in porties naar een taalmodel-API en
                bewaart de Chinese vertaling in zh_cache.json (hervatbaar).
  2. build      maakt van de cache het bestand zh_dialog.bin voor op de SD-kaart:
                sdmc:/3ds/emerald3ds/zh_dialog.bin  (in Citra/Azahar: de map
                sdmc van de emulator, zie LEESMIJ).
  3. gloss      laat het taalmodel per vertaalde tekst de woorden bepalen, met
                pinyin, korte betekenis en HSK-niveau (zh_gloss_cache.json,
                hervatbaar). build schrijft daarna ook zh_gloss.bin.
  4. review     toont die woorden voor een paar contexten, om na te lopen.
  5. status     laat zien hoeveel er vertaald is.

Voorbeelden:
  python translate_dialogue.py translate --provider anthropic --only birch_speech,LittlerootTown
  python translate_dialogue.py translate --provider openai --base-url https://api.deepseek.com --model deepseek-chat
  python translate_dialogue.py gloss --only birch_speech,LittlerootTown
  python translate_dialogue.py review --only birch_speech
  python translate_dialogue.py build

API-sleutels komen uit de omgeving: ANTHROPIC_API_KEY of OPENAI_API_KEY
(of --key). Alleen de standaardbibliotheek van Python 3.9+ is nodig.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import zh_gloss  # noqa: E402
from zh_gloss_bin import GlossWriter  # noqa: E402
from zh_text import Encoder, write_table  # noqa: E402

SOURCE = HERE / "dialogue_en.jsonl"
CACHE = HERE / "zh_cache.json"
GLOSS_CACHE = HERE / "zh_gloss_cache.json"
GLOSSARY = HERE / "glossary.json"
WIDTHS = HERE / "font_widths.json"

BOX_WIDTH = 208          # message box: 27 tiles = 216 px, a little margin
CJK_WIDTH = 12
MAX_BYTES = 900          # gStringVar4 holds 1000 bytes
PLACEHOLDER_WIDTH = {"PLAYER": 42, "RIVAL": 24, "STR_VAR_1": 60, "STR_VAR_2": 60, "STR_VAR_3": 60,
                     "KUN": 0, "DYNAMIC": 42, "PKMN": 12, "POKEBLOCK": 30, "AQUA": 24, "MAGMA": 24,
                     "ARCHIE": 36, "MAXIE": 36, "KYOGRE": 36, "GROUDON": 36, "VERSION": 36}
# Tokens that carry content and must survive translation.
REQUIRED = re.compile(r"^(PLAYER|RIVAL|STR_VAR_\d|DYNAMIC|B_\w+|AQUA|MAGMA|ARCHIE|MAXIE|KYOGRE|GROUDON|VERSION)\b")
NO_LINE_START = set("，。！？、；：）」』】》…～・,.!?;:)'\"”’\u2014")

LEVELS = {
    "natural": "Write natural, idiomatic Simplified Chinese (Mainland usage), in the style of the official Chinese "
               "Pokémon games: clear, friendly, everyday Mandarin.",
    "simple": "Write simple, clear Simplified Chinese for a learner around HSK 3-4: prefer common words and short "
              "sentences, avoid chengyu and rare characters, but keep the meaning, tone and personality.",
}

SYSTEM = """You translate the in-game text of Pokémon Emerald into Simplified Chinese for a player who learns Mandarin by immersion (comprehensible input).
{level}
Rules:
- Use the official Chinese names from the glossary for Pokémon, moves, items, places, people and game terms.
- Keep every {{...}} token exactly as written (e.g. {{PLAYER}}, {{STR_VAR_1}}, {{COLOR BLUE}}, {{PAUSE 30}}, {{PLAY_SE SE_DING_DONG}}); place it where it belongs in the Chinese sentence. {{KUN}} may stay at the end of a name.
- Each text is a list of paragraphs (each paragraph is one text box). Return exactly the same number of paragraphs, in order.
- Use Chinese punctuation (，。！？……「」). Do not add pinyin, notes or English.
- Write no line breaks; the game wraps the lines itself.
Answer with one JSON object only: {{"<id>": ["paragraph", ...], ...}} for every id you were given."""


# --------------------------------------------------------------------------
# Text shape
# --------------------------------------------------------------------------

def split_paragraphs(en: str):
    """English pret text -> (paragraphs as plain lines, ends_with_p, kind_end)."""
    body = en[:-1] if en.endswith("$") else en
    trailing_p = body.endswith("\\p")
    if trailing_p:
        body = body[:-2]
    paras = [re.sub(r"\\[nl]", " ", p).strip() for p in body.split("\\p")]
    return paras, trailing_p


class Measure:
    def __init__(self, enc: Encoder):
        self.enc = enc
        self.widths = json.loads(WIDTHS.read_text())

    def items(self, text: str):
        i = 0
        while i < len(text):
            if text[i] == "{":
                j = text.index("}", i)
                yield text[i:j + 1]
                i = j + 1
            else:
                yield text[i]
                i += 1

    def width(self, item: str) -> int:
        if item.startswith("{"):
            return PLACEHOLDER_WIDTH.get(item[1:-1].split()[0], 0)
        if ord(item) > 0x2000:
            return CJK_WIDTH
        code = self.enc.chars.get(item)
        return self.widths[code[0]] if code and len(code) == 1 and code[0] < len(self.widths) else 6

    def wrap(self, para: str, limit: int):
        lines, cur, w = [], [], 0
        for item in self.items(para):
            iw = self.width(item)
            if cur and w + iw > limit:
                # no closing punctuation at the start of a line
                if item in NO_LINE_START and len(cur) > 1:
                    moved = cur.pop()
                    lines.append(cur)
                    cur, w = [moved], self.width(moved)
                else:
                    lines.append(cur)
                    cur, w = [], 0
                if not cur and item == " ":
                    continue
            cur.append(item)
            w += iw
        if cur:
            lines.append(cur)
        return ["".join(line).strip() for line in lines if "".join(line).strip()]


def assemble(paras, trailing_p: bool, kind: str, measure: Measure, limit: int) -> str:
    out = []
    for p in paras:
        lines = measure.wrap(p, limit)
        text = ""
        for n, line in enumerate(lines):
            text += line if n == 0 else ("\\n" if n == 1 else "\\l") + line
        out.append(text)
    text = "\\p".join(out)
    if trailing_p:
        text += "\\p"
    return text + ("$" if kind == "box" else "")


def tokens(text: str):
    return sorted(t for t in re.findall(r"\{([^}]*)\}", text) if REQUIRED.match(t))


def c_limit(en: str, measure: Measure) -> int:
    lines = re.split(r"\\[nlp]", en.rstrip("$"))
    return max(120, max(sum(measure.width(i) for i in measure.items(l)) for l in lines))


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------

def call_api(args, system: str, user: str) -> str:
    if args.provider == "anthropic":
        url = (args.base_url or "https://api.anthropic.com") + "/v1/messages"
        body = {"model": args.model or "claude-sonnet-5-5", "max_tokens": 8000, "system": system,
                "messages": [{"role": "user", "content": user}]}
        headers = {"x-api-key": args.key or os.environ.get("ANTHROPIC_API_KEY", ""),
                   "anthropic-version": "2023-06-01", "content-type": "application/json"}
    else:
        url = (args.base_url or "https://api.openai.com").rstrip("/") + "/v1/chat/completions"
        body = {"model": args.model or "gpt-4o", "temperature": 0.3,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        headers = {"authorization": "Bearer " + (args.key or os.environ.get("OPENAI_API_KEY", "")),
                   "content-type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    if args.provider == "anthropic":
        return "".join(part.get("text", "") for part in data["content"])
    return data["choices"][0]["message"]["content"]


def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def load_rows(only=None):
    rows = [json.loads(l) for l in SOURCE.read_text(encoding="utf-8").splitlines() if l.strip()]
    if only:
        wanted = {o.strip().lower() for o in only.split(",")}
        rows = [r for r in rows if r["context"].lower() in wanted]
    return rows


def load_cache() -> dict:
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def batches(rows, size: int, chars: int):
    group, n = [], 0
    for r in rows:
        if group and (len(group) >= size or n + len(r["en"]) > chars or group[-1]["context"] != r["context"]):
            yield group
            group, n = [], 0
        group.append(r)
        n += len(r["en"])
    if group:
        yield group


def glossary_for(group, glossary: dict) -> dict:
    text = " ".join(r["en"] for r in group).upper()
    return {k: v for k, v in glossary.items() if k.upper() in text}


def cmd_translate(args):
    cache = load_cache()
    lock = threading.Lock()
    glossary = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    rows = [r for r in load_rows(args.only) if r["hash"] not in cache]
    if args.limit:
        rows = rows[:args.limit]
    system = SYSTEM.format(level=LEVELS[args.level])
    todo = list(batches(rows, args.batch, 6000))
    print("%d texts to translate in %d requests" % (len(rows), len(todo)))
    if not todo:
        return

    def work(group):
        items = []
        for r in group:
            paras, _ = split_paragraphs(r["en"])
            items.append({"id": r["hash"], "where": r["context"], "paragraphs": paras})
        user = ("Glossary (English -> official Chinese):\n" + json.dumps(glossary_for(group, glossary), ensure_ascii=False)
                + "\n\nTexts:\n" + json.dumps(items, ensure_ascii=False))
        for attempt in range(4):
            try:
                answer = parse_json(call_api(args, system, user))
                break
            except (urllib.error.URLError, json.JSONDecodeError, KeyError, TimeoutError) as e:
                if isinstance(e, urllib.error.HTTPError) and e.code in (400, 401, 403):
                    raise SystemExit("API error %s: %s" % (e.code, e.read()[:300]))
                time.sleep(5 * (attempt + 1))
        else:
            return 0
        done = 0
        with lock:
            for r, item in zip(group, items):
                zh = answer.get(r["hash"])
                if (isinstance(zh, list) and len(zh) == len(item["paragraphs"])
                        and tokens(" ".join(zh)) == tokens(" ".join(item["paragraphs"]))):
                    cache[r["hash"]] = {"id": r["id"], "zh": zh}
                    done += 1
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
        return done

    total = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for n, f in enumerate(as_completed([pool.submit(work, g) for g in todo]), 1):
            total += f.result()
            print("\r%d/%d requests, %d texts translated" % (n, len(todo), total), end="", flush=True)
    print("\nRun again to retry what failed; 'build' makes zh_dialog.bin.")


def load_gloss_cache() -> dict:
    return json.loads(GLOSS_CACHE.read_text(encoding="utf-8")) if GLOSS_CACHE.exists() else {}


def names_for(group, cache, glossary: dict) -> dict:
    """Official names (Chinese -> English) that occur in the Chinese of these texts."""
    text = " ".join(" ".join(cache[r["hash"]]["zh"]) for r in group)
    return {zh: en for en, zh in glossary.items() if zh and zh in text}


def cmd_gloss(args):
    cache = load_cache()
    gloss = load_gloss_cache()
    lock = threading.Lock()
    glossary = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    cedict = zh_gloss.Cedict(args.cedict) if args.cedict else None
    rows = [r for r in load_rows(args.only) if r["hash"] in cache
            and gloss.get(r["hash"], {}).get("zh") != zh_gloss.zh_key(cache[r["hash"]]["zh"])]
    if args.limit:
        rows = rows[:args.limit]
    todo = list(batches(rows, args.batch, 2500))
    print("%d texts to annotate in %d requests" % (len(rows), len(todo)))
    if not todo:
        return
    failed = []

    def work(group):
        items = []
        for r in group:
            paras, _ = split_paragraphs(r["en"])
            items.append({"id": r["hash"], "en": paras, "zh": cache[r["hash"]]["zh"]})
        user = ("Official names in these texts (Chinese -> English):\n"
                + json.dumps(names_for(group, cache, glossary), ensure_ascii=False)
                + "\n\nTexts:\n" + json.dumps(items, ensure_ascii=False))
        for attempt in range(4):
            try:
                answer = parse_json(call_api(args, zh_gloss.SYSTEM, user))
                break
            except (urllib.error.URLError, json.JSONDecodeError, KeyError, TimeoutError) as e:
                if isinstance(e, urllib.error.HTTPError) and e.code in (400, 401, 403):
                    raise SystemExit("API error %s: %s" % (e.code, e.read()[:300]))
                time.sleep(5 * (attempt + 1))
        else:
            return 0
        done = 0
        with lock:
            for r, item in zip(group, items):
                paras, errors = zh_gloss.check_answer(item["zh"], answer.get(r["hash"]))
                if errors:
                    failed.append((r["id"], errors))
                    continue
                warn = zh_gloss.cedict_warnings(paras, cedict) if cedict else []
                gloss[r["hash"]] = {"zh": zh_gloss.zh_key(item["zh"]), "w": paras, "warn": warn}
                done += 1
            GLOSS_CACHE.write_text(json.dumps(gloss, ensure_ascii=False, indent=0), encoding="utf-8")
        return done

    total = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for n, f in enumerate(as_completed([pool.submit(work, g) for g in todo]), 1):
            total += f.result()
            print("\r%d/%d requests, %d texts annotated" % (n, len(todo), total), end="", flush=True)
    print()
    for text_id, errors in failed[:20]:
        print("rejected %s: %s" % (text_id, "; ".join(errors[:3])))
    if failed:
        print("%d texts rejected; run again to retry them." % len(failed))


def cmd_build(args):
    enc = Encoder(HERE / "charmap.txt", HERE / "cjk_table.json")
    measure = Measure(enc)
    cache = load_cache()
    rows = {r["hash"]: r for r in load_rows()}
    table, problems, missing_chars = {}, 0, set()
    gloss = load_gloss_cache()
    writer = GlossWriter(enc, lambda t: bool(REQUIRED.match(t)))
    stale = 0
    for h, entry in cache.items():
        r = rows.get(h)
        if not r:
            continue
        _, trailing_p = split_paragraphs(r["en"])
        paras = []
        for p in entry["zh"]:
            p = re.sub(r"\\[nlp]|\n", "", p)
            kept = []
            for item in measure.items(p):
                if item.startswith("{") or enc.has(item):
                    kept.append(item)
                else:
                    missing_chars.add(item)
            paras.append("".join(kept))
        limit = BOX_WIDTH if r["kind"] == "box" else c_limit(r["en"], measure)
        text = assemble(paras, trailing_p, r["kind"], measure, limit)
        try:
            data = enc.encode(text, terminate=(r["kind"] != "box"))
        except ValueError as e:
            problems += 1
            continue
        if 0xFF not in data or len(data) > MAX_BYTES:
            problems += 1
            continue
        table[int(h, 16)] = data[:data.index(0xFF) + 1]
        g = gloss.get(h)
        if g and g["zh"] == zh_gloss.zh_key(entry["zh"]):
            writer.add(int(h, 16), r["context"], g["w"])
        elif g:
            stale += 1
    out = Path(args.out)
    write_table(table, out)
    print("%s: %d texts (%d skipped)" % (out, len(table), problems))
    gloss_out = out.with_name("zh_gloss.bin")
    gloss_out.write_bytes(writer.to_bytes())
    print("%s: %d texts, %d words (%d out of date, run 'gloss')"
          % (gloss_out, len(writer.texts), len(writer.words), stale))
    if missing_chars:
        print("characters without a glyph (left out):", "".join(sorted(missing_chars)))


def cmd_review(args):
    cache = load_cache()
    gloss = load_gloss_cache()
    cedict = zh_gloss.Cedict(args.cedict) if args.cedict else None
    for r in load_rows(args.only):
        entry, g = cache.get(r["hash"]), gloss.get(r["hash"])
        print("== %s  %s" % (r["context"], r["id"]))
        if not entry:
            print("   (not translated)")
            continue
        print("   EN: " + " / ".join(split_paragraphs(r["en"])[0]))
        print("   ZH: " + " / ".join(entry["zh"]))
        if not g:
            print("   (no words yet)")
            continue
        if g["zh"] != zh_gloss.zh_key(entry["zh"]):
            print("   (words out of date, run 'gloss')")
        for items in g["w"]:
            for s_, p_, g_, h_ in items:
                if p_:
                    print("   %-8s %-18s %-28s %s" % (s_, p_, g_, "HSK %d" % h_ if h_ else "-"))
            print("   --")
        warn = zh_gloss.cedict_warnings(g["w"], cedict) if cedict else g.get("warn", [])
        for w in warn:
            print("   ! " + w)


def cmd_status(args):
    rows = load_rows()
    cache = load_cache()
    per = {}
    for r in rows:
        t = per.setdefault(r["context"], [0, 0])
        t[0] += 1
        t[1] += r["hash"] in cache
    done = sum(v[1] for v in per.values())
    for ctx, (n, d) in sorted(per.items()):
        if args.verbose or 0 < d < n:
            print("%-40s %4d / %d" % (ctx, d, n))
    print("total: %d / %d texts translated" % (done, len(rows)))
    cache, gloss = load_cache(), load_gloss_cache()
    current = sum(1 for h, g in gloss.items() if h in cache and g["zh"] == zh_gloss.zh_key(cache[h]["zh"]))
    print("words: %d / %d translated texts annotated" % (current, done))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("translate")
    t.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    t.add_argument("--model")
    t.add_argument("--base-url", help="OpenAI-compatible endpoint, e.g. https://api.deepseek.com")
    t.add_argument("--key")
    t.add_argument("--level", choices=sorted(LEVELS), default="natural")
    t.add_argument("--only", help="comma-separated contexts (map names, text files), e.g. birch_speech,LittlerootTown")
    t.add_argument("--limit", type=int)
    t.add_argument("--batch", type=int, default=30)
    t.add_argument("--workers", type=int, default=4)
    g = sub.add_parser("gloss", help="words, pinyin and meaning per translated text")
    g.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    g.add_argument("--model")
    g.add_argument("--base-url")
    g.add_argument("--key")
    g.add_argument("--only")
    g.add_argument("--limit", type=int)
    g.add_argument("--batch", type=int, default=10)
    g.add_argument("--workers", type=int, default=4)
    g.add_argument("--cedict", help="path to cedict_ts.u8: warn about readings it does not know")
    r = sub.add_parser("review", help="show the words of some texts to check them by hand")
    r.add_argument("--only", required=True)
    r.add_argument("--cedict")
    b = sub.add_parser("build")
    b.add_argument("--out", default=str(HERE / "zh_dialog.bin"))
    s = sub.add_parser("status")
    s.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    {"translate": cmd_translate, "gloss": cmd_gloss, "review": cmd_review,
     "build": cmd_build, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    main()
