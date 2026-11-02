# PokemonWoofer

Pokémon Emerald voor de 3DS (Citra / Azahar), omgebouwd tot leermiddel voor
Mandarijn via comprehensible input. Gebaseerd op de port
[ZallaxDev/emerald-3ds](https://github.com/ZallaxDev/emerald-3ds) (v0.5.0).

Deze repo bevat alleen **onze** wijzigingen: patches, generatoren, Chinese
catalogi en de vertaalkit. Speldata zit er niet in. De build haalt de port
op, voegt onze laag toe en compileert met jouw eigen ROM-dump erbij.

## Snel starten

```bash
# 1. eigen dump neerzetten (schone BPEE, zie roms/README.md)
cp ~/pad/naar/emerald.gba roms/baserom.gba

# 2. bouwen (Docker met de vastgepinde devkitARM-omgeving)
scripts/build.sh            # of: scripts/build.sh --native

# 3. spelen
#    dist/PokemonWoofer.3dsx openen in Azahar/Citra (File > Load File)
```

De eerste build duurt lang (Docker-image, decomp-tools, ca. 2.000
C-bestanden). Daarna gaat het incrementeel.

## Structuur

| Pad | Wat |
|---|---|
| `woofer.lock` | vastgepinde versies: port-commit, ROM-hash, lettertype |
| `scripts/build.sh` | instap: ROM-check, port en lettertype ophalen, Docker |
| `scripts/build_tree.sh` | de eigenlijke build (patches, font, teksten, make) |
| `patches/pokeemerald/` | wijzigingen aan de decomp (`src/text.c` enz.), gaan mee met de bootstrap van de port |
| `patches/port/` | wijzigingen aan `3ds_port/` (onderscherm, gevechts-HUD, hooks) |
| `port/` | nieuwe C-bestanden voor `3ds_port/src/` (`3ds_cjk.c`: dialoogtabel) |
| `tools/gen_font.py` | WenQuanYi 12 px BDF naar `3ds_cjk_font.c` + `cjk_table.json` |
| `tools/localize_chinese.py` | zet de catalogi in de decomp-boom |
| `tools/gen_names.py` | officiële zh-Hans namen (PokeAPI-CSV) naar catalogi |
| `tools/tsv2cat.py` | `label<TAB>tekst` naar catalogus met hashes |
| `tools/extract_dialogue.py` | Engelse dialoog + hashes voor de kit |
| `tools/lp.py` | shim naar de catalogushelpers van de port |
| `catalog/zh_cn/` | ingebouwde Chinese teksten (namen, gevechten, menu's) |
| `catalog/tsv/` | bron van de handvertaalde catalogi (strings, gevechtsberichten) |
| `kit/` | dialoogvertaler: maakt `zh_dialog.bin` voor op de SD-kaart |

Niet in git (`.gitignore`): `roms/`, `build/`, `dist/`, `out/` en de
gegenereerde kitbestanden.

## Sleutelen

**Een ingebouwde tekst aanpassen** (menu, gevechtsbericht): bewerk
`catalog/tsv/*.tsv` en zet om naar een catalogus, of bewerk
`catalog/zh_cn/...txt` direct. Daarna `scripts/build.sh`.

```bash
python3 tools/tsv2cat.py build/emerald-3ds/build/upstream src/battle_message.c \
    catalog/tsv/battle_message.tsv catalog/zh_cn/src/battle_message.c.txt
```

`tsv2cat` leest de Engelse bron uit een boom die nog niet gelokaliseerd is.
Reset die eerst met `git -C build/emerald-3ds/build/upstream checkout -- src`.

**Engine of port wijzigen**: werk in `build/emerald-3ds/build/upstream`,
en zet je wijziging daarna terug als patch:

```bash
cd build/emerald-3ds/build/upstream
git diff -- src include > ../../../../patches/pokeemerald/9101-mijn-wijziging.patch
```

Wijzigingen in `3ds_port/` maak je in `build/emerald-3ds/3ds_port` en sla je
op met `git -C build/emerald-3ds diff -- 3ds_port > patches/port/0101-....patch`.
Let op: `build_tree.sh` zet de port bij elke build schoon terug, dus eerst
de patch opslaan.

**Dialoog vertalen** (geen hercompilatie nodig): zie `kit/README.md`.

## Spelen

* Open `dist/PokemonWoofer.3dsx` in Azahar (opvolger van Citra) of Citra.
* Geluid: `dspfirm.cdc` in `sdmc/3ds/dspfirm.cdc` (zie emerald-3ds.com).
* Dialoogvertaling: `kit/zh_dialog.bin` naar `sdmc/3ds/emerald3ds/zh_dialog.bin`.
* Log: lege `sdmc/3ds/emerald3ds/debug.txt` aanmaken, dan schrijft het spel
  `port.log`.

## Licenties

De port valt onder de licenties van emerald-3ds (`LICENSE-PORT.md` daar).
Het lettertype is WenQuanYi Bitmap Song (GPL-2 met font-uitzondering).
Gebouwde bestanden bevatten speldata uit je eigen cartridge: niet delen.
