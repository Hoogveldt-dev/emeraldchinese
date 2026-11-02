# Woordenboekfunctie: bouwplan (WooferCitra + PokemonWoofer)

Status: versie 3 (2026-11-02). Versie 2 is goedgekeurd; versie 3 maakt de brug
spelonafhankelijk, zodat volgende games hetzelfde principe volgen. Het
protocol staat nu apart in `docs/woofer-bridge/PROTOCOL.md` (in beide repo's
gelijk), met een handdruk van emulator naar game en één woordenlijst voor alle
games: `sdmc:/woofer/vocab.jsonl`.

## 1. Doel

De speler ziet in PokemonWoofer (Emerald 3DS in het Chinees) een onbekend woord
of karakter, tikt het aan, krijgt de pinyin en de betekenis te zien, en kan het
met één tik opslaan in een eigen woordenlijst.

### Succescriterium voor de eerste versie

1. Tijdens een dialoog tikt de speler op het onderscherm een woord aan uit de
   zin die op dat moment in het berichtvak staat.
2. Direct verschijnen de pinyin met toontekens en een korte betekenis. De
   pinyin klopt in de context, dus 银行 is `yínháng` en 行走 is `xíngzǒu`.
3. Op verzoek is ook de oorspronkelijke Engelse zin te zien.
4. "Opslaan" zet het woord met de zin en de plek in het spel in de woordenlijst.
5. Dit werkt offline, in elke emulator (Citra, Azahar, WooferCitra) en op een
   echte 3DS.

## 2. Waarom geen OCR meer

Versie 1 ging uit van een willekeurige game waarvan we de tekst niet kennen. Dan
zijn een screenshot en OCR nodig. Bij PokemonWoofer ligt dat anders: wij maken
de game zelf, en de game weet precies welke tekst er in beeld staat.

- Elke tekst loopt door `Port_ResolveTextPointer`, waar `Cjk_TextOverride` de
  Engelse tekst vervangt door de Chinese. Op dat punt zijn de Engelse bron, de
  Chinese vertaling en de hash van de tekst alle drie bekend.
- Elk Chinees teken is een vast codepaar (lead, trail), dus er hoeft niets
  herkend te worden.
- De vertaalkit (`kit/translate_dialogue.py`) maakt alle dialogen vooraf aan.
  Daar kunnen we ook meteen de woordgrenzen, de juiste pinyin en de betekenis
  per woord laten bepalen. Dat is nauwkeuriger dan elke opzoeking tijdens het
  spelen, omdat het de hele zin als context heeft.
- De port heeft al een volledig aanraakbaar onderscherm (`3ds_bottom_ui.c`) en
  stuurt al logregels naar de emulator via `svcOutputDebugString`
  (`3ds_log.c`). WooferCitra ontvangt die in `SVC::OutputDebugString`
  (`src/core/hle/kernel/svc.cpp`).

OCR, het meeleveren van CC-CEDICT voor opzoeken tijdens het spelen, en de
Qt-code van de eerste poging zijn daarmee niet meer nodig voor dit doel.

## 3. Twee lagen

```
 PokemonWoofer (bouwtijd)                PokemonWoofer (in het spel)
 +---------------------------+           +----------------------------------+
 | kit: vertalen + per tekst |  zh_dialog | huidige zin bijhouden             |
 | woorden, pinyin, betekenis| --------> | onderscherm: zin, woord aantikken,|
 | (zh_gloss.bin)            |  zh_gloss | pinyin + betekenis, Opslaan        |
 +---------------------------+           | -> sdmc:/woofer/vocab.jsonl       |
                                         +----------------+-----------------+
                                                          | "WOOF1 {...}" via
                                                          | svcOutputDebugString
                                         +----------------v-----------------+
                                         | WooferCitra (optioneel extra)     |
                                         | Android-paneel, uitspraak (TTS),   |
                                         | woordenlijst, export naar Anki     |
                                         +----------------------------------+
```

**Laag A, in de game:** dit is de kern en bereikt het doel zelfstandig. Werkt
overal, ook zonder WooferCitra.

**Laag B, in WooferCitra:** een extra dat alleen werkt in onze emulator. Het
voegt toe wat een 3DS niet goed kan: een groot scherm voor de woordenlijst,
uitspraak via de spraakfunctie van Android, export naar Anki, en herhalen
buiten het spel.

### Repo's apart houden

Ik raad aan de twee repo's niet samen te voegen, maar wel samen te
ontwikkelen:

- **Licenties en inhoud verschillen.** WooferCitra valt onder GPLv2. PokemonWoofer
  is een laag op emerald-3ds met een eigen licentie, en de gebouwde bestanden
  bevatten speldata die nooit in een repo mag.
- **De toolchains verschillen:** devkitARM en Docker tegenover de Android NDK
  en Gradle.
- **WooferCitra moet een gewone emulator blijven** die ook andere games draait.

De koppeling loopt via één vastgelegd, geversioneerd protocol (paragraaf 5).
Dat staat in beide repo's, en beide kanten controleren het versienummer.

## 4. Fasen

### Fase 1: woorddata bij het bouwen (PokemonWoofer, `kit/`)

Eerst de data, omdat de kwaliteit daarvan alles bepaalt en we dit zonder
emulator of hercompilatie kunnen beoordelen.

- [x] `translate_dialogue.py` uitbreiden met een stap `gloss`. Per vertaalde
      tekst: een lijst woorden met per woord de tekens, pinyin met toontekens
      en een korte Engelse betekenis (eventueel ook Nederlands).
- [x] Werkwijze: eerst automatisch segmenteren en pinyin bepalen, daarna het
      taalmodel laten controleren en verbeteren, met de hele zin en de Engelse
      bron als context. Dat vangt woorden met meerdere uitspraken (行, 了, 得,
      长, 重) en spelnamen uit `glossary.json`.
- [x] Hervatbaar via een cache, net als `zh_cache.json`.
- [x] `build` maakt naast `zh_dialog.bin` een `zh_gloss.bin`, met dezelfde
      hash als sleutel. Betekenissen worden ontdubbeld in één tabel, zodat het
      bestand klein blijft voor een Old 3DS.
- [x] Controle: `--only birch_speech,LittlerootTown` en de resultaten met de
      hand nalopen. Pas daarna alles verwerken.
- [ ] Later dezelfde gegevens voor de ingebouwde catalogi (`catalog/zh_cn`):
      menu's en gevechtsberichten.

### Fase 2: woordenboek op het onderscherm (PokemonWoofer, port)

Na deze fase is het doel bereikt.

- [x] Bijhouden welke tekst er in het berichtvak staat: de hash uit
      `Cjk_TextOverride` en de uitgevouwen tekst die de printer van het
      berichtvak krijgt.
- [x] Namen als `{PLAYER}` worden pas tijdens het spelen ingevuld. Daardoor
      kloppen vaste byteposities niet. De game loopt daarom de uitgevouwen
      tekst door en koppelt de woorden uit `zh_gloss.bin` op volgorde. Wat niet
      overeenkomt (een ingevulde naam) blijft een los, niet-aantikbaar stuk.
- [x] Bij meerdere pagina's (`\p`) alleen de pagina die nu in beeld is.
- [x] Een woordenboekpaneel in `3ds_bottom_ui.c`: de huidige zin groot, woorden
      aantikbaar; daaronder pinyin en betekenis van het gekozen woord; knoppen
      "Opslaan" en "Engels". Te openen via een knop op het onderscherm, en
      optioneel via een sneltoets.
- [x] (anders opgelost) Lettertype: de pinyin heeft klinkers met toontekens nodig (ā á ǎ à, ē é ě è,
      ī í ǐ ì, ō ó ǒ ò, ū ú ǔ ù, ǖ ǘ ǚ ǜ, ü). Die toevoegen via `tools/gen_font.py`
      uit hetzelfde WenQuanYi-lettertype. Opgelost zonder nieuwe glyphs: de
      letters komen uit het lettertype van de game en het paneel tekent de
      toonstreep erboven, zodat alle tekencodes gelijk blijven.
- [x] Opslaan in `sdmc:/woofer/vocab.jsonl` (gedeeld door alle Woofer-games),
      met `Woofer_BeginVocab` en `Woofer_SaveVocab`. Elk opgeslagen woord is
      één nieuwe regel die achteraan wordt toegevoegd. Dat is veilig op een
      SD-kaart: bij stroomuitval gaat hooguit de laatste regel verloren, nooit
      de hele lijst.
- [ ] Controle volgens `CLAUDE.md`: de build slaagt en
      `localize_chinese.py --check` geeft geen problemen. Daarna handmatig
      testen in Azahar of WooferCitra.

### Fase 3: de brug naar WooferCitra (protocol v1)

- [x] Protocol spelonafhankelijk vastgelegd in `docs/woofer-bridge/PROTOCOL.md`,
      in beide repo's.
- [x] Handdruk: de game vraagt `svcGetSystemInfo(0x574F4F46 'WOOF', 0)`.
      WooferCitra antwoordt met versie 1; een echte 3DS en andere emulators
      niet, en dan stuurt de game niets.
- [x] Game: `port/woofer_bridge.c` (spelonafhankelijk) en patch
      `0110-woofer-bridge.patch`: handdruk en `hello` bij het opstarten.
      Let op: `CtrLog_Write` stuurt alle logregels van de port al via
      `svcOutputDebugString`; de brug onderscheidt die door het voorvoegsel.
- [x] WooferCitra (core): `src/core/woofer/` herkent `WOOF1 `-regels in
      `SVC::OutputDebugString`, bewaart de laatste `hello` en `line`, geeft ze
      via een callback aan de frontend en beantwoordt de handdruk.
- [x] Game: `line` bij elke nieuwe pagina, `clear` bij sluiten, `saved` bij
      opslaan. Hangt af van fase 2 (bijhouden welke pagina in beeld is).

### Fase 4: Android-paneel in WooferCitra

- [x] JNI: de callback doorgeven aan Java (`NativeLibrary.onWooferMessage`,
      `org.citra.emu.woofer.WooferBridge`), met lezen en aanvullen van
      `vocab.jsonl` via de core (werkt ook met Android-opslagrechten via SAF).
- [x] Een inklapbaar paneel naast of onder het beeld met de huidige zin, de
      aantikbare woorden, pinyin en betekenis. Op een telefoon in landschap is
      daar ruim plek voor.
- [x] Uitspraak met de Android-spraakfunctie (`TextToSpeech`, zh-CN), per woord
      en voor de hele zin. Dit is een duidelijke meerwaarde boven de 3DS.
- [x] "Opslaan" via `WooferBridge.saveWord`: hetzelfde `vocab.jsonl` op de
      geëmuleerde SD-kaart, zodat de games en de emulator één lijst delen.
- [x] `WooferBridge.setPanelVisible` aanroepen als het paneel open of dicht
      gaat, zodat de game zijn eigen paneel kan aanpassen.
- [x] Een woordenlijstscherm in het hoofdmenu: zoeken, verwijderen, en export
      naar Anki (TSV met hanzi, pinyin, betekenis, zin en plek in het spel).

### Fase 5: leren

- [ ] Status per woord (nieuw, aan het leren, bekend). De game kan bekende
      woorden in het paneel anders kleuren, omdat hij `vocab.jsonl` zelf kan
      lezen.
- [x] HSK-niveau per woord, toe te voegen in de `gloss`-stap.
- [ ] Herhalen volgens spaced repetition in WooferCitra (eenvoudig SM-2).

## 5. Protocol en volgende games

Het protocol (handdruk, berichten `hello`, `line`, `clear`, `saved` en het
formaat van `vocab.jsonl`) staat in `docs/woofer-bridge/PROTOCOL.md`. Dat
bestand is in WooferCitra en in elke Woofer-game gelijk.

Uitgangspunt voor volgende games: de emulator blijft spelonafhankelijk en
krijgt alles van de game. Een nieuwe game neemt over:

| Onderdeel | Uit PokemonWoofer | Per game aan te passen |
|---|---|---|
| Brug | `port/woofer_bridge.c`, `.h` | `game`-id in `Woofer_Init` |
| Woorddata | `kit/zh_pinyin.py`, `zh_gloss.py`, `zh_gloss_bin.py` | tekstcodering en uitlezen van de dialogen |
| Tests | `scripts/test_port.sh`, `kit/test_zh_gloss.py` | eigen voorbeelddata |
| Woordenlijst | `sdmc:/woofer/vocab.jsonl` | niets |

## 6. Wat er gebeurt met eerder werk

| Onderdeel | Besluit |
|---|---|
| Plan versie 1 (OCR, CC-CEDICT in de app) | Vervangen door dit plan. Eventueel later terug als algemene functie voor andere games |
| Qt-code van Mistral (`src/citra_qt/dictionary`, wijzigingen in `main.*`) | Niet op voortbouwen. Voorstel: terugdraaien, zodat de branch alleen bevat wat we gebruiken |
| Datamodel van Mistral (hanzi, pinyin, vertaling, notities) | Terug te zien in `vocab.jsonl`, aangevuld met zin, plek en status |

## 7. Risico's

| Risico | Aanpak |
|---|---|
| Fouten in segmentatie of pinyin uit het taalmodel | Steekproef nalopen in fase 1; automatische controle dat elk woord exact in de zin voorkomt en elke pinyin bij de tekens past |
| `zh_gloss.bin` te groot voor het geheugen van een Old 3DS | Betekenissen ontdubbelen; alleen de index in het geheugen, de rest per tekst van de SD-kaart lezen |
| Ingevulde namen verstoren de koppeling van woorden | Koppelen op volgorde en niet op positie (fase 2) |
| Ruimte op het onderscherm conflicteert met bestaande schermen (tas, Pokédex, PokéNav) | Het paneel alleen tonen in de veldweergave en tijdens dialogen; elders een knop |
| Protocol loopt uit de pas tussen de repo's | Versienummer in het voorvoegsel; protocoldocument in beide repo's |
| Wijzigingen in de port gaan verloren omdat `build_tree.sh` die terugzet | Werken volgens `CLAUDE.md`: altijd eerst als patch opslaan in `patches/port/` |

## 8. Volgorde

1. Fase 1 (data). Uitkomst beoordelen op een steekproef.
2. Fase 2 (onderscherm). Hiermee is het doel bereikt, ook zonder WooferCitra.
3. Fase 3 en 4 (brug en Android-paneel), als de extra's van een telefoon
   gewenst zijn.
4. Fase 5 (leren) na een periode van echt gebruik.
