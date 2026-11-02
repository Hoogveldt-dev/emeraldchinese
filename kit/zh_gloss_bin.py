"""zh_gloss.bin: the words of every text, for the dictionary panel in the game.

All numbers little endian. Layout:

  header (40 bytes)
    magic "ZHGLS\\0\\1\\0" (8)
    u32 n_texts,  u32 off_texts
    u32 n_words,  u32 off_words
    u32 n_tokens, u32 off_tokens
    u32 pool_size, u32 off_pool
  texts  (24 bytes each, sorted by hash for binary search)
    u64 hash (same as zh_dialog.bin), u32 first_token, u32 n_tokens,
    u32 loc (pool offset, UTF-8), u32 reserved
  words  (20 bytes each, deduplicated)
    u32 game bytes (pool offset, ends with 0xFF), u32 characters (UTF-8),
    u32 pinyin (UTF-8), u32 meaning (UTF-8), u8 hsk, u8 n_chars, u16 reserved
  tokens (u32 each): a word index, or one of the TOKEN_* values below
  pool   strings; offset 0 is the empty string. UTF-8 strings end with 0x00.

A word without pinyin (punctuation) is still a word, so the game can follow
the text in order; it is just not tappable. Characters without a glyph are left
out, as in zh_dialog.bin. Spaces and line breaks are not in the tokens; the
game skips them while matching.
"""
import struct

from zh_gloss import TOKEN, parse_item
from zh_pinyin import han_count

MAGIC = b"ZHGLS\x00\x01\x00"
TOKEN_PARA = 0xFFFF0000      # next paragraph (\p)
TOKEN_NAME = 0xFFFF0001      # {PLAYER} and other names filled in while playing
TOKEN_CONTROL = 0xFFFF0002   # {COLOR ...}, {PAUSE ...}: control codes, no text
HEADER = struct.Struct("<8s8I")
TEXT = struct.Struct("<QIIII")
WORD = struct.Struct("<IIIIBBH")


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

    def _word(self, s, p, g, h):
        kept = "".join(c for c in s if not c.isspace() and self.enc.has(c))
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
                               h, min(han_count(kept), 255)))
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
        while len(self.pool) % 4:
            self.pool += b"\x00"
        off_texts = HEADER.size
        off_words = off_texts + TEXT.size * len(self.texts)
        off_tokens = off_words + WORD.size * len(self.words)
        off_pool = off_tokens + 4 * len(self.tokens)
        out = bytearray(HEADER.pack(MAGIC, len(self.texts), off_texts, len(self.words), off_words,
                                    len(self.tokens), off_tokens, len(self.pool), off_pool))
        for h, first, n, loc in sorted(self.texts):
            out += TEXT.pack(h, first, n, loc, 0)
        for game, chars, pinyin, meaning, hsk, n_chars in self.words:
            out += WORD.pack(game, chars, pinyin, meaning, hsk, n_chars, 0)
        out += struct.pack("<%dI" % len(self.tokens), *self.tokens)
        return bytes(out + self.pool)


def read_gloss(data: bytes) -> dict:
    """zh_gloss.bin -> {hash: {"loc": str, "tokens": [word dict | "para" | "name" | "control"]}}."""
    magic, n_texts, off_texts, n_words, off_words, n_tokens, off_tokens, pool_size, off_pool = \
        HEADER.unpack_from(data, 0)
    if magic != MAGIC:
        raise ValueError("not a zh_gloss.bin file")
    pool = data[off_pool:off_pool + pool_size]

    def utf8(off):
        return pool[off:pool.index(b"\x00", off)].decode("utf-8") if off else ""

    words = []
    for i in range(n_words):
        game, chars, pinyin, meaning, hsk, n_chars, _ = WORD.unpack_from(data, off_words + i * WORD.size)
        words.append({"game": pool[game:pool.index(b"\xff", game) + 1], "s": utf8(chars),
                      "p": utf8(pinyin), "g": utf8(meaning), "h": hsk, "n": n_chars})
    tokens = struct.unpack_from("<%dI" % n_tokens, data, off_tokens)
    special = {TOKEN_PARA: "para", TOKEN_NAME: "name", TOKEN_CONTROL: "control"}
    out = {}
    for i in range(n_texts):
        h, first, n, loc, _ = TEXT.unpack_from(data, off_texts + i * TEXT.size)
        out[h] = {"loc": utf8(loc),
                  "tokens": [special.get(t) or words[t] for t in tokens[first:first + n]]}
    return out
