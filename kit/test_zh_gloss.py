"""Tests for the gloss step. Run: python3 -m unittest test_zh_gloss (in kit/)."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import translate_dialogue as td  # noqa: E402
import zh_gloss  # noqa: E402
from zh_gloss_bin import GlossWriter, read_gloss  # noqa: E402
from zh_pinyin import split_reading  # noqa: E402
from zh_text import Encoder  # noqa: E402

# Small made-up example data. 吧 has no glyph on purpose.
CHARMAP = "\n".join(["' ' = 00", "'$' = FF"] + ["'%s' = %02X" % (c, 0xBB + i) for i, c in enumerate("ABCDEFGH")]
                    + ["PLAYER = FD 01", "COLOR = FC 01", "BLUE = 08"]) + "\n"
CJK = {"chars": list("你好，。！我们去银行走一点儿"), "leads": [0xF0], "trails": 64, "trail_min": 0x40}
PARA = "你好，{PLAYER}！我们去银行吧。"
WORDS = [["你好", "nǐhǎo", "hello", 1], ["，"], ["{PLAYER}"], ["！"], ["我们", "wǒmen", "we", 1],
         ["去", "qù", "to go", 1], ["银行", "yínháng", "bank", 3], ["吧", "ba", "(suggestion)", 2], ["。"]]


def fixture(test):
    d = Path(tempfile.mkdtemp())
    test.addCleanup(shutil.rmtree, d)
    (d / "charmap.txt").write_text(CHARMAP, encoding="utf-8")
    (d / "cjk_table.json").write_text(json.dumps(CJK, ensure_ascii=False), encoding="utf-8")
    return d


class PinyinTest(unittest.TestCase):
    def test_good(self):
        for word, p in [("银行", "yínháng"), ("行走", "xíngzǒu"), ("一点儿", "yìdiǎnr"),
                        ("你好", "nǐ hǎo"), ("东西", "dōngxi"), ("西安", "xī'ān"), ("女儿", "nǚ'ér"),
                        ("这儿", "zhèr"), ("啊啊啊", "āāā"), ("101号道路", "Yāolíngyāo Hào Dàolù")]:
            units, why = split_reading(word, p)
            self.assertIsNone(why, (word, p))
            self.assertTrue(units)

    def test_bad(self):
        for word, p in [("你好", "nǐ"), ("好", "hǎǒ"), ("你", "ni3x"), ("你", ""), ("这", "zhèr")]:
            self.assertIsNotNone(split_reading(word, p)[1], (word, p))


class CheckTest(unittest.TestCase):
    def test_ok(self):
        items, errors = zh_gloss.check_paragraph(PARA, WORDS)
        self.assertEqual(errors, [])
        self.assertEqual(len(items), len(WORDS))

    def test_punctuation_loses_pinyin(self):
        items, errors = zh_gloss.check_paragraph("你。", [["你", "nǐ", "you", 1], ["。", "x", "y", 3]])
        self.assertEqual(errors, [])
        self.assertEqual(items[1], ["。", "", "", 0])

    def test_errors(self):
        cases = [
            [["你好", "nǐhǎo", "hello", 1]],                       # text missing
            [w if w[0] != "银行" else ["银行", "yín", "bank", 3] for w in WORDS],
            [w if w[0] != "去" else ["去", "qù", "", 1] for w in WORDS],
            [["你好，{PLAYER}"]] + WORDS[3:],                      # token not on its own
        ]
        for words in cases:
            self.assertNotEqual(zh_gloss.check_paragraph(PARA, words)[1], [], words)

    def test_words_only(self):
        """The model may list only the words; punctuation and tokens are filled in."""
        only = [w for w in WORDS if len(w) > 1]
        items, errors = zh_gloss.check_paragraph(PARA, only)
        self.assertEqual(errors, [])
        self.assertEqual([i[0] for i in items], [w[0] for w in WORDS])
        _, errors = zh_gloss.check_paragraph(PARA, [w for w in only if w[0] != "去"])
        self.assertTrue(any("without a word" in e for e in errors))
        _, errors = zh_gloss.check_paragraph(PARA, list(reversed(only)))
        self.assertTrue(errors)

    def test_tone_numbers(self):
        items, errors = zh_gloss.check_paragraph("银行。", [["银行", "yin2hang2", "bank", 3]])
        self.assertEqual(errors, [])
        self.assertEqual(items[0][1], "yínháng")

    def test_paragraph_count(self):
        self.assertIsNone(zh_gloss.check_answer([PARA, PARA], [WORDS])[0])
        self.assertEqual(zh_gloss.check_answer([PARA], [WORDS])[1], [])

    def test_key_follows_translation(self):
        self.assertEqual(zh_gloss.zh_key([PARA]), zh_gloss.zh_key([PARA]))
        self.assertNotEqual(zh_gloss.zh_key([PARA]), zh_gloss.zh_key([PARA + "。"]))

    def test_cedict(self):
        d = fixture(self)
        (d / "cedict.u8").write_text("# test\n銀行 银行 [yin2 hang2] /bank/\n銀行 银行 [hang2 hang2] /x/\n"
                                     "一點兒 一点儿 [yi1 dian3 r5] /a little/\n", encoding="utf-8")
        c = zh_gloss.Cedict(d / "cedict.u8")
        self.assertIsNone(c.warn("银行", "yínháng"))
        self.assertIsNotNone(c.warn("银行", "yínxíng"))
        self.assertIsNone(c.warn("一点儿", "yìdiǎnr"))   # tone change of 一
        self.assertIsNone(c.warn("你", "nǐ"))              # unknown word: no warning

    def test_cedict_fixes_first_tone(self):
        d = fixture(self)
        (d / "cedict.u8").write_text("背包 背包 [bei1 bao1] /backpack/\n一点儿 一点儿 [yi1 dian3 r5] /a bit/\n",
                                     encoding="utf-8")
        c = zh_gloss.Cedict(d / "cedict.u8")
        self.assertEqual(zh_gloss.fix_first_tone(c, "背包", "beibāo"), "bēibāo")
        self.assertIsNone(zh_gloss.fix_first_tone(c, "背包", "bēibāo"))     # nothing to fix
        self.assertIsNone(zh_gloss.fix_first_tone(c, "一点儿", "yidiǎnr"))  # tone change of 一
        paras = [[["背包", "beibāo", "backpack", 3], ["。", "", "", 0]]]
        self.assertEqual(zh_gloss.apply_cedict(paras, c), [])
        self.assertEqual(paras[0][0][1], "bēibāo")

    def test_cedict_neutral_tone(self):
        d = fixture(self)
        (d / "cedict.u8").write_text("外面 外面 [wai4 mian4] /outside/\n", encoding="utf-8")
        c = zh_gloss.Cedict(d / "cedict.u8")
        self.assertIsNone(c.warn("外面", "wàimian"))       # spoken neutral tone
        self.assertIsNotNone(c.warn("外面", "wàimiàn".replace("à", "á", 1)))


class BinaryTest(unittest.TestCase):
    def test_round_trip(self):
        enc = Encoder(*(fixture(self) / n for n in ("charmap.txt", "cjk_table.json")))
        w = GlossWriter(enc, lambda t: t == "PLAYER")
        paras, errors = zh_gloss.check_answer([PARA, "我们去银行。"], [WORDS, WORDS[4:7] + [["。"]]])
        self.assertEqual(errors, [])
        w.add(0x1234, "SomeTown", paras)
        w.add(0x0042, "", [[["{COLOR BLUE}"], ["你好", "nǐhǎo", "hello", 1]]])
        self.assertEqual(w.missing, {"吧"})
        texts = read_gloss(w.to_bytes())
        self.assertEqual(sorted(texts), [0x42, 0x1234])
        self.assertEqual(texts[0x1234]["loc"], "SomeTown")
        toks = texts[0x1234]["tokens"]
        shown = [t if isinstance(t, str) else t["s"] for t in toks]
        self.assertEqual(shown, ["你好", "，", "name", "！", "我们", "去", "银行", "。",
                                 "para", "我们", "去", "银行", "。"])
        bank = toks[6]
        self.assertEqual((bank["p"], bank["g"], bank["h"], bank["n"]), ("yínháng", "bank", 3, 2))
        self.assertEqual(bank["game"], enc.encode("银行", terminate=True))
        self.assertIs(toks[6], toks[11])                  # same word stored once
        self.assertEqual(len(w.words), 7)
        self.assertEqual([t if isinstance(t, str) else t["s"] for t in texts[0x42]["tokens"]],
                         ["control", "你好"])


class BuildTest(unittest.TestCase):
    """build writes zh_gloss.bin next to zh_dialog.bin and skips stale words."""

    def test_build(self):
        d = fixture(self)
        rows = [{"id": "a", "hash": "%016x" % 1, "context": "TownA", "kind": "box", "en": "Hi, {PLAYER}!$"},
                {"id": "b", "hash": "%016x" % 2, "context": "TownA", "kind": "box", "en": "Go.$"}]
        (d / "dialogue_en.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        cache = {rows[0]["hash"]: {"id": "a", "zh": [PARA]}, rows[1]["hash"]: {"id": "b", "zh": ["我们去。"]}}
        (d / "zh_cache.json").write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        gloss = {rows[0]["hash"]: {"zh": zh_gloss.zh_key([PARA]), "w": [WORDS], "warn": []},
                 rows[1]["hash"]: {"zh": "old", "w": [], "warn": []}}
        (d / "zh_gloss_cache.json").write_text(json.dumps(gloss, ensure_ascii=False), encoding="utf-8")
        for name, value in (("HERE", d), ("SOURCE", d / "dialogue_en.jsonl"), ("CACHE", d / "zh_cache.json"),
                            ("GLOSS_CACHE", d / "zh_gloss_cache.json")):
            old = getattr(td, name)
            setattr(td, name, value)
            self.addCleanup(setattr, td, name, old)
        td.cmd_build(SimpleNamespace(out=str(d / "zh_dialog.bin")))
        texts = read_gloss((d / "zh_gloss.bin").read_bytes())
        self.assertEqual(list(texts), [1])
        self.assertEqual(texts[1]["loc"], "TownA")
        self.assertIn("name", texts[1]["tokens"])



class GlossCommandTest(unittest.TestCase):
    """gloss keeps good answers, rejects bad ones and skips what is current."""

    def test_gloss(self):
        d = fixture(self)
        rows = [{"id": "a", "hash": "%016x" % 1, "context": "T", "kind": "box", "en": "Hi.$"},
                {"id": "b", "hash": "%016x" % 2, "context": "T", "kind": "box", "en": "Go.$"}]
        (d / "dialogue_en.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        cache = {rows[0]["hash"]: {"id": "a", "zh": [PARA]}, rows[1]["hash"]: {"id": "b", "zh": ["我们去。"]}}
        (d / "zh_cache.json").write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        (d / "glossary.json").write_text("{}", encoding="utf-8")
        # short ids per request; the second text has a wrong reading
        answer = {"1": [WORDS], "2": [[["我们", "wǒ", "we", 1], ["去", "qù", "go", 1]]]}
        calls = []

        def fake_api(args, system, user):
            calls.append(user)
            return json.dumps(answer, ensure_ascii=False)

        for name, value in (("SOURCE", d / "dialogue_en.jsonl"), ("CACHE", d / "zh_cache.json"),
                            ("GLOSS_CACHE", d / "zh_gloss_cache.json"), ("GLOSSARY", d / "glossary.json"),
                            ("call_api", fake_api)):
            old = getattr(td, name)
            setattr(td, name, value)
            self.addCleanup(setattr, td, name, old)
        args = SimpleNamespace(only=None, limit=None, batch=10, workers=1, cedict=None, estimate=False,
                               provider="deepseek", model=None, base_url=None, key="test", allow_peak=True)
        old_load = zh_gloss.load_cedict
        zh_gloss.load_cedict = lambda path: None          # no download in tests
        self.addCleanup(setattr, zh_gloss, "load_cedict", old_load)
        old_log = td.USAGE_LOG
        td.USAGE_LOG = d / "api_usage.jsonl"
        self.addCleanup(setattr, td, "USAGE_LOG", old_log)
        td.cmd_gloss(args)
        gloss = json.loads((d / "zh_gloss_cache.json").read_text(encoding="utf-8"))
        self.assertEqual(list(gloss), [rows[0]["hash"]])          # b was rejected (pinyin)
        td.cmd_gloss(args)                                         # only b is asked again
        self.assertEqual(len(calls), 2)
        self.assertNotIn(rows[0]["hash"], calls[1])



class ApiUseTest(unittest.TestCase):
    """No needless requests: a cut-off answer splits the batch, peak hours are known."""

    def test_split_on_truncation(self):
        import llm
        sizes = []

        def fake(args, system, user):
            n = user.count('"id"')
            sizes.append(n)
            if n > 1:
                raise llm.Truncated()
            return '{"1":"ok"}'

        old = td.call_api
        td.call_api = fake
        self.addCleanup(setattr, td, "call_api", old)
        group = [{"id": str(i)} for i in range(4)]
        done = td.ask(None, "", group, lambda g: json.dumps([{"id": r["id"]} for r in g]),
                      lambda g, answer: len(g), [])
        self.assertEqual(done, 4)
        self.assertEqual(sizes, [4, 2, 1, 1, 2, 1, 1])     # never the same batch twice

    def test_peak_hours(self):
        import datetime
        import llm
        utc = datetime.timezone.utc
        self.assertTrue(llm.is_peak(datetime.datetime(2026, 11, 2, 7, 0, tzinfo=utc)))    # Monday
        self.assertFalse(llm.is_peak(datetime.datetime(2026, 11, 2, 20, 0, tzinfo=utc)))
        self.assertFalse(llm.is_peak(datetime.datetime(2026, 11, 7, 7, 0, tzinfo=utc)))   # Saturday
        self.assertEqual(llm.minutes_to_off_peak(datetime.datetime(2026, 11, 2, 9, 30, tzinfo=utc)), 30)


if __name__ == "__main__":
    unittest.main()
