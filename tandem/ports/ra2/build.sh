#!/bin/bash
# Builds dist/ra2engine: the RA2 Engine fork "Thor RA2" (Red Alert 2 / Yuri's Revenge) for Linux aarch64 with its command
# deck on Tandem's bottom screen. -DRA2_TANDEM turns on the engine's Linux handheld side (engine/thor.cpp): the deck
# talks through ../tandem_deck.h (a local socket) where the Android build uses JNI. dist/ also gets the SDL2 the engine
# pins and downloads itself: the handheld's own "SDL2" is sdl2-compat on SDL3, which leaves the game picture black (the
# engine lights the map through render targets under a logical size). No game data is involved: it stays the player's own.
# Runs in a Debian container so the result needs no newer glibc than the handheld has.
#   SRC=/path/to/thor-ra2 ./build.sh     needs Docker on a machine of the handheld's architecture (aarch64)
#   JOBS=8 WORK=/somewhere/else SRC=… ./build.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "${SRC:?SRC=/path/to/thor-ra2 (a checkout of the engine)}" && pwd)"
WORK="${WORK:-$HERE/build}"  # the objects stay here between runs
mkdir -p "$WORK" "$HERE/dist"

docker run --rm -e JOBS="${JOBS:-$(nproc)}" -e OWNER="$(id -u):$(id -g)" -v "$SRC":/src:ro -v "$HERE/..":/ports:ro -v "$WORK":/work -v "$HERE/dist":/dist debian:bookworm bash -euc '
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq --no-install-recommends build-essential cmake ninja-build binutils ca-certificates pkg-config \
    libx11-dev libxext-dev libxcursor-dev libxi-dev libxrandr-dev libxfixes-dev libxss-dev libegl1-mesa-dev libgles2-mesa-dev libgl1-mesa-dev \
    libpulse-dev libasound2-dev libpipewire-0.3-dev libudev-dev libdbus-1-dev >/dev/null  # what SDL2 needs for X11, GL, sound and the controller
cmake -G Ninja -S /src -B /work/obj -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_FLAGS="-DRA2_TANDEM -I/ports" >/dev/null
cmake --build /work/obj -j"$JOBS" --target ra2engine
rm -rf /dist/*
cp -L /work/obj/ra2engine /work/obj/_deps/sdl2-build/libSDL2-2.0.so.0 /dist/
strip /dist/ra2engine /dist/libSDL2-2.0.so.0
echo "glibc needed: $(objdump -T /dist/ra2engine | grep -o "GLIBC_[0-9.]*" | sort -uV | tail -1)"
echo "libraries needed: $(objdump -p /dist/ra2engine | awk "/NEEDED/{print \$2}" | tr "\n" " ")"
chown -R "$OWNER" /work /dist
'
ls -l "$HERE/dist"
