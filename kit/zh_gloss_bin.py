"""zh_gloss.bin: the words of every text, for the dictionary panel in the game.

All numbers little endian. Layout:

  header (48 bytes)
    magic "ZHGLS\\0\\2\\0" (8)
    u32 n_texts,  u32 off_texts
    u32 n_words,  u32 off_words
    u32 n_tokens, u32 off_tokens
    u32 pool_size, u32 off_pool
    u32 off_decode, u32 off_wide (0 when the file has no wide table)
  texts  (24 bytes each, sorted by hash for binary search)
    u64 hash (same as zh_dialog.bin), u32 first_token, u32 n_tokens,
    u32 loc (pool offset, UTF-8), u32 reserved
  words  (28 bytes each, deduplicated)
    u32 game bytes (pool offset, ends with 0xFF), u32 characters (UTF-8),
    u32 pinyin (UTF-8), u32 meaning (UTF-8),
    u32 pinyin to draw: game letters without tone marks, 0xFF, then one byte
        per letter with its tone (0 none, 1-4),
    u32 meaning to draw (game bytes, ends with 0xFF),
    u8 hsk, u8 n_chars, u16 reserved
  tokens (u32 each): a word index, or one of the TOKEN_* values below
  decode (256 u32): per single game byte the UTF-8 of its character (pool
         offset, 0 when none), to turn names and English text into UTF-8
  wide   the two-byte characters (lead, trail) of cjk_table.json, to turn
         Chinese that is not a word (a name filled in, unmatched text) into
         UTF-8: u8 lead index per byte (256, 0xFF when not a lead byte),
         u16 trail_min, u16 trails, u32 n_chars, then n_chars u16 code points
         (index = lead index * trails + trail - trail_min), padded to 4 bytes.
         Optional: an older reader ignores it, as the field was reserved.
  pool   strings; offset 0 is the empty string. UTF-8 strings end with 0x00.

A word without pinyin (punctuation) is still a word, so the game can follow
the text in order; it is just not tappable. Characters without a glyph are left
out, as in zh_dialog.bin. Spaces and line breaks are not in the tokens; the
game skips them while matching.
"""
import struct

from zh_gloss import TOKEN, parse_item
from zh_pinyin import han_count, tone_letters

MAGIC = b"ZHGLS\x00\x02\x00"
TOKEN_PARA = 0xFFFF0000      # next paragraph (\p)
TOKEN_NAME = 0xFFFF0001      # {PLAYER} and other names filled in while playing
TOKEN_CONTROL = 0xFFFF0002   # {COLOR ...}, {PAUSE ...}: control codes, no text
HEADER = struct.Struct("<8s10I")
TEXT = struct.Struct("<QIIII")
WORD = struct.Struct("<IIIIIIBBH")


class GlossWriter:
    def __init__(self, enc, is_name):
        self.enc, self.is_name = enc, is_name
        self.pool = bytearray(b"\x00")
        self.strings = {}
        self.words, self.word_index = [], {}
        self.tokens, self.texts = [], []
        self.missing = set()

    def _str(self, data: bytes) -> int:
        if not data or data == b"\x00":
            return 0
        if data not in self.strings:
            self.strings[data] = len(self.pool)
            self.pool += data
        return self.strings[data]

    def _utf8(self, text: str) -> int:
        return self._str(text.encode("utf-8") + b"\x00") if text else 0

    def _single(self, ch: str):
        code = self.enc.chars.get(ch)
        return code[0] if code is not None and len(code) == 1 else None

    def _pinyin_game(self, pinyin: str) -> int:
        """Letters in the game's own font, tones apart (the panel draws them)."""
        letters, tones = bytearray(), bytearray()
        for base, tone in tone_letters(pinyin):
            code = self._single(base)
            if code is not None:
                letters.append(code)
                tones.append(tone)
        return self._str(bytes(letters) + b"\xff" + bytes(tones)) if letters else 0

    def _game_text(self, text: str) -> int:
        out = bytearray()
        for ch in text:
            code = self._single(ch)
            if code is not None:
                out.append(code)
        return self._str(bytes(out) + b"\xff") if out else 0

    def _word(self, s, p, g, h):
        # "$" is the end of a text in the game (0xFF): never part of a word
        kept = "".join(c for c in s if not c.isspace() and self.enc.has(c) and self.enc.chars.get(c) != b"\xff")
        self.missing.update(c for c in s if not c.isspace() and not self.enc.has(c))
        if not kept:
            return None
        try:
            game = self.enc.encode(kept, terminate=True)
        except ValueError:
            return None
        key = (game, kept, p, g, h)
        if key not in self.word_index:
            self.word_index[key] = len(self.words)
            self.words.append((self._str(game), self._utf8(kept), self._utf8(p), self._utf8(g),
                               self._pinyin_game(p), self._game_text(g), h, min(han_count(kept), 255)))
        return self.word_index[key]

    def add(self, hash_value: int, loc: str, paras):
        first = len(self.tokens)
        for n, items in enumerate(paras):
            if n:
                self.tokens.append(TOKEN_PARA)
            for raw in items:
                item = parse_item(raw)
                if item is None:
                    continue
                s, p, g, h = item
                if TOKEN.fullmatch(s):
                    inner = s[1:-1].strip()
                    self.tokens.append(TOKEN_NAME if self.is_name(inner) else TOKEN_CONTROL)
                    continue
                w = self._word(s, p, g, h)
                if w is not None:
                    self.tokens.append(w)
        self.texts.append((hash_value, first, len(self.tokens) - first, self._utf8(loc)))

    def to_bytes(self) -> bytes:
        decode = [0] * 256
        for ch, code in self.enc.chars.items():
            if len(code) == 1 and code[0] != 0xFF and not decode[code[0]]:
                decode[code[0]] = self._utf8(ch)
        while len(self.pool) % 4:
            self.pool += b"\x00"
        off_texts = HEADER.size
        off_words = off_texts + TEXT.size * len(self.texts)
        off_tokens = off_words + WORD.size * len(self.words)
        off_decode = off_tokens + 4 * len(self.tokens)
        wide = self._wide()
        off_wide = off_decode + 4 * 256 if wide else 0
        off_pool = off_decode + 4 * 256 + len(wide)
        out = bytearray(HEADER.pack(MAGIC, len(self.texts), off_texts, len(self.words), off_words,
                                    len(self.tokens), off_tokens, len(self.pool), off_pool, off_decode, off_wide))
        for h, first, n, loc in sorted(self.texts):
            out += TEXT.pack(h, first, n, loc, 0)
        for word in self.words:
            out += WORD.pack(*word, 0)
        out += struct.pack("<%dI" % len(self.tokens), *self.tokens)
        out += struct.pack("<256I", *decode)
        out += wide
        return bytes(out + self.pool)

    def _wide(self) -> bytes:
        """The table of two-byte characters (see the layout above), b"" without one."""
        t = getattr(self.enc, "table", None)
        if not t or not t.get("chars"):
            return b""
        lead_index = bytearray(b"\xff" * 256)
        for n, lead in enumerate(t["leads"]):
            lead_index[lead] = n
        points = [ord(c) if ord(c) <= 0xFFFF else 0 for c in t["chars"]]
        out = bytearray(lead_index) + struct.pack("<HHI", t["trail_min"], t["trails"], len(points))
        out += struct.pack("<%dH" % len(points), *points)
        while len(out) % 4:
            out += b"\x00"
        return bytes(out)


def read_gloss(data: bytes) -> dict:
    """zh_gloss.bin -> {hash: {"loc": str, "tokens": [word dict | "para" | "name" | "control"]}}."""
    magic, n_texts, off_texts, n_words, off_words, n_tokens, off_tokens, pool_size, off_pool, off_decode, off_wide = \
        HEADER.unpack_from(data, 0)
    if magic != MAGIC:
        raise ValueError("not a zh_gloss.bin file")
    pool = data[off_pool:off_pool + pool_size]

    def utf8(off):
        return pool[off:pool.index(b"\x00", off)].decode("utf-8") if off else ""

    def game(off):
        return pool[off:pool.index(b"\xff", off) + 1] if off else b""

    words = []
    for i in range(n_words):
        g_off, chars, pinyin, meaning, p_game, m_game, hsk, n_chars, _ = \
            WORD.unpack_from(data, off_words + i * WORD.size)
        letters = game(p_game)
        tones = pool[p_game + len(letters):p_game + 2 * len(letters) - 1] if p_game else b""
        words.append({"game": game(g_off), "s": utf8(chars), "p": utf8(pinyin), "g": utf8(meaning),
                      "h": hsk, "n": n_chars, "p_game": letters, "p_tones": tones, "g_game": game(m_game)})
    tokens = struct.unpack_from("<%dI" % n_tokens, data, off_tokens)
    special = {TOKEN_PARA: "para", TOKEN_NAME: "name", TOKEN_CONTROL: "control"}
    decode = struct.unpack_from("<256I", data, off_decode)
    out = {"decode": {b: utf8(o) for b, o in enumerate(decode) if o}, "wide": {}}
    if off_wide:
        lead_index = data[off_wide:off_wide + 256]
        trail_min, trails, n = struct.unpack_from("<HHI", data, off_wide + 256)
        points = struct.unpack_from("<%dH" % n, data, off_wide + 264)
        for lead, li in enumerate(lead_index):
            if li == 0xFF:
                continue
            for k in range(trails):
                i = li * trails + k
                if i < n and points[i]:
                    out["wide"][bytes([lead, trail_min + k])] = chr(points[i])
    for i in range(n_texts):
        h, first, n, loc, _ = TEXT.unpack_from(data, off_texts + i * TEXT.size)
        out[h] = {"loc": utf8(loc),
                  "tokens": [special.get(t) or words[t] for t in tokens[first:first + n]]}
    return out
