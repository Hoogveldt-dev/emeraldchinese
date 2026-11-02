# kit: dialoog naar het Chinees

De verhaaldialoog (ca. 7.000 teksten) wordt tijdens het spelen vervangen
vanuit `zh_dialog.bin`. Hercompileren is daarvoor niet nodig.

`scripts/build.sh` zet de gegenereerde bestanden klaar:
`dialogue_en.jsonl`, `charmap.txt` en `cjk_table.json`. In git staan alleen
het script, `zh_text.py`, `glossary.json` (officiële namen) en
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
