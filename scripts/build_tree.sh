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

step "lettertype: 12-px CJK-glyphs en tekentabel"
$PY tools/gen_font.py "build/font/$BDF" out
cp out/3ds_cjk_font.c "$PORT/3ds_port/src/"

step "boom: pokeemerald + port (tools/bootstrap.py)"
# Altijd terug naar de schone, gepatchte decomp: de lokalisatie schrijft in de bronbestanden.
rm -f "$TREE/.emerald3ds-patches" "$TREE/src/data/region_map/region_map_entries.h"
(cd "$PORT" && $PY tools/bootstrap.py --python "$PY")
make -C "$TREE" tools -j"$JOBS"
make -C "$TREE" generated -j"$JOBS"

step "Chinese teksten in de boom zetten"
$PY tools/localize_chinese.py --tree "$TREE" --catalog catalog/zh_cn --table out/cjk_table.json

step "3DSX compileren"
make -C "$TREE/3ds_port" -j"$JOBS" PYTHON="$PY" PORT_LANG=en
mkdir -p dist
cp "$TREE/3ds_port/emerald3ds.3dsx" dist/PokemonWoofer.3dsx

step "vertaalkit bijwerken (kit/)"
cp "$TREE/charmap.txt" kit/charmap.txt
cp out/cjk_table.json kit/cjk_table.json
$PY tools/extract_dialogue.py "$TREE" kit/dialogue_en.jsonl

echo
echo "klaar: dist/PokemonWoofer.3dsx ($(du -h dist/PokemonWoofer.3dsx | cut -f1))"
