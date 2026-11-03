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
import re
import sys
import threading
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import llm  # noqa: E402
import zh_gloss  # noqa: E402
from zh_gloss_bin import GlossWriter  # noqa: E402
from zh_text import Encoder, write_table  # noqa: E402

SOURCE = HERE / "dialogue_en.jsonl"
CACHE = HERE / "zh_cache.json"
GLOSS_CACHE = HERE / "zh_gloss_cache.json"
USAGE_LOG = HERE / "api_usage.jsonl"
CEDICT = HERE / "cedict_ts.u8"     # downloaded when needed, not in git
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
    return llm.call(args, system, user)


def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}


# --------------------------------------------------------------------------
# Requests: one routine for translate and gloss
# --------------------------------------------------------------------------

def ask(args, system, group, build, accept, failed):
    """Send one batch. A cut-off or unreadable answer is not sent again as
    is: the batch is split in two. What still fails waits for the next run."""
    user = build(group)
    answer = None
    for attempt in range(3):
        try:
            answer = parse_json(call_api(args, system, user))
            break
        except (llm.Truncated, json.JSONDecodeError, KeyError, IndexError, TypeError):
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if llm.is_fatal(e):
                raise SystemExit("API error %s: %s" % (e.code, e.read()[:300]))
            time.sleep(10 * (attempt + 1))
    else:
        return 0                      # network trouble: the next run tries again
    if not isinstance(answer, dict):
        if len(group) > 1:
            half = len(group) // 2
            return (ask(args, system, group[:half], build, accept, failed)
                    + ask(args, system, group[half:], build, accept, failed))
        failed.append((group[0]["id"], ["no usable answer"]))
        return 0
    return accept(group, answer)


def run(args, command, system, todo, build, accept, failed):
    total = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = [pool.submit(ask, args, system, g, build, accept, failed) for g in todo]
        for n, f in enumerate(as_completed(jobs), 1):
            total += f.result()
            print("\r%d/%d requests, %d texts done" % (n, len(todo), total), end="", flush=True)
    print()
    for text_id, errors in failed[:20]:
        print("rejected %s: %s" % (text_id, "; ".join(errors[:3])))
    if failed:
        print("%d texts rejected; run again to retry only those." % len(failed))
    print("use: " + llm.USAGE.summary())
    llm.log_usage(USAGE_LOG, command, args, total)
    return total


# Tokens per English character (input, output), measured with deepseek-flash.
EST = {"translate": (0.65, 0.26), "gloss": (0.98, 1.93)}


def estimate(command, rows, args):
    chars = sum(len(r["en"]) for r in rows)
    tin, tout = EST[command]
    miss, _, out = llm.PRICES.get(args.model or llm.DEEPSEEK_MODEL, (0.30, 0.006, 1.20))
    cost = (chars * tin * miss + chars * tout * out) / 1e6
    print("estimate: %d texts, about %.0fk input and %.0fk output tokens, $%.2f off-peak ($%.2f peak)"
          % (len(rows), chars * tin / 1e3, chars * tout / 1e3, cost / 2, cost))


def load_rows(only=None):
    rows = [json.loads(l) for l in SOURCE.read_text(encoding="utf-8").splitlines() if l.strip()]
    if only:
        wanted = {o.strip().lower() for o in only.split(",")}
        rows = [r for r in rows if r["context"].lower() in wanted]
    return rows


def load_cache() -> dict:
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def batches(rows, size: int, chars: int):
    """Texts of several places may share a request; each item says where it is."""
    group, n = [], 0
    for r in rows:
        if group and (len(group) >= size or n + len(r["en"]) > chars):
            yield group
            group, n = [], 0
        group.append(r)
        n += len(r["en"])
    if group:
        yield group


def glossary_for(group, glossary: dict) -> dict:
    text = " ".join(r["en"] for r in group).upper()
    return {k: v for k, v in glossary.items() if k.upper() in text}


def save(path: Path, data: dict):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), indent=0), encoding="utf-8")
    tmp.replace(path)


def cmd_translate(args):
    cache = load_cache()
    lock = threading.Lock()
    glossary = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    rows = [r for r in load_rows(args.only) if r["hash"] not in cache]
    if args.limit:
        rows = rows[:args.limit]
    todo = list(batches(rows, args.batch, 8000))
    print("%d texts to translate in %d requests" % (len(rows), len(todo)))
    if args.estimate:
        estimate("translate", rows, args)
        return
    if not todo:
        return
    llm.resolve(args)
    system = SYSTEM.format(level=LEVELS[args.level])
    failed = []

    def build(group):
        items = [{"id": str(n + 1), "where": r["context"], "paragraphs": split_paragraphs(r["en"])[0]}
                 for n, r in enumerate(group)]
        return ("Glossary (English -> official Chinese):\n"
                + json.dumps(glossary_for(group, glossary), ensure_ascii=False, separators=(",", ":"))
                + "\n\nTexts:\n" + json.dumps(items, ensure_ascii=False, separators=(",", ":")))

    def accept(group, answer):
        done = 0
        with lock:
            for n, r in enumerate(group):
                paras, _ = split_paragraphs(r["en"])
                zh = answer.get(str(n + 1))
                if (isinstance(zh, list) and len(zh) == len(paras) and all(isinstance(p, str) for p in zh)
                        and tokens(" ".join(zh)) == tokens(" ".join(paras))
                        and set(re.findall(r"\{[^}]*\}", " ".join(zh))) <= set(re.findall(r"\{[^}]*\}", r["en"]))):
                    cache[r["hash"]] = {"id": r["id"], "zh": zh}
                    done += 1
                else:
                    failed.append((r["id"], ["paragraphs or {tokens} do not match"]))
            save(CACHE, cache)
        return done

    run(args, "translate", system, todo, build, accept, failed)
    print("'gloss' adds the words; 'build' makes zh_dialog.bin.")


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
    rows = [r for r in load_rows(args.only) if r["hash"] in cache
            and gloss.get(r["hash"], {}).get("zh") != zh_gloss.zh_key(cache[r["hash"]]["zh"])]
    if args.limit:
        rows = rows[:args.limit]
    todo = list(batches(rows, args.batch, 4000))
    print("%d texts to annotate in %d requests" % (len(rows), len(todo)))
    if args.estimate:
        estimate("gloss", rows, args)
        return
    if not todo:
        return
    llm.resolve(args)
    cedict = zh_gloss.Cedict(args.cedict) if args.cedict else zh_gloss.load_cedict(CEDICT)
    failed = []

    def build(group):
        items = [{"id": str(n + 1), "en": split_paragraphs(r["en"])[0], "zh": cache[r["hash"]]["zh"]}
                 for n, r in enumerate(group)]
        return ("Official names in these texts (Chinese -> English):\n"
                + json.dumps(names_for(group, cache, glossary), ensure_ascii=False, separators=(",", ":"))
                + "\n\nTexts:\n" + json.dumps(items, ensure_ascii=False, separators=(",", ":")))

    def accept(group, answer):
        done = 0
        with lock:
            for n, r in enumerate(group):
                zh = cache[r["hash"]]["zh"]
                paras, errors = zh_gloss.check_answer(zh, answer.get(str(n + 1)))
                if errors:
                    failed.append((r["id"], errors))
                    continue
                warn = zh_gloss.apply_cedict(paras, cedict) if cedict else []
                gloss[r["hash"]] = {"zh": zh_gloss.zh_key(zh), "w": paras, "warn": warn}
                done += 1
            save(GLOSS_CACHE, gloss)
        return done

    run(args, "gloss", zh_gloss.SYSTEM, todo, build, accept, failed)


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
    # The built-in Chinese texts (catalog/zh_cn in the repo): the game looks
    # these up by the hash of the Chinese it has compiled in, so they are not
    # in the table, only in the word data. See tools/catalog_texts.py.
    catalog, catalog_gloss, from_catalog = HERE / "zh_catalog.jsonl", HERE / "zh_catalog_gloss.json", 0
    if catalog.exists() and catalog_gloss.exists():
        cg = json.loads(catalog_gloss.read_text(encoding="utf-8"))
        for line in catalog.open(encoding="utf-8"):
            r = json.loads(line)
            g = cg.get(r["hash"])
            if g and g["zh"] == zh_gloss.zh_key(zh_gloss.paragraphs(r["zh"])):
                writer.add(int(r["hash"], 16), r["context"], g["w"])
                from_catalog += 1

    out = Path(args.out)
    write_table(table, out)
    print("%s: %d texts (%d skipped)" % (out, len(table), problems))
    gloss_out = out.with_name("zh_gloss.bin")
    gloss_out.write_bytes(writer.to_bytes())
    print("%s: %d texts (%d built in), %d words (%d out of date, run 'gloss')"
          % (gloss_out, len(writer.texts), from_catalog, len(writer.words), stale))
    if missing_chars:
        print("characters without a glyph (left out):", "".join(sorted(missing_chars)))


def cmd_review(args):
    cache = load_cache()
    gloss = load_gloss_cache()
    cedict = zh_gloss.Cedict(args.cedict if args.cedict else CEDICT) if (args.cedict or CEDICT.exists()) else None
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
    def api_options(p, batch):
        p.add_argument("--provider", choices=["deepseek", "openai", "anthropic"], default="deepseek")
        p.add_argument("--model", help="default: deepseek-flash (deepseek), gpt-4o, claude-sonnet-5-5")
        p.add_argument("--base-url", help="OpenAI-compatible endpoint, e.g. https://api.siliconflow.cn/v1")
        p.add_argument("--key", help="default: from DEEPSEEK_API_KEY, OPENAI_API_KEY or ANTHROPIC_API_KEY")
        p.add_argument("--only", help="comma-separated contexts, e.g. birch_speech,LittlerootTown")
        p.add_argument("--limit", type=int)
        p.add_argument("--batch", type=int, default=batch)
        p.add_argument("--workers", type=int, default=4)
        p.add_argument("--estimate", action="store_true", help="only show what it would cost")
        p.add_argument("--allow-peak", action="store_true", help="DeepSeek: do not wait for off-peak hours")
    t = sub.add_parser("translate")
    api_options(t, 40)
    t.add_argument("--level", choices=sorted(LEVELS), default="natural")
    g = sub.add_parser("gloss", help="words, pinyin and meaning per translated text")
    api_options(g, 16)
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
