# Overdracht woordenboekfunctie (2026-11-02)

## Stand van zaken

- Het plan staat in `docs/dictionary/PLAN.md` (versie 2) in WooferCitra. De
  gebruiker heeft alle punten goedgekeurd.
- Kern van het plan: PokemonWoofer levert de tekst zelf aan, dus geen
  screenshots en geen OCR. Laag A zit in de game (woordenboekpaneel op het
  onderscherm). Laag B zit in WooferCitra (optioneel Android-paneel via het
  protocol `WOOF1` over `svcOutputDebugString`).
- De repo's blijven apart, maar worden samen ontwikkeld. Het protocol komt in
  beide repo's te staan.

## Gedaan

- WooferCitra, branch `ccr-b774cd4f-bc9hgz`:
  - `PLAN.md` versie 2;
  - de Qt-code van de eerste poging (commit `8052992`) is teruggedraaid;
  - dit overdrachtsdocument.
- PokemonWoofer, branch `ccr-b774cd4f-bc9hgz`: aangemaakt, met een kopie van
  dit document in `docs/OVERDRACHT-woordenboek.md`. Verder nog geen code.

## Update: fase 1 geschreven (branch `ccr-f8302ad8-9uq3y4`)

De punten hieronder zijn uitgevoerd in `kit/`: `zh_pinyin.py` (lettergrepen),
`zh_gloss.py` (prompt, controles, CC-CEDICT), `zh_gloss_bin.py` (formaat,
schrijver en lezer), de commando's `gloss` en `review` in
`translate_dialogue.py`, en `test_zh_gloss.py` (11 tests, slagen). Nog te
doen: de proefronde met ROM en API-sleutel, en het oordeel over de
steekproef. Daarna fase 2.

## Update: de brug (beide repo's, branch `ccr-f8302ad8-9uq3y4`)

Plan versie 3: de koppeling is spelonafhankelijk gemaakt voor volgende games.

- `docs/woofer-bridge/PROTOCOL.md` in beide repo's (gelijk houden).
- WooferCitra: `src/core/woofer/bridge.*` (herkent `WOOF1`-regels, handdruk
  via `svcGetSystemInfo` type `'WOOF'`), `src/core/woofer/vocab.*` (gedeelde
  woordenlijst `sdmc:/woofer/vocab.jsonl`), JNI en
  `org.citra.emu.woofer.WooferBridge` voor het Android-paneel, Catch-tests in
  `src/tests/core/woofer/`.
- PokemonWoofer: `port/woofer_bridge.c`/`.h`, patch
  `patches/port/0110-woofer-bridge.patch` (handdruk en `hello` bij opstarten),
  host-test `scripts/test_port.sh`.
- Nog niet: `line`, `clear` en `saved` vanuit de game (na fase 2) en het
  paneel zelf in WooferCitra (fase 4). De volledige builds (3DSX, Android)
  zijn in de cloudsessie niet gedraaid: geen ROM, geen devkitARM, geen
  Android SDK.

## Volgende stap: fase 1 in PokemonWoofer (`kit/`)

Nieuwe stap `gloss` in `kit/translate_dialogue.py`, met de helpers in een
nieuwe module `kit/zh_gloss.py`:

1. Per vertaalde tekst uit `zh_cache.json` het taalmodel laten bepalen:
   woorden (`s`), pinyin met toontekens passend bij de zin (`p`), korte
   betekenis (`g`) en HSK-niveau (`h`). Leestekens en `{...}`-tokens zijn
   aparte items zonder pinyin. De Engelse bron en de officiële namen uit
   `glossary.json` gaan mee als context.
2. Cache in `kit/zh_gloss_cache.json` (hervatbaar), met een hash van de
   Chinese tekst zodat een gewijzigde vertaling opnieuw wordt verwerkt.
3. Automatische controle per antwoord:
   - de woorden samen vormen exact de alinea (witruimte genegeerd);
   - aantal pinyin-lettergrepen past bij het aantal tekens (splitsen met een
     lijst geldige lettergrepen, erhua met 儿 toegestaan);
   - Chinese woorden hebben pinyin en betekenis, leestekens niet;
   - optioneel: lezingen vergelijken met CC-CEDICT (`--cedict pad`), alleen
     als waarschuwing.
4. `build` schrijft naast `zh_dialog.bin` ook `zh_gloss.bin`. Voorgesteld
   formaat:
   - header: magic `ZHGLS\0\1\0`, aantallen en offsets van teksten, woorden,
     tokens en een stringpool;
   - tekst: hash (zelfde als `zh_dialog.bin`), eerste token, aantal tokens,
     offset van de plek in het spel;
   - woord: game-bytes van de tekens (0xFF-afgesloten), UTF-8 van tekens,
     pinyin en betekenis, HSK-niveau;
   - token: index van een woord, of een speciale waarde voor een ingevulde
     naam (`{PLAYER}` enz.) of een nieuwe alinea;
   - tekens zonder glyph worden net als in `build` weggelaten.
5. Nieuw commando `review --only <context>` dat per tekst de woorden met
   pinyin, betekenis en waarschuwingen toont, zodat de gebruiker een
   steekproef kan beoordelen.
6. Unit tests in `kit/test_zh_gloss.py` met nepdata (eigen kleine
   `charmap.txt` en `cjk_table.json`), alleen standaardbibliotheek.
7. `kit/README.md` en `.gitignore` bijwerken (`zh_gloss_cache.json`,
   `zh_gloss.bin`).

Beperking: in een cloudsessie is er geen ROM en geen API-sleutel. De echte
proefronde op een paar contexten doet de gebruiker zelf.

## Opmerking voor de nieuwe sessie

De vorige sessie werd twee keer afgebroken met "Output blocked by content
filtering policy" tijdens het schrijven van code. De oorzaak is onbekend.
Advies: code in kleine bestanden en stappen schrijven, en geen lange
fragmenten speltekst of lijsten met namen uit de game in antwoorden of code
overnemen. Verwijs naar `glossary.json` in plaats van de inhoud te herhalen.
