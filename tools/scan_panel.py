#!/usr/bin/env python3
"""Checks what the Woofer panel gets for every text of the game.

For every dialogue text (kit/zh_dialog.bin) and every built-in text
(kit/zh_catalog.jsonl), with names filled in (a Latin and a Chinese one), page
by page: the page matcher and the UTF-8 conversion of port/woofer_gloss.c (the
real C code, through ctypes) must give exactly the Chinese the game prints.

    python3 tools/scan_panel.py            # summary, exit 1 on problems
    python3 tools/scan_panel.py -v         # every problem

Needs kit/zh_dialog.bin and kit/zh_gloss.bin (cd kit && python3 translate_dialogue.py build).
"""
import argparse
import ctypes
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit"))
from zh_text import Encoder  # noqa: E402
from zh_gloss_bin import LATIN_SYMBOLS, read_gloss  # noqa: E402

EOS, NEWLINE, SCROLL, CLEAR, SPACE, CTRL, PLACEHOLDER = 0xFF, 0xFE, 0xFA, 0xFB, 0x00, 0xFC, 0xFD
DYNAMIC, KEYPAD, EXTRA = 0xF7, 0xF8, 0xF9
# pokeemerald's GetExtCtrlCodeLength
CTRL_LEN = [1, 2, 2, 2, 4, 2, 2, 1, 2, 1, 1, 3, 2, 2, 2, 1, 3, 2, 2, 2, 2, 1, 1, 1, 1]


class Seg(ctypes.Structure):
    _fields_ = [("kind", ctypes.c_uint8), ("word", ctypes.c_uint32), ("start", ctypes.c_uint16),
                ("len", ctypes.c_uint16)]


class Word(ctypes.Structure):
    _fields_ = [("game", ctypes.c_void_p), ("s", ctypes.c_char_p), ("p", ctypes.c_char_p), ("g", ctypes.c_char_p),
                ("pGame", ctypes.c_void_p), ("pTones", ctypes.c_void_p), ("gGame", ctypes.c_void_p),
                ("hsk", ctypes.c_uint), ("nChars", ctypes.c_uint)]


def ctrl_len(t, i):
    if t[i] == CTRL:
        return 1 if i + 1 >= len(t) or t[i + 1] == EOS else 1 + (CTRL_LEN[t[i + 1]] if t[i + 1] < len(CTRL_LEN) else 1)
    if t[i] == PLACEHOLDER:
        return 1 if i + 1 >= len(t) or t[i + 1] == EOS else 2
    return 0


# The symbols the game draws from two bytes, as charmap.txt names them.
KEYS = ["Ⓐ", "Ⓑ", "Ⓛ", "Ⓡ", "START", "SELECT", "↑", "↓", "←", "→", "↕", "↔", "✚"]
EXTRA_SYMBOLS = ["↑", "↓", "←", "→", "+", "Lv", "PP", "ID", "No", "_", "①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧",
                 "⑨", "(", ")", "◎", "△", "✕"]


def symbol(t, i):
    """(text, bytes) of a two-byte symbol at t[i], or None."""
    if t[i] not in (DYNAMIC, KEYPAD, EXTRA) or i + 1 >= len(t) or t[i + 1] == EOS:
        return None
    table = {DYNAMIC: [], KEYPAD: KEYS, EXTRA: EXTRA_SYMBOLS}[t[i]]
    return (table[t[i + 1]] if t[i + 1] < len(table) else ""), 2


def load_lib(tmp):
    """port/woofer_gloss.c and woofer_dict.c (for the game's charset) as a library."""
    so = Path(tmp) / "woofer_panel.so"
    port = ROOT / "port"
    subprocess.run(["cc", "-std=gnu99", "-O2", "-shared", "-fPIC", "-I", str(port), str(port / "woofer_gloss.c"),
                    str(port / "woofer_dict.c"), str(port / "woofer_bridge.c"),
                    str(ROOT / "tests" / "port" / "game_stubs.c"), "-o", str(so)], check=True)
    lib = ctypes.CDLL(str(so))
    lib.WooferDict_Charset.restype = ctypes.c_void_p
    lib.WooferGloss_Use.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
    lib.WooferGloss_MatchPage.argtypes = [ctypes.c_uint64, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p,
                                          ctypes.POINTER(Seg), ctypes.c_int]
    lib.WooferGloss_Word.argtypes = [ctypes.c_uint32, ctypes.POINTER(Word)]
    lib.WooferGloss_ToUtf8.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t,
                                       ctypes.c_void_p]
    lib.WooferGloss_Find.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    return lib


def read_table(path):
    data = path.read_bytes()
    count, blob = struct.unpack_from("<II", data, 8)
    out = {}
    for i in range(count):
        h, off, n = struct.unpack_from("<QII", data, 16 + i * 16)
        out[h] = data[blob + off:blob + off + n]
    return out


def expand(t, name):
    out = bytearray()
    i = 0
    while i < len(t) and t[i] != EOS:
        if t[i] == PLACEHOLDER and i + 1 < len(t):
            out += name
            i += 2
            continue
        out.append(t[i])
        i += 1
    return bytes(out) + b"\xff"


def pages(t):
    """Bytes of each page (split on CLEAR outside control codes)."""
    out, start, i = [], 0, 0
    while i < len(t) and t[i] != EOS:
        c = ctrl_len(t, i)
        if c:
            i += c
            continue
        if t[i] == CLEAR:
            out.append(t[start:i])
            start = i + 1
        i += 1
    out.append(t[start:i])
    return out


class Decoder:
    """What the game prints, as text: the reference the panel is checked against."""

    def __init__(self, enc, single):
        self.single = single
        # bytes of a Latin symbol that carry no text of their own (POKéBLOCK is on its first byte)
        self.silent = {b for name in LATIN_SYMBOLS for b in enc.consts.get(name, b"")}
        self.wide = {v: k for k, v in enc.cjk.items()}
        self.leads = enc.leads

    def text(self, t):
        out, i = [], 0
        while i < len(t):
            c = ctrl_len(t, i)
            if c:
                i += c
                continue
            sym = symbol(t, i)
            if sym:
                out.append(sym[0])
                i += sym[1]
                continue
            if t[i] in (NEWLINE, SCROLL, SPACE, EOS):
                i += 1
                continue
            if t[i] in self.leads and i + 1 < len(t) and bytes(t[i:i + 2]) in self.wide:
                out.append(self.wide[bytes(t[i:i + 2])])
                i += 2
                continue
            out.append(self.single.get(t[i], "" if t[i] in self.silent else "\ufffd"))
            i += 1
        return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    kit = ROOT / "kit"
    enc = Encoder(kit / "charmap.txt", kit / "cjk_table.json")
    gloss_data = (kit / "zh_gloss.bin").read_bytes()
    decoded = read_gloss(gloss_data)
    dec = Decoder(enc, decoded["decode"])
    texts = {h: ("dialogue", t) for h, t in read_table(kit / "zh_dialog.bin").items()}
    for line in (kit / "zh_catalog.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        try:
            data = enc.encode(r["zh"], terminate=True)
        except ValueError:
            continue
        texts.setdefault(int(r["hash"], 16), (r["id"], data))
    names = {"Latin": enc.encode("KJELL"), "Chinese": enc.encode("小明")}

    with tempfile.TemporaryDirectory() as tmp:
        lib = load_lib(tmp)
        buf = ctypes.create_string_buffer(gloss_data, len(gloss_data))
        if not lib.WooferGloss_Use(buf, len(gloss_data)):
            sys.exit("zh_gloss.bin not accepted")
        cs = ctypes.c_void_p(lib.WooferDict_Charset())
        segs = (Seg * 256)()
        out = ctypes.create_string_buffer(4096)
        n_texts = n_pages = 0
        problems = {"garbled": [], "no words": [], "partial": []}
        for h, (where, raw) in sorted(texts.items()):
            if not lib.WooferGloss_Find(h, None, None, None):
                continue
            n_texts += 1
            for name_kind, name in names.items():
                printed = expand(raw, name)
                cbuf = ctypes.create_string_buffer(printed, len(printed))
                base = ctypes.addressof(cbuf)
                for page, pbytes in enumerate(pages(printed)):
                    want = dec.text(pbytes)
                    if not want.strip():
                        continue
                    if name_kind == "Latin":
                        n_pages += 1
                    n = lib.WooferGloss_MatchPage(h, page, cbuf, cs, segs, 256)
                    if n == 0:
                        problems["no words"].append((where, h, page, name_kind, want, ""))
                        continue
                    got, words = [], 0
                    for s in segs[:n]:
                        w = Word()
                        if s.kind == 0 and lib.WooferGloss_Word(s.word, ctypes.byref(w)):
                            got.append(w.s.decode("utf-8"))
                            words += 1
                        else:
                            lib.WooferGloss_ToUtf8(out, 4096, ctypes.c_char_p(base + s.start), s.len,
                                                   cs)
                            got.append(out.value.decode("utf-8", "replace"))
                    got = "".join(got).replace(" ", "")
                    if got != want.replace(" ", ""):
                        problems["garbled"].append((where, h, page, name_kind, want, got))
                    elif any(s.kind == 2 for s in segs[:n]):
                        problems["partial"].append((where, h, page, name_kind, want, got))
    print("scan_panel: %d texts, %d pages, names Latin and Chinese" % (n_texts, n_pages))
    for kind, rows in problems.items():
        print("  %-9s %d" % (kind, len(rows)))
        if args.verbose:
            for where, h, page, name_kind, want, got in rows:
                print("    %016x p%d %-7s %s\n      game:  %s\n      panel: %s" % (h, page, name_kind, where, want, got))
    return 1 if problems["garbled"] else 0


if __name__ == "__main__":
    sys.exit(main())
