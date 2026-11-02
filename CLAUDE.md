# PokemonWoofer: notities voor Claude

* Taal met de gebruiker: Nederlands. Geen em-dash gebruiken.
* Deze repo is een laag bovenop ZallaxDev/emerald-3ds (gepind in
  `woofer.lock`).
* De repo is privé en blijft privé (besluit gebruiker, 2026-11-02). Daarom
  staan speldata bewust in git, zodat elke sessie erbij kan:
  - `roms/`: de eigen ROM-dump (BPEE);
  - `prebuilt/`: een kant-en-klare Chinese 3DSX met LEESMIJ;
  - `kit/`: `dialogue_en.jsonl`, `charmap.txt`, `cjk_table.json` en de
    caches `zh_cache.json` en `zh_gloss_cache.json`. Vertaal- en woordwerk
    altijd committen, dat is het waardevolle resultaat.
  Builduitvoer (`build/`, `dist/`, `out/`, `kit/zh_*.bin`) blijft buiten git.
  Nooit naar een openbare repo of fork pushen. Moet de repo ooit openbaar,
  dan eerst `roms/`, `prebuilt/` en de kitdata uit de hele geschiedenis
  verwijderen (bijv. `git filter-repo`).
* Vertalen via DeepSeek (`kit/llm.py`, standaard): sleutel in de omgeving als
  `DEEPSEEK_API_KEY`, nooit in git of in bestanden in de repo. Tegoed is
  beperkt: altijd eerst `--estimate`, alleen buiten de piekuren, en na elke
  run `kit/api_usage.jsonl` en de caches committen.
* Zonder API-sleutel kan Claude zelf vertalen en woorden bepalen: antwoord in
  hetzelfde JSON-formaat als de API en laat het door `cmd_translate` en
  `cmd_gloss` controleren (de controles zijn gelijk). Speltekst wel kort
  houden in antwoorden in de chat.
* Bouwen: `scripts/build.sh` (Docker). Zonder draaiende daemon eerst
  `dockerd &` starten. De boom staat daarna in `build/emerald-3ds/build/upstream`.
* Wijzigingen aan de decomp gaan als patch naar `patches/pokeemerald/`
  (nummers 9100+, sorteren na die van de port); aan `3ds_port/` naar
  `patches/port/`; nieuwe C-bestanden naar `port/`.
* Chinese tekens: 2 bytes (lead, trail), tabel uit `tools/gen_font.py`.
  Lead-bytes overlappen Japanse codes; `IsStringJapanese` is daarom uitgezet.
  Teken 12 px breed, berichtvak 208 px, dus ca. 17 tekens per regel.
* Catalogusformaat: `[LABEL] <hash Engelse tekst>` + tekstregel, zie
  `tools/localize_chinese.py`. Een hash die niet klopt betekent dat de Engelse
  bron veranderde.
* Testen: Azahar headless is niet aanwezig; minimaal moet de build slagen en
  `localize_chinese.py --check` zonder problemen draaien.
  Zonder ROM: `scripts/test_port.sh` (eigen C-code in `port/`) en
  `cd kit && python3 -m unittest test_zh_gloss`.
* Brug naar WooferCitra: `port/woofer_bridge.c` is spelonafhankelijk; het
  protocol staat in `docs/woofer-bridge/PROTOCOL.md` en is gelijk aan dat in
  WooferCitra. Wijzig het altijd in beide repo's.
