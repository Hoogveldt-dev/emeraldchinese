# PokemonWoofer (简体中文)

`PokemonWoofer.3dsx`, gebouwd uit jouw eigen ROM (BPEE, SHA-1
`f3ae0881…07b7`, gecontroleerd) op basis van Emerald 3DS v0.5.0. Alleen voor
eigen gebruik: het bestand bevat speldata uit jouw cartridge, deel het dus
niet.

Deze build is van 2026-11-03 (commit van de repo hieronder) en bevat de
volledige Chinese dialoog, het woordenboek op het onderscherm en de
Woofer-brug naar WooferAzahar. Opnieuw maken: `scripts/build.sh`, de uitvoer
komt in `dist/`.

## Drie bestanden

| Bestand | Waar |
|---|---|
| `PokemonWoofer.3dsx` | openen via *File > Load File* |
| `zh_dialog.bin` | `sdmc/3ds/emerald3ds/` (de Chinese dialoog) |
| `zh_gloss.bin` | `sdmc/3ds/emerald3ds/` (woorden, pinyin, betekenis) |

De twee `.bin`-bestanden maak je met `cd kit && python3 translate_dialogue.py
build`; ze staan niet in git omdat ze uit de caches (wel in git) te maken
zijn. Zonder die bestanden speelt het spel met Engelse dialoog en zonder
woordenboek.

## Wat is Chinees

| Onderdeel | Status | Bron |
|---|---|---|
| Pokémonnamen (386), aanvallen, items, vaardigheden, types, naturen | Chinees, ingebouwd | Officiële zh-Hans namen (PokeAPI) |
| Pokédex-categorieën | Chinees, ingebouwd | Officiële genus zonder 宝可梦 |
| Plaatsnamen in Hoenn | Chinees, ingebouwd | Officiële namen |
| Alle gevechtsberichten (520) | Chinees, ingebouwd | Mijn vertaling, in de stijl van de officiële games |
| Menu's en systeemteksten (hoofdmenu, tas, winkel, team, pc, opslaan) | Chinees, ingebouwd | Mijn vertaling |
| Verhaaldialoog, NPC's, borden (6.982 teksten) | Chinees, uit `zh_dialog.bin` | DeepSeek, met controles nagelopen |
| Woorden met pinyin, betekenis en HSK (6.923 teksten, 15.756 woorden) | uit `zh_gloss.bin` | DeepSeek plus CC-CEDICT |

Het aanraakmenu op het onderscherm tekent de port zelf. De eigen labels
daarvan (zoals MAP en OPTION) blijven Engels.

## Spelen in Citra of Azahar

1. Open `PokemonWoofer.3dsx` via *File > Load File*. De speldata zit in het
   bestand zelf. Een `emerald3ds.pak` is niet nodig.
2. **Geluid:** zoals elke 3DS-homebrew heeft het spel `dspfirm.cdc` nodig in
   de SD-root (`sdmc/3ds/dspfirm.cdc`). Zie de geluidsinstructies op
   emerald-3ds.com. Zonder dat bestand draait het spel zonder geluid.
3. Zet *OPTION > TEXT SPEED* op MID of SLOW als je leestijd wilt.

## Het woordenboek

Tijdens een dialoog staat op het onderscherm de zin met de woorden los. Tik
een woord aan voor de pinyin en de betekenis, en bewaar het met één tik in
`sdmc:/woofer/vocab.jsonl`. Dat werkt in elke emulator en op een echte 3DS.

In WooferAzahar komt daar een paneel over het beeld bij, met uitspraak, de
woordenlijst buiten het spel en export naar Anki. Dat loopt via de
Woofer-brug (`docs/woofer-bridge/PROTOCOL.md`): de game stuurt per pagina de
zin en de woorden. Een andere emulator of een echte 3DS antwoordt niet op de
handdruk, en dan stuurt de game niets.

## De dialoog opnieuw vertalen (zh-kit)

De dialoog wordt tijdens het spelen vervangen vanuit één bestand. Opnieuw
compileren is dus niet nodig.

```
cd zh-kit
set ANTHROPIC_API_KEY=...        (Windows; op macOS/Linux: export ...)
python translate_dialogue.py translate --only birch_speech,LittlerootTown   (korte test)
python translate_dialogue.py translate                                      (alles)
python translate_dialogue.py build
```

* Elke OpenAI-compatibele API werkt ook, bijvoorbeeld DeepSeek:
  `--provider openai --base-url https://api.deepseek.com --model deepseek-chat`
  (met `OPENAI_API_KEY`).
* `--level simple` geeft eenvoudiger Chinees (rond HSK 3-4).
  `natural` (standaard) volgt de stijl van de officiële games.
* De vertaling wordt bewaard in `zh_cache.json`. Je kunt op elk moment
  stoppen en verdergaan. Opnieuw draaien probeert opnieuw wat mislukte.
  Met `status` zie je de voortgang.
* De officiële namen (Pokémon, aanvallen, items, plaatsen, personages) gaan
  als woordenlijst mee. Zo gebruikt de dialoog dezelfde termen als de
  gevechten en menu's.
* `build` regelt de regelafbreking (17 tekens per regel) en maakt
  `zh_dialog.bin`.

Kopieer `zh_dialog.bin` naar de SD-kaart van de emulator:
`sdmc/3ds/emerald3ds/zh_dialog.bin`. In Citra/Azahar ga je via
*File > Open Citra/Azahar Folder* naar `sdmc`. Het spel laadt het bestand
bij het opstarten. Teksten zonder vertaling blijven Engels.

## Technisch

* Chinese tekens zijn gecodeerd als twee bytes. Voor de eerste byte zijn 82
  codes gebruikt die in het Engelse spel niet voorkomen. Dat geeft 20.023
  tekens (heel GB2312 en meer). Ze komen uit WenQuanYi Bitmap Song 12px
  (GPL-2 met font-uitzondering): 12 pixels per teken, met de tekstschaduw
  van het spel zelf.
* De gewone tekstvakken, de HD-infovakken in gevechten en het onderscherm
  kunnen Chinese tekens tekenen.
* In `bron/` staan de patch op de port, de generatoren en de catalogi,
  zodat de build te reproduceren is.
