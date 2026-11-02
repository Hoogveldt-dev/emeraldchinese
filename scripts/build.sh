#!/usr/bin/env bash
# Bouwt PokemonWoofer: dist/PokemonWoofer.3dsx plus de vertaalkit in kit/.
#
#   scripts/build.sh                 # alles, in de vastgepinde Docker-omgeving
#   scripts/build.sh --native        # zonder Docker (devkitPro, host-gcc, Python 3.11+ met Pillow nodig)
#   JOBS=16 scripts/build.sh
#
# Stap 1 (hier, op de host): ROM controleren, de port en het lettertype ophalen.
# Stap 2 (scripts/build_tree.sh): patches, lettertype, Chinese teksten, compileren.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

lock() { python3 -c "import tomllib,sys;d=tomllib.load(open('woofer.lock','rb'));print(d['$1']['$2'])"; }

# 1. ROM
ROM=""
for f in roms/baserom.gba "roms/$(lock rom name)"; do [ -f "$f" ] && ROM="$f" && break; done
if [ -z "$ROM" ]; then
    echo "build: zet je Emerald-dump in roms/baserom.gba (zie roms/README.md)" >&2; exit 1
fi
SHA=$(sha1sum "$ROM" | cut -d' ' -f1)
if [ "$SHA" != "$(lock rom sha1)" ]; then
    echo "build: $ROM is niet de schone BPEE-dump (SHA-1 $SHA)" >&2; exit 1
fi
echo "build: ROM ok ($ROM)"

# 2. De port op de vastgepinde commit
PORT=build/emerald-3ds
COMMIT=$(lock port commit)
if [ ! -d "$PORT/.git" ]; then
    git clone -q "$(lock port repository)" "$PORT"
fi
if [ "$(git -C "$PORT" rev-parse HEAD)" != "$COMMIT" ]; then
    git -C "$PORT" fetch -q origin "$COMMIT" 2>/dev/null || git -C "$PORT" fetch -q origin
    git -C "$PORT" checkout -q --detach "$COMMIT"
fi
echo "build: port op ${COMMIT:0:12}"

# 2b. pokeemerald op de commit die de port pint (zo heeft de build zelf geen netwerk nodig)
TREE="$PORT/build/upstream"
plock() { python3 -c "import tomllib;d=tomllib.load(open('$PORT/upstream.lock','rb'));print(d['$1']['$2'])"; }
PE_COMMIT=$(plock pokeemerald commit)
if [ "$(git -C "$TREE" rev-parse HEAD 2>/dev/null)" != "$PE_COMMIT" ]; then
    mkdir -p "$TREE"
    [ -d "$TREE/.git" ] || { git -C "$TREE" init -q; git -C "$TREE" remote add origin "$(plock pokeemerald repository)"; }
    git -C "$TREE" fetch -q --depth 1 origin "$PE_COMMIT"
    git -C "$TREE" checkout -q --force --detach "$PE_COMMIT"
fi

# 3. Lettertype
FONT=build/font
if [ ! -f "$FONT/$(lock font bdf)" ]; then
    mkdir -p "$FONT"
    curl -sSL -o "$FONT/font.tgz" "$(lock font url)"
    echo "$(lock font sha256)  $FONT/font.tgz" | sha256sum -c --quiet
    tar xzf "$FONT/font.tgz" -C "$FONT"
fi

# 4. Bouwen
JOBS=${JOBS:-$(nproc)}
if [ "${1:-}" = "--native" ]; then
    JOBS=$JOBS scripts/build_tree.sh
    exit 0
fi
TAG=woofer-env:$(sha1sum "$PORT/upstream.lock" docker/Dockerfile | sha1sum | cut -c1-12)
if ! docker image inspect "$TAG" >/dev/null 2>&1; then
    # Docker Hub knijpt anonieme pulls af (429); dan dezelfde image via mirror.gcr.io.
    image() {
        local ref="$1" full="$1"
        [[ "$ref" == */* ]] || full="library/$ref"
        if docker image inspect "$ref" >/dev/null 2>&1 || docker pull -q "$ref" >/dev/null 2>&1; then
            echo "$ref"
        else
            docker pull -q "mirror.gcr.io/$full" >/dev/null && echo "mirror.gcr.io/$full"
        fi
    }
    PY_IMG=$(image "$(plock python image)")
    DKA_IMG=$(image "$(plock devkitarm image)")
    mkdir -p build/docker-ctx/wheels
    cp docker/Dockerfile build/docker-ctx/
    # Pillow vooraf op de host ophalen: de image-build hoeft dan niet naar PyPI.
    PILLOW=$(plock python pillow)
    ls build/docker-ctx/wheels/pillow-"$PILLOW"-*.whl >/dev/null 2>&1 || \
        python3 -m pip download -q --only-binary=:all: --no-deps --python-version 3.13 \
            --platform manylinux_2_28_x86_64 "pillow==$PILLOW" -d build/docker-ctx/wheels
    docker build -t "$TAG" \
        --build-arg PYTHON_IMAGE="$PY_IMG" \
        --build-arg DEVKITARM_IMAGE="$DKA_IMG" \
        --build-arg PILLOW="$(plock python pillow)" build/docker-ctx
fi
docker run --rm --network none -e HOME=/tmp -e JOBS="$JOBS" -v "$ROOT:/woofer" -w /woofer "$TAG" scripts/build_tree.sh
