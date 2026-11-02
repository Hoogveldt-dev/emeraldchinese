# PokemonWoofer: notities voor Claude

* Taal met de gebruiker: Nederlands. Geen em-dash gebruiken.
* Deze repo is een laag bovenop ZallaxDev/emerald-3ds (gepind in
  `woofer.lock`). Nooit ROM-, 3DSX- of uit de ROM gehaalde tekst committen;
  `.gitignore` dekt `roms/`, `build/`, `dist/`, `out/` en `kit/` output.
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
