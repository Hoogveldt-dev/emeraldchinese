"""Encoding of game texts for the Chinese Emerald 3DS build.

Texts are written as in the pret decomp: characters, \\n \\l \\p, {PLACEHOLDER}s,
{CONSTANT 12} arguments and $ (end of string). CJK characters become two bytes
(lead, trail) from cjk_table.json, everything else follows charmap.txt.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def fnv1a64(data: bytes) -> int:
    h = 0xCBF29CE484222325
    for b in data:
        h ^= b
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


class Encoder:
    def __init__(self, charmap: Path = HERE / "charmap.txt", table: Path = HERE / "cjk_table.json"):
        self.chars, self.escapes, self.consts = {}, {}, {}
        for line in charmap.read_text(encoding="utf-8").splitlines():
            s = line.split("@")[0].strip()
            m = re.match(r"^'(\\?.)'\s*=\s*((?:[0-9A-Fa-f]{2}\s*)+)$", s)
            if m:
                key, val = m.group(1), bytes(int(x, 16) for x in m.group(2).split())
                if key in ("\\'", '\\"', "\\\\"):
                    self.chars.setdefault(key[1], val)
                elif key.startswith("\\"):
                    self.escapes.setdefault(key[1], val)
                else:
                    self.chars.setdefault(key, val)
                continue
            m = re.match(r"^(\w+)\s*=\s*((?:[0-9A-Fa-f]{2}\s*)+)$", s)
            if m:
                self.consts.setdefault(m.group(1), bytes(int(x, 16) for x in m.group(2).split()))
        t = json.loads(table.read_text(encoding="utf-8"))
        self.cjk = {}
        for i, ch in enumerate(t["chars"]):
            self.cjk[ch] = bytes([t["leads"][i // t["trails"]], t["trail_min"] + i % t["trails"]])
        self.leads = set(t["leads"])

    def _int(self, tok: str) -> bytes:
        if tok.startswith("0x"):
            n = int(tok, 16)
            size = {2: 1, 4: 2, 8: 4}[len(tok) - 2]
        else:
            suffix = tok[-1] if tok[-1] in "HW" else ""
            n = int(tok.rstrip("HW"))
            size = 2 if suffix == "H" else 4 if suffix == "W" else (4 if n >= 0x10000 else 2 if n >= 0x100 else 1)
        return n.to_bytes(size, "little")

    def encode(self, text: str, terminate: bool = False, cjk: bool = True) -> bytes:
        out = bytearray()
        i = 0
        while i < len(text):
            c = text[i]
            if c == "{":
                end = text.index("}", i)
                for tok in text[i + 1:end].split():
                    if tok[0].isdigit():
                        out += self._int(tok)
                    elif tok in self.consts:
                        out += self.consts[tok]
                    else:
                        raise ValueError("unknown constant {%s}" % tok)
                i = end + 1
                continue
            if c == "\\" and i + 1 < len(text):
                e = text[i + 1]
                if e in self.escapes:
                    out += self.escapes[e]
                elif e in self.chars:
                    out += self.chars[e]
                else:
                    raise ValueError("unknown escape \\%s" % e)
                i += 2
                continue
            if cjk and c in self.cjk and ord(c) > 0x2000:
                out += self.cjk[c]
            elif c in self.chars:
                out += self.chars[c]
            elif c in self.cjk:
                out += self.cjk[c]
            else:
                raise ValueError("no code for %r" % c)
            i += 1
        if terminate:
            out.append(0xFF)
        return bytes(out)

    def has(self, ch: str) -> bool:
        return ch in self.cjk or ch in self.chars


def write_table(entries: dict, path: Path) -> None:
    """entries: {hash: bytes (EOS-terminated)} -> zh_dialog.bin"""
    items = sorted(entries.items())
    blob = bytearray()
    index = bytearray()
    for h, data in items:
        index += h.to_bytes(8, "little") + len(blob).to_bytes(4, "little") + len(data).to_bytes(4, "little")
        blob += data
    header = b"ZHDLG\x00\x01\x00" + len(items).to_bytes(4, "little") + (16 + len(index)).to_bytes(4, "little")
    path.write_bytes(header + index + blob)
