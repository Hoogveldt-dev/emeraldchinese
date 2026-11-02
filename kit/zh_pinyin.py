"""Pinyin helpers for the gloss step: split a reading into syllables and check
that it fits the characters of a word.

The syllable pattern is deliberately a little permissive (initial + final);
it is used to count syllables, not to prove that a syllable exists.
"""
import re
import unicodedata

# toned vowel -> (base vowel, tone)
_TONES = {}
for _base, _marks in (("a", "āáǎà"), ("e", "ēéěè"), ("i", "īíǐì"), ("o", "ōóǒò"),
                      ("u", "ūúǔù"), ("ü", "ǖǘǚǜ")):
    for _n, _ch in enumerate(_marks, 1):
        _TONES[_ch] = (_base, _n)
# syllabic n and m (interjections)
_TONES.update({"ń": ("n", 2), "ň": ("n", 3), "ǹ": ("n", 4), "ḿ": ("m", 2)})

_INITIAL = r"(?:zh|ch|sh|[bpmfdtnlgkhjqxrzcsyw])?"
_FINAL = (r"(?:iang|iong|uang|ueng|ang|eng|ing|ong|ian|iao|uai|uan|üan|"
          r"ai|ei|ao|ou|an|en|in|un|ün|ia|ie|iu|ua|uo|ui|ue|üe|a|o|e|i|u|ü)")
# "er" has no initial: "zher" is erhua (zhe + r), not zh + er.
SYLLABLE = re.compile(r"^(?:%s%s|er)$" % (_INITIAL, _FINAL))
# interjections, only accepted as a whole chunk
INTERJECTIONS = {"hm", "hng", "m", "n", "ng"}
SEPARATORS = " '’-·"


def is_han(ch: str) -> bool:
    o = ord(ch)
    return 0x3400 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF or 0x20000 <= o <= 0x3134F


def han_count(text: str) -> int:
    return sum(1 for c in text if is_han(c))


def _letters(chunk: str):
    """'yínháng' -> ('yinhang', [0, 2, 0, 0, 0, 0, 0])  (tone per letter, 0 = none)."""
    letters, tones = [], []
    for ch in unicodedata.normalize("NFC", chunk.lower().replace("u:", "ü").replace("v", "ü")):
        if ch in _TONES:
            base, tone = _TONES[ch]
        else:
            base, tone = ch, 0
        letters.append(base)
        tones.append(tone)
    return "".join(letters), tones


def _segment(letters: str, tones, erhua: bool):
    """All ways to cut one chunk into syllables: {unit count: [(syllable, tone), ...]}."""
    memo = {}

    def go(i):
        if i == len(letters):
            return {0: []}
        if i in memo:
            return memo[i]
        out = {}
        for j in range(i + 1, min(len(letters), i + 7) + 1):
            s, marks = letters[i:j], [t for t in tones[i:j] if t]
            if len(marks) > 1:
                continue
            tone = marks[0] if marks else 0
            if not s[0] in "aoe" and s[0] not in "bpmfdtnlgkhjqxrzcsyw":
                continue        # i, u, ü start with y or w
            if SYLLABLE.match(s) or (i == 0 and j == len(letters) and s in INTERJECTIONS):
                units = [(s, tone)]
            elif erhua and len(s) > 2 and s.endswith("r") and SYLLABLE.match(s[:-1]) and not tones[j - 1]:
                units = [(s[:-1], tone), ("r", 0)]
            else:
                continue
            for n, rest in go(j).items():
                out.setdefault(n + len(units), units + rest)
        memo[i] = out
        return out

    return go(0)


def split_reading(word: str, pinyin: str):
    """Split the pinyin of a word into one (syllable, tone) per Chinese character.

    Returns (units, None) or (None, reason). Tone 0 means neutral tone.
    Erhua ('diǎnr') is allowed when the word contains 儿.
    """
    target = han_count(word)
    # digits are read aloud (101 = yāolíngyāo), so they may add syllables
    extra = 4 * sum(1 for c in word if c.isdigit())
    erhua = "儿" in word
    chunks = [c for c in re.split("[%s]+" % re.escape(SEPARATORS), pinyin.strip()) if c]
    if not chunks:
        return None, "no pinyin"
    totals = {0: []}
    for chunk in chunks:
        letters, tones = _letters(chunk)
        if not re.fullmatch("[a-zü]+", letters):
            return None, "not pinyin: %r" % chunk
        options = _segment(letters, tones, erhua)
        if not options:
            return None, "no valid syllables in %r" % chunk
        totals = {a + b: x + y for a, x in totals.items() for b, y in options.items() if a + b <= target + extra}
    for n in range(target, target + extra + 1):
        if n in totals:
            return totals[n], None
    return None, "%d characters but pinyin %r does not split into %d syllables" % (target, pinyin, target)


def numbered(units) -> str:
    """[('yin', 2), ('hang', 2)] -> 'yin2 hang2' (neutral tone as 5), as in CC-CEDICT."""
    return " ".join("%s%d" % (s, t or 5) for s, t in units)


_MARKS = {"a": "āáǎà", "e": "ēéěè", "i": "īíǐì", "o": "ōóǒò", "u": "ūúǔù", "ü": "ǖǘǚǜ"}


def _mark(syllable: str, tone: int) -> str:
    s = syllable.replace("u:", "ü").replace("U:", "Ü").replace("v", "ü").replace("V", "Ü")
    if tone not in (1, 2, 3, 4):
        return s
    low = s.lower()
    if "a" in low:
        i = low.index("a")
    elif "e" in low:
        i = low.index("e")
    elif "ou" in low:
        i = low.index("o")
    else:
        i = max(low.rfind(v) for v in "iouü")
        if i < 0:
            return s
    mark = _MARKS[low[i]][tone - 1]
    return s[:i] + (mark.upper() if s[i].isupper() else mark) + s[i + 1:]


def to_marks(pinyin: str) -> str:
    """'ni3hao3' -> 'nǐhǎo'; text without tone numbers is returned unchanged.
    Tone numbers are cheaper for the model to write than tone marks."""
    return re.sub(r"([A-Za-zÜü:]+?)([1-5])", lambda m: _mark(m.group(1), int(m.group(2))), pinyin)
