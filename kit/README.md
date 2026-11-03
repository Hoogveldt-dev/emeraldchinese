# kit: dialoog naar het Chinees

De verhaaldialoog (ca. 7.000 teksten) wordt tijdens het spelen vervangen
vanuit `zh_dialog.bin`. Hercompileren is daarvoor niet nodig.

`scripts/build.sh` zet de gegenereerde bestanden klaar:
`dialogue_en.jsonl`, `charmap.txt` en `cjk_table.json`. Omdat de repo privé
is, staan die en de caches (`zh_cache.json`, `zh_gloss_cache.json`) ook in
git; commit ze na elke vertaalronde. Verder staan in git: het script,
`zh_text.py`, `zh_pinyin.py`, `zh_gloss.py`, `zh_gloss_bin.py`, de tests,
`glossary.json` (officiële namen) en `font_widths.json`.

```bash
cd kit
export DEEPSEEK_API_KEY=...          # als secret in de omgeving, nooit in git
python3 translate_dialogue.py translate --estimate                           # kosten vooraf
python3 translate_dialogue.py translate --only birch_speech,LittlerootTown   # korte test
python3 translate_dialogue.py translate                                      # alles
python3 translate_dialogue.py status
python3 translate_dialogue.py build                                          # -> zh_dialog.bin
```

Standaard: DeepSeek (`deepseek-flash`, zonder nadenken), zo zuinig mogelijk:

* aanvragen alleen buiten de piekuren van DeepSeek (half tarief); de kit
  wacht anders tot het daluur is (`--allow-peak` om niet te wachten);
* de vaste instructie staat vooraan, zodat DeepSeek die uit de cache haalt;
* korte id's per aanvraag, compacte JSON, teksten van meerdere plekken per
  aanvraag;
* een afgekapt of onleesbaar antwoord wordt niet opnieuw gevraagd zoals het
  was: de portie wordt gehalveerd, wat dan nog mislukt komt bij de volgende run;
* elk run schrijft het verbruik naar `api_usage.jsonl` (in git).

Andere aanbieders:

* `--provider openai --base-url ... --model ...` met `OPENAI_API_KEY`, bijv.
  SiliconFlow: `--base-url https://api.siliconflow.cn/v1 --model deepseek-ai/DeepSeek-V3`
* `--provider anthropic` met `ANTHROPIC_API_KEY`.
* `--level simple` geeft eenvoudiger Chinees (rond HSK 3-4).
* Voortgang staat in `zh_cache.json` (in git); stoppen en hervatten kan.

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
* Het model geeft alleen de woorden; leestekens en `{...}` vult de kit in.
* CC-CEDICT (`kit/cedict_ts.u8`, wordt de eerste keer gedownload, niet in
  git) herstelt gratis tonen als het woordenboek precies één uitspraak kent,
  en geeft waarschuwingen voor de rest (`review` toont ze).
* Voortgang staat in `zh_gloss_cache.json` (in git). Verandert een
  vertaling, dan wordt die tekst opnieuw verwerkt.
* Het formaat van `zh_gloss.bin` staat bovenin `zh_gloss_bin.py`. Kopieer het
  bestand naast `zh_dialog.bin`.
* Tests (zonder ROM of API-sleutel): `python3 -m unittest test_zh_gloss`.
