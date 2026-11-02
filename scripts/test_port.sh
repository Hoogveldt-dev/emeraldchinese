#!/usr/bin/env bash
# Tests van de eigen C-code in port/ die zonder 3DS kan draaien (gewone cc).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
CC=${CC:-cc}
FLAGS="-std=gnu99 -Wall -Wextra -Werror -O2"
$CC $FLAGS -I"$ROOT/port" "$ROOT/port/woofer_bridge.c" "$ROOT/tests/port/woofer_bridge_test.c" -o "$TMP/woofer_bridge_test"
"$TMP/woofer_bridge_test" "$TMP"
$CC $FLAGS -I"$ROOT/port" "$ROOT/port/woofer_gloss.c" "$ROOT/tests/port/woofer_gloss_test.c" -o "$TMP/woofer_gloss_test"
"$TMP/woofer_gloss_test" "$ROOT/kit"
$CC $FLAGS -I"$ROOT/port" "$ROOT/port/woofer_dict.c" "$ROOT/port/woofer_gloss.c" "$ROOT/port/woofer_bridge.c" \
    "$ROOT/tests/port/woofer_dict_test.c" -o "$TMP/woofer_dict_test"
"$TMP/woofer_dict_test" "$ROOT/kit" "$TMP"
