"""Word data for the in-game dictionary (phase 1 of docs/PLAN-woordenboek.md).

Per translated text the language model returns the words of every paragraph
with pinyin, a short meaning and an HSK level. This module checks those answers,
keeps them in zh_gloss_cache.json and writes zh_gloss.bin.

Item format in the cache and in the model answer: [s, p, g, h]
  s  text of the item (word, punctuation or one {...} token)
  p  pinyin with tone marks ("" for anything without Chinese characters)
  g  short English meaning ("" when p is "")
  h  HSK level: 1-6, 7 for levels 7-9, 0 for none
"""
import gzip
import hashlib
import json
import re
import urllib.request

from zh_pinyin import han_count, numbered, split_reading, to_marks

TOKEN = re.compile(r"\{[^}]*\}")

SYSTEM = """You annotate Simplified Chinese game text for a learner of Mandarin.
Split every paragraph into words as a learner's dictionary would: a single character only when it is a word on its own. Names from the list of official names stay one word.
List only the words that contain Chinese characters, in order, each as [s,p,g,h]. Leave out punctuation, spaces and {...} tokens: the program fills those in.
- s: the word exactly as written in the paragraph.
- p: Hanyu Pinyin with tone marks as spoken in this sentence, syllables written together as in a dictionary (yínháng, xī'ān), neutral tone without a mark, 一 and 不 with their tone change applied. Take care with characters that have several readings.
- g: a short English meaning that fits this sentence, 1 to 3 words. For a name, say what it is, e.g. "(name of a town)".
- h: HSK 3.0 level 1-6, 7 for levels 7-9, 0 when the word is not in HSK (names, game terms).
Answer with one compact JSON object only, no spaces or line breaks: {"<id>":[[[s,p,g,h],...],...]} with one list of words per paragraph, for every id you were given."""


def zh_key(paras) -> str:
    """Short hash of the Chinese paragraphs; a new translation gets a new key."""
    return hashlib.sha1(json.dumps(paras, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def clean_para(para: str) -> str:
    """The paragraph as build uses it: no line breaks."""
    return re.sub(r"\\[nlp]|\n", "", para)


def paragraphs(zh: str):
    """A text as the game shows it, one entry per paragraph (\\p)."""
    return [p for p in (clean_para(part) for part in re.split(r"\\p", zh)) if p]


def parse_item(raw):
    """Model item (list or dict) -> [s, p, g, h], or None when unusable."""
    if isinstance(raw, dict):
        raw = [raw.get("s"), raw.get("p", ""), raw.get("g", ""), raw.get("h", 0)]
    if not isinstance(raw, list) or not raw or not isinstance(raw[0], str):
        return None
    s = raw[0]
    p = raw[1] if len(raw) > 1 and isinstance(raw[1], str) else ""
    g = raw[2] if len(raw) > 2 and isinstance(raw[2], str) else ""
    h = raw[3] if len(raw) > 3 else 0
    try:
        h = int(h)
    except (TypeError, ValueError):
        h = 0
    if not 0 <= h <= 7:
        h = 0
    if not han_count(s):
        p, g, h = "", "", 0     # punctuation, tokens, digits: not a word to look up
    return [s, to_marks(p.strip()), g.strip(), h]


GAP = re.compile(r"\{[^}]*\}|[^{\s]+")


def _gap_items(gap: str):
    """Punctuation and {...} tokens between two words, as items without pinyin."""
    return [[piece, "", "", 0] for piece in GAP.findall(gap)]


def check_paragraph(para: str, raw_items):
    """Return (items, errors) for one paragraph.

    The answer may list only the words with Chinese characters; they are
    matched in order against the paragraph, and what lies between them
    (punctuation, {...} tokens) is filled in here. Items without Chinese
    characters in the answer are ignored, so a full answer works too."""
    if not isinstance(raw_items, list):
        return [], ["paragraph is not a list"]
    text = clean_para(para)
    items, errors, pos = [], [], 0
    for raw in raw_items:
        item = parse_item(raw)
        if item is None:
            errors.append("bad item %r" % (raw,))
            continue
        s, p, g, _ = item
        if not han_count(s):
            continue
        if "{" in s or "}" in s:
            errors.append("token not on its own: %r" % s)
            continue
        at = text.find(s, pos)
        if at < 0:
            errors.append("%s: not found in order in the paragraph" % s)
            continue
        gap = text[pos:at]
        if han_count(gap):
            errors.append("characters without a word: %r" % gap.strip())
        items += _gap_items(gap)
        if not g:
            errors.append("%s: no meaning" % s)
        _, why = split_reading(s, p)
        if why:
            errors.append("%s: %s" % (s, why))
        items.append(item)
        pos = at + len(s)
    rest = text[pos:]
    if han_count(rest):
        errors.append("characters without a word: %r" % rest.strip())
    items += _gap_items(rest)
    return items, errors


def check_answer(zh_paras, answer):
    """Check the model answer for one text. Return (paragraph items, errors)."""
    if not isinstance(answer, list) or len(answer) != len(zh_paras):
        return None, ["expected %d paragraphs" % len(zh_paras)]
    out, errors = [], []
    for para, raw_items in zip(zh_paras, answer):
        items, errs = check_paragraph(para, raw_items)
        out.append(items)
        errors += errs
    return out, errors


# --------------------------------------------------------------------------
# Optional check against CC-CEDICT (warnings only)
# --------------------------------------------------------------------------

def _same_reading(ours, theirs, ignore_tones=False) -> bool:
    """Same syllables. After the first syllable a neutral tone (5) on either
    side matches any tone: CC-CEDICT often gives the citation tone where speech
    has none (wài mian). The first syllable is almost never neutral."""
    if len(ours) != len(theirs):
        return False
    for n, (a, b) in enumerate(zip(ours, theirs)):
        if a[:-1] != b[:-1]:
            return False
        if not ignore_tones and a[-1] != b[-1] and not (n > 0 and "5" in (a[-1], b[-1])):
            return False
    return True


class Cedict:
    """Readings per simplified word from a cedict_ts.u8 file."""

    LINE = re.compile(r"^\S+ (\S+) \[([^\]]*)\]")

    def __init__(self, path):
        self.readings = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = self.LINE.match(line)
                if m:
                    reading = m.group(2).lower().replace("u:", "ü")
                    self.readings.setdefault(m.group(1), set()).add(reading)

    def warn(self, word: str, pinyin: str):
        """A warning when CC-CEDICT knows the word but not this reading."""
        known = self.readings.get(word)
        units, why = split_reading(word, pinyin)
        if not known or why:
            return None
        ours = numbered(units).split()
        sandhi = "一" in word or "不" in word    # tone change: compare without tones
        if any(_same_reading(ours, r.split(), sandhi) for r in known):
            return None
        return "%s %s: CC-CEDICT has %s" % (word, pinyin, " / ".join(sorted(known)))


def _join_numbered(units) -> str:
    out = ""
    for n, (syl, tone) in enumerate(units):
        if n and syl[0] in "aoe":
            out += "'"
        out += syl + (str(tone) if tone else "")
    return out


def fix_tones(cedict, word: str, pinyin: str):
    """Tones repaired from CC-CEDICT, for free: only when CC-CEDICT has exactly
    one reading with the same syllables. A neutral tone after the first
    syllable is kept (spoken), and words with 一 or 不 (tone change) are left
    alone. Returns the new pinyin or None."""
    if word[:1] in "一不" or "一" in word or "不" in word:
        return None
    units, why = split_reading(word, pinyin)
    known = cedict.readings.get(word)
    if not known or why or any(syl == "r" for syl, _ in units):
        return None
    same = [r.split() for r in known
            if len(r.split()) == len(units) and all(a[:-1] == b for a, (b, _) in zip(r.split(), units))]
    if len(same) != 1:
        return None
    fixed = []
    for n, ((syl, tone), theirs) in enumerate(zip(units, same[0])):
        t = int(theirs[-1])
        fixed.append((syl, tone if (n > 0 and tone == 0) or t == 5 else t))
    if fixed == list(units):
        return None
    marked = to_marks(_join_numbered(fixed))
    return marked[0].upper() + marked[1:] if pinyin[:1].isupper() else marked


fix_first_tone = fix_tones     # older name


def apply_cedict(paras, cedict):
    """Fix what CC-CEDICT can fix for free, return warnings for the rest."""
    out = []
    for items in paras:
        for item in items:
            if item[1]:
                fixed = fix_tones(cedict, item[0], item[1])
                if fixed:
                    item[1] = fixed
                w = cedict.warn(item[0], item[1])
                if w:
                    out.append(w)
    return out


CEDICT_URL = "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz"


def load_cedict(path):
    """CC-CEDICT from path; downloaded once when missing (free, no tokens).
    Returns None when it cannot be had."""
    if not path.exists():
        try:
            with urllib.request.urlopen(CEDICT_URL, timeout=60) as resp:
                path.write_bytes(gzip.decompress(resp.read()))
            print("downloaded CC-CEDICT to %s" % path)
        except OSError as e:
            print("no CC-CEDICT (%s); continuing without" % e)
            return None
    return Cedict(path)


def cedict_warnings(paras, cedict):
    out = []
    for items in paras:
        for s, p, _, _ in items:
            if p:
                w = cedict.warn(s, p)
                if w:
                    out.append(w)
    return out
