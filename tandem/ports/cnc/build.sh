#!/bin/bash
# Builds dist/vanillatd and dist/vanillara: the Vanilla Conquer fork "Thor Conquer" (Command & Conquer: Tiberian Dawn and
# Red Alert) for Linux aarch64 with its command deck on Tandem's bottom screen. -DTHOR_TANDEM=ON builds the code paths of
# the fork's Android version (controller, 960x540 map view, deck channel) and common/thor_tandem.cpp, which talks to the
# deck through ../tandem_deck.h (a local socket) where the Android build uses JNI. No game data is involved: it stays
# the player's own. Runs in a Debian container so the result needs no newer glibc than the handheld has; SDL2 and
# OpenAL are the handheld's own (libSDL2-2.0.so.0, libopenal.so.1).
#   SRC=/path/to/thor-conquer ./build.sh     needs Docker on a machine of the handheld's architecture (aarch64)
#   JOBS=8 WORK=/somewhere/else SRC=… ./build.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "${SRC:?SRC=/path/to/thor-conquer (a checkout of the engine)}" && pwd)"
WORK="${WORK:-$HERE/build}"  # the objects stay here between runs
mkdir -p "$WORK" "$HERE/dist"

docker run --rm -e JOBS="${JOBS:-$(nproc)}" -e OWNER="$(id -u):$(id -g)" -v "$SRC":/src:ro -v "$HERE/..":/ports:ro -v "$WORK":/work -v "$HERE/dist":/dist debian:bookworm bash -euc '
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq --no-install-recommends build-essential cmake ninja-build binutils ca-certificates pkg-config git \
    libsdl2-dev libopenal-dev >/dev/null
cmake -G Ninja -S /src -B /work/obj -DCMAKE_BUILD_TYPE=Release -DTHOR_TANDEM=ON -DCMAKE_CXX_FLAGS="-I/ports" >/dev/null
cmake --build /work/obj -j"$JOBS" --target VanillaTD VanillaRA
rm -rf /dist/*
cp -L /work/obj/vanillatd /work/obj/vanillara /dist/
strip /dist/vanillatd /dist/vanillara
echo "glibc needed: $(objdump -T /dist/vanillara | grep -o "GLIBC_[0-9.]*" | sort -uV | tail -1)"
echo "libraries needed: $(objdump -p /dist/vanillara | awk "/NEEDED/{print \$2}" | tr "\n" " ")"
chown -R "$OWNER" /work /dist
'
ls -l "$HERE/dist"
