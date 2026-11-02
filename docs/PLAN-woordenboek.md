# Woordenboekfunctie: bouwplan (WooferCitra + PokemonWoofer)

Status: voorstel, versie 2 (2026-11-02). Vervangt versie 1, die uitging van
screenshots en tekstherkenning (OCR).

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
 +---------------------------+           | -> sdmc:/3ds/emerald3ds/vocab.jsonl|
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

- [ ] `translate_dialogue.py` uitbreiden met een stap `gloss`. Per vertaalde
      tekst: een lijst woorden met per woord de tekens, pinyin met toontekens
      en een korte Engelse betekenis (eventueel ook Nederlands).
- [ ] Werkwijze: eerst automatisch segmenteren en pinyin bepalen, daarna het
      taalmodel laten controleren en verbeteren, met de hele zin en de Engelse
      bron als context. Dat vangt woorden met meerdere uitspraken (行, 了, 得,
      长, 重) en spelnamen uit `glossary.json`.
- [ ] Hervatbaar via een cache, net als `zh_cache.json`.
- [ ] `build` maakt naast `zh_dialog.bin` een `zh_gloss.bin`, met dezelfde
      hash als sleutel. Betekenissen worden ontdubbeld in één tabel, zodat het
      bestand klein blijft voor een Old 3DS.
- [ ] Controle: `--only birch_speech,LittlerootTown` en de resultaten met de
      hand nalopen. Pas daarna alles verwerken.
- [ ] Later dezelfde gegevens voor de ingebouwde catalogi (`catalog/zh_cn`):
      menu's en gevechtsberichten.

### Fase 2: woordenboek op het onderscherm (PokemonWoofer, port)

Na deze fase is het doel bereikt.

- [ ] Bijhouden welke tekst er in het berichtvak staat: de hash uit
      `Cjk_TextOverride` en de uitgevouwen tekst die de printer van het
      berichtvak krijgt.
- [ ] Namen als `{PLAYER}` worden pas tijdens het spelen ingevuld. Daardoor
      kloppen vaste byteposities niet. De game loopt daarom de uitgevouwen
      tekst door en koppelt de woorden uit `zh_gloss.bin` op volgorde. Wat niet
      overeenkomt (een ingevulde naam) blijft een los, niet-aantikbaar stuk.
- [ ] Bij meerdere pagina's (`\p`) alleen de pagina die nu in beeld is.
- [ ] Een woordenboekpaneel in `3ds_bottom_ui.c`: de huidige zin groot, woorden
      aantikbaar; daaronder pinyin en betekenis van het gekozen woord; knoppen
      "Opslaan" en "Engels". Te openen via een knop op het onderscherm, en
      optioneel via een sneltoets.
- [ ] Lettertype: de pinyin heeft klinkers met toontekens nodig (ā á ǎ à, ē é ě è,
      ī í ǐ ì, ō ó ǒ ò, ū ú ǔ ù, ǖ ǘ ǚ ǜ, ü). Die toevoegen via `tools/gen_font.py`
      uit hetzelfde WenQuanYi-lettertype.
- [ ] Opslaan als `sdmc:/3ds/emerald3ds/vocab.jsonl`. Elk opgeslagen woord is
      één nieuwe regel die achteraan wordt toegevoegd. Dat is veilig op een
      SD-kaart: bij stroomuitval gaat hooguit de laatste regel verloren, nooit
      de hele lijst.
- [ ] Controle volgens `CLAUDE.md`: de build slaagt en
      `localize_chinese.py --check` geeft geen problemen. Daarna handmatig
      testen in Azahar of WooferCitra.

### Fase 3: de brug naar WooferCitra (protocol v1)

- [ ] Game: bij elke nieuwe pagina in het berichtvak één regel sturen via
      `svcOutputDebugString`, met het voorvoegsel `WOOF1 ` en daarna JSON (zie
      paragraaf 5). Dit staat los van `CtrLog_Write`, dat alleen werkt als
      `debug.txt` bestaat.
- [ ] Ook een regel sturen bij elk woord dat in de game wordt opgeslagen, zodat
      WooferCitra direct bijwerkt.
- [ ] WooferCitra (core): in `SVC::OutputDebugString` regels met `WOOF1 `
      herkennen en doorgeven via een callback aan de frontend, op dezelfde
      manier als `VideoCore::g_screenshot_complete_callback`. Andere regels gaan
      zoals nu naar de log.
- [ ] Het protocoldocument in beide repo's zetten.

### Fase 4: Android-paneel in WooferCitra

- [ ] JNI: de callback doorgeven aan Java (`NativeLibrary`).
- [ ] Een inklapbaar paneel naast of onder het beeld met de huidige zin, de
      aantikbare woorden, pinyin en betekenis. Op een telefoon in landschap is
      daar ruim plek voor.
- [ ] Uitspraak met de Android-spraakfunctie (`TextToSpeech`, zh-CN), per woord
      en voor de hele zin. Dit is een duidelijke meerwaarde boven de 3DS.
- [ ] "Opslaan" schrijft naar hetzelfde `vocab.jsonl` op de geëmuleerde SD-kaart,
      zodat de game en de emulator één lijst delen.
- [ ] Een woordenlijstscherm in het hoofdmenu: zoeken, verwijderen, en export
      naar Anki (TSV met hanzi, pinyin, betekenis, zin en plek in het spel).

### Fase 5: leren

- [ ] Status per woord (nieuw, aan het leren, bekend). De game kan bekende
      woorden in het paneel anders kleuren, omdat hij `vocab.jsonl` zelf kan
      lezen.
- [ ] HSK-niveau per woord, toe te voegen in de `gloss`-stap.
- [ ] Herhalen volgens spaced repetition in WooferCitra (eenvoudig SM-2).

## 5. Protocol v1 (game naar emulator)

Eén regel per bericht via `svcOutputDebugString`, UTF-8:

```
WOOF1 {"t":"line","h":"6b8a1f0c9e2d4a17","zh":"勇者啊，你终于来了。","en":"Ah, hero, you have finally come.","w":[{"s":"勇者","p":"yǒngzhě","g":"hero"},{"s":"啊","p":"a","g":"(particle)"},{"s":"，"},{"s":"你","p":"nǐ","g":"you"},{"s":"终于","p":"zhōngyú","g":"finally"},{"s":"来","p":"lái","g":"to come"},{"s":"了","p":"le","g":"(completed action)"},{"s":"。"}],"loc":"LittlerootTown"}
WOOF1 {"t":"saved","s":"勇者","p":"yǒngzhě"}
```

- `t`: soort bericht (`line` of `saved`). Onbekende soorten worden genegeerd.
- `h`: de hash van de tekst, zoals in `zh_dialog.bin`.
- `w`: woorden op volgorde. Stukken zonder `p` (leestekens, namen) zijn niet
  aantikbaar.
- `loc`: de groep uit `dialogue_en.jsonl`, als plek in het spel.
- Het versienummer zit in het voorvoegsel. Een nieuwe versie wordt `WOOF2`, en
  een emulator die die niet kent negeert hem.
- Maximale lengte: wat in één aanroep past. Een te lange regel wordt niet
  afgekapt maar zonder `en` opnieuw gestuurd.

### Woordenlijst `vocab.jsonl`

Eén JSON-object per regel:

```json
{"v":1,"s":"勇者","p":"yǒngzhě","g":"hero","zh":"勇者啊，你终于来了。","en":"Ah, hero, you have finally come.","loc":"LittlerootTown","at":"2026-11-02T14:03:00Z","status":"new"}
```

Wijzigen of verwijderen gebeurt door een nieuwe regel met hetzelfde woord
achteraan te zetten (`"status":"deleted"` voor verwijderen). Wie het bestand
leest, neemt per woord de laatste regel. Zo hoeft niemand ooit het hele bestand
te herschrijven.

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
