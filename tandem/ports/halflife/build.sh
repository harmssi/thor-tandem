#!/bin/bash
# Builds dist/: Xash3D FWGS and the game libraries of Half-Life, Opposing Force and Blue Shift for Linux aarch64, from
# the sources of the Android port "Thor Half-Life" (engine + three hlsdk trees with cl_dll/thor_deck.cpp). The deck's
# JNI bridge is replaced by ../tandem_deck.h (a local socket). No game data is involved; the game files stay the player's own.
# Runs in a Debian container so the result needs no newer glibc than the handheld has.
#   SRC=/path/to/thor-halflife ./build.sh     needs Docker on a machine of the handheld's architecture (aarch64)
#   JOBS=8 WORK=/somewhere/else SRC=… ./build.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "${SRC:?SRC=/path/to/thor-halflife (a checkout with its submodules)}" && pwd)"
WORK="${WORK:-$HERE/build}"  # a copy of the sources and the objects stay here between runs
mkdir -p "$WORK" "$HERE/dist"

docker run --rm -e JOBS="${JOBS:-$(nproc)}" -e OWNER="$(id -u):$(id -g)" -v "$SRC":/src:ro -v "$HERE/..":/ports:ro -v "$WORK":/work -v "$HERE/dist":/dist debian:bookworm bash -euc '
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq --no-install-recommends build-essential cmake python3 pkg-config rsync binutils \
    libsdl2-dev libfreetype-dev libfontconfig-dev libgl-dev libegl-dev >/dev/null
cd /work
rsync -a --delete --exclude .git /src/ src/  # a copy: the checkout itself is never changed
cp src/thor/android/app/src/main/assets/gamepad_presets/thor.cfg src/3rdparty/extras/xash-extras/gamepad_presets/  # the pad layout of the port
# Tandem ends a game with SIGTERM, which SDL turns into its quit event. The engine would answer that with the menu and its
# "really quit?" question and be killed a few seconds later, without saving its settings: quit at once instead.
sed -i "s/CL_RequestQuit( \"caught SDL_QUIT\" )/Sys_Quit( \"caught SDL_QUIT\" )/" src/engine/platform/sdl2/host_sdl2.c
grep -q "Sys_Quit( \"caught SDL_QUIT\" )" src/engine/platform/sdl2/host_sdl2.c

for game in portable opfor bshift; do
    cat /ports/halflife/deck_socket.inc >> src/3rdparty/hlsdk-$game/cl_dll/thor_deck.cpp
    cmake -S src/3rdparty/hlsdk-$game -B hlsdk-$game -DCMAKE_BUILD_TYPE=Release -D64BIT=ON -DCMAKE_CXX_FLAGS=-I/ports >/dev/null
    cmake --build hlsdk-$game -j"$JOBS"
done

cd src
python3 waf configure -o /work/engine -T release -8 --enable-bundled-deps
python3 waf build -j"$JOBS"
rm -rf /work/stage && python3 waf install --destdir=/work/stage >/dev/null
cd /work

rm -rf /dist/* && mkdir -p /dist/valve /dist/gearbox /dist/bshift
find stage -type f \( -name "*.so" -o -name xash3d -o -name extras.pk3 \) -exec cp {} /dist/ \;
# client and server library per game folder; "run" links them under the names the engine asks for
cp "$(find hlsdk-portable/cl_dll -name "client*.so")" /dist/valve/client.so;  cp "$(find hlsdk-portable/dlls -name "*.so")" /dist/valve/server.so
cp "$(find hlsdk-opfor/cl_dll -name "client*.so")" /dist/gearbox/client.so;   cp "$(find hlsdk-opfor/dlls -name "*.so")" /dist/gearbox/server.so
cp "$(find hlsdk-bshift/cl_dll -name "client*.so")" /dist/bshift/client.so;   cp "$(find hlsdk-bshift/dlls -name "*.so")" /dist/bshift/server.so
strip /dist/xash3d /dist/*.so /dist/*/*.so
echo "glibc needed: $(for f in /dist/xash3d /dist/*.so /dist/*/*.so; do objdump -T "$f"; done | grep -o "GLIBC_[0-9.]*" | sort -uV | tail -1)"
echo "libraries needed: $(for f in /dist/xash3d /dist/*.so /dist/*/*.so; do objdump -p "$f"; done | awk "/NEEDED/{print \$2}" | sort -u | tr "\n" " ")"
chown -R "$OWNER" /work /dist
'
ls -lR "$HERE/dist"
