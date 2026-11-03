#!/usr/bin/env bash
# De eigenlijke build. Draait in de Docker-omgeving van scripts/build.sh,
# of native met --native. Verwacht build/emerald-3ds en build/font (build.sh).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT="$ROOT/build/emerald-3ds"
TREE="$PORT/build/upstream"
JOBS=${JOBS:-4}
PY=${PYTHON:-python3}
export WOOFER_PORT="$PORT"
BDF=$($PY -c "import tomllib;print(tomllib.load(open('woofer.lock','rb'))['font']['bdf'])")

step() { echo; echo "=== $*"; }

step "port: schoon maken en onze patches toepassen"
git -C "$PORT" checkout -q -- .
git -C "$PORT" clean -q -fd -- 3ds_port patches tools
cp patches/pokeemerald/*.patch "$PORT/patches/pokeemerald/"
for p in patches/port/*.patch; do git -C "$PORT" apply --whitespace=nowarn "$ROOT/$p"; done
cp port/*.c "$PORT/3ds_port/src/"
cp port/*.h "$PORT/3ds_port/src/"

step "lettertype: 12-px CJK-glyphs en tekentabel"
$PY tools/gen_font.py "build/font/$BDF" out
cp out/3ds_cjk_font.c "$PORT/3ds_port/src/"

step "boom: pokeemerald + port (tools/bootstrap.py)"
# Altijd terug naar de schone, gepatchte decomp: de lokalisatie schrijft in de bronbestanden.
rm -f "$TREE/.emerald3ds-patches" "$TREE/src/data/region_map/region_map_entries.h"
(cd "$PORT" && $PY tools/bootstrap.py --python "$PY")
make -C "$TREE" tools -j"$JOBS"
make -C "$TREE" generated -j"$JOBS"

# De sleutels van de ingebouwde teksten, nu de boom nog Engels is.
step "sleutels van de ingebouwde teksten (kit/zh_catalog.jsonl)"
$PY tools/catalog_texts.py "$TREE" kit/zh_catalog.jsonl

step "Chinese teksten in de boom zetten"
$PY tools/localize_chinese.py --tree "$TREE" --catalog catalog/zh_cn --table out/cjk_table.json

step "vertaalkit bijwerken (kit/)"
cp "$TREE/charmap.txt" kit/charmap.txt
cp out/cjk_table.json kit/cjk_table.json
$PY tools/extract_dialogue.py "$TREE" kit/dialogue_en.jsonl

# De dialoog en de woorden uit de caches (in git), zonder netwerk of API.
step "dialoog en woorden: zh_dialog.bin en zh_gloss.bin"
(cd kit && $PY translate_dialogue.py build)

# In de RomFS van de 3DSX, zodat één bestand genoeg is. 3ds_cjk.c en
# woofer_dict.c kijken eerst op sdmc:/3ds/emerald3ds/: een bestand daar wint,
# zodat een nieuwe vertaling te proberen is zonder opnieuw te compileren.
step "data in de 3DSX (RomFS)"
for f in zh_dialog.bin zh_gloss.bin; do
    if [ -f "kit/$f" ]; then
        cp "kit/$f" "$TREE/3ds_port/romfs/$f"
        echo "romfs/$f ($(du -h "kit/$f" | cut -f1))"
    else
        echo "kit/$f ontbreekt: de 3DSX krijgt hem niet mee" >&2
    fi
done

step "3DSX compileren"
# Weg met de oude 3DSX: anders ziet make de nieuwe RomFS-bestanden niet.
rm -f "$TREE/3ds_port/emerald3ds.3dsx"
make -C "$TREE/3ds_port" -j"$JOBS" PYTHON="$PY" PORT_LANG=en
mkdir -p dist
cp "$TREE/3ds_port/emerald3ds.3dsx" dist/PokemonWoofer.3dsx

echo
echo "klaar: dist/PokemonWoofer.3dsx ($(du -h dist/PokemonWoofer.3dsx | cut -f1))"
