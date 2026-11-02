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
import hashlib
import json
import re

from zh_pinyin import han_count, numbered, split_reading

TOKEN = re.compile(r"\{[^}]*\}")

SYSTEM = """You annotate Simplified Chinese game text for a learner of Mandarin.
Split every paragraph into words as a learner's dictionary would: a single character only when it is a word on its own. Names from the list of official names stay one word.
For every item give [s, p, g, h]:
- s: the exact text of the item. The items of a paragraph, joined in order, must give back that paragraph exactly (spaces may be left out).
- p: Hanyu Pinyin with tone marks as spoken in this sentence, syllables written together as in a dictionary (yínháng, xī'ān), neutral tone without a mark, 一 and 不 with their tone change applied. Take care with characters that have several readings.
- g: a short English meaning that fits this sentence, 1 to 4 words. For a name, say what it is, e.g. "(name of a town)".
- h: HSK 3.0 level 1-6, 7 for levels 7-9, 0 when the word is not in HSK (names, game terms).
Punctuation and every {...} token are separate items written as [s] only.
Answer with one JSON object only: {"<id>": [[item, ...], ...]} with one list of items per paragraph, for every id you were given."""


def zh_key(paras) -> str:
    """Short hash of the Chinese paragraphs; a new translation gets a new key."""
    return hashlib.sha1(json.dumps(paras, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def clean_para(para: str) -> str:
    """The paragraph as build uses it: no line breaks."""
    return re.sub(r"\\[nlp]|\n", "", para)


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


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
    return [s, p.strip(), g.strip(), h]


def check_paragraph(para: str, raw_items):
    """Return (items, errors) for one paragraph."""
    if not isinstance(raw_items, list):
        return [], ["paragraph is not a list"]
    items, errors = [], []
    for raw in raw_items:
        item = parse_item(raw)
        if item is None:
            errors.append("bad item %r" % (raw,))
            continue
        s, p, g, _ = item
        if "{" in s or "}" in s:
            if not TOKEN.fullmatch(s):
                errors.append("token not on its own: %r" % s)
        elif han_count(s):
            if not g:
                errors.append("%s: no meaning" % s)
            _, why = split_reading(s, p)
            if why:
                errors.append("%s: %s" % (s, why))
        items.append(item)
    joined = "".join(i[0] for i in items)
    if _squash(joined) != _squash(clean_para(para)):
        errors.append("words do not form the paragraph: %r" % joined)
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
    """Same syllables; a neutral tone (5) on either side matches any tone,
    since CC-CEDICT often gives the citation tone where speech has none."""
    if len(ours) != len(theirs):
        return False
    for a, b in zip(ours, theirs):
        if a[:-1] != b[:-1]:
            return False
        if not ignore_tones and a[-1] != b[-1] and "5" not in (a[-1], b[-1]):
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


def cedict_warnings(paras, cedict):
    out = []
    for items in paras:
        for s, p, _, _ in items:
            if p:
                w = cedict.warn(s, p)
                if w:
                    out.append(w)
    return out
