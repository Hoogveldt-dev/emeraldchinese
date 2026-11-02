# kit: dialoog naar het Chinees

De verhaaldialoog (ca. 7.000 teksten) wordt tijdens het spelen vervangen
vanuit `zh_dialog.bin`. Hercompileren is daarvoor niet nodig.

`scripts/build.sh` zet de gegenereerde bestanden klaar:
`dialogue_en.jsonl`, `charmap.txt` en `cjk_table.json`. In git staan alleen
het script, `zh_text.py`, `zh_pinyin.py`, `zh_gloss.py`,
`zh_gloss_bin.py`, de tests, `glossary.json` (officiële namen) en
`font_widths.json`.

```bash
cd kit
export ANTHROPIC_API_KEY=...
python3 translate_dialogue.py translate --only birch_speech,LittlerootTown   # korte test
python3 translate_dialogue.py translate                                      # alles
python3 translate_dialogue.py status
python3 translate_dialogue.py build                                          # -> zh_dialog.bin
```

* OpenAI-compatibel (bijv. DeepSeek):
  `--provider openai --base-url https://api.deepseek.com --model deepseek-chat`
* `--level simple` geeft eenvoudiger Chinees (rond HSK 3-4).
* Voortgang staat in `zh_cache.json` (niet in git); stoppen en hervatten kan.

Kopieer `zh_dialog.bin` naar `sdmc/3ds/emerald3ds/zh_dialog.bin`.

## Woorden voor het woordenboek (`gloss`)

Fase 1 van `docs/PLAN-woordenboek.md`. Per vertaalde tekst bepaalt het
taalmodel de woorden, met pinyin (passend bij de zin), een korte Engelse
betekenis en het HSK-niveau.

```bash
python3 translate_dialogue.py gloss --only birch_speech,LittlerootTown   # proefronde
python3 translate_dialogue.py review --only birch_speech                 # met de hand nalopen
python3 translate_dialogue.py gloss                                      # alles
python3 translate_dialogue.py build            # -> zh_dialog.bin en zh_gloss.bin
```

* Elk antwoord wordt gecontroleerd: de woorden vormen samen precies de alinea,
  het aantal pinyin-lettergrepen past bij het aantal tekens (erhua met 儿 mag),
  elk Chinees woord heeft een betekenis, en `{...}`-tokens staan los. Een
  afgekeurde tekst wordt bij de volgende run opnieuw gevraagd.
* `--cedict cedict_ts.u8` (bij `gloss` en `review`) vergelijkt de lezingen met
  CC-CEDICT. Dat geeft alleen waarschuwingen.
* Voortgang staat in `zh_gloss_cache.json` (niet in git). Verandert een
  vertaling, dan wordt die tekst opnieuw verwerkt.
* Het formaat van `zh_gloss.bin` staat bovenin `zh_gloss_bin.py`. Kopieer het
  bestand naast `zh_dialog.bin`.
* Tests (zonder ROM of API-sleutel): `python3 -m unittest test_zh_gloss`.
