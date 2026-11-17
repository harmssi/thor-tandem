#!/bin/bash
# Builds dist/OpenAoK: the engine OpenAoK (Age of Kings) for Linux aarch64 with the Thor deck on Tandem's bottom screen.
# The engine's Android deck talks through JNI; deck_socket.inc puts ../tandem_deck.h (a local socket) in its place, and
# -DOPENAOK_TANDEM turns on the handheld's controller layout. No game data is involved: it stays the player's own.
# Runs in a Debian container so the result needs no newer glibc than the handheld has.
#   SRC=/path/to/openaok ./build.sh     needs Docker on a machine of the handheld's architecture (aarch64)
#   JOBS=8 WORK=/somewhere/else SRC=… ./build.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "${SRC:?SRC=/path/to/openaok (a checkout of the engine)}" && pwd)"
WORK="${WORK:-$HERE/build}"  # a copy of the sources and the objects stay here between runs
mkdir -p "$WORK" "$HERE/dist"

docker run --rm -e JOBS="${JOBS:-$(nproc)}" -e OWNER="$(id -u):$(id -g)" -v "$SRC":/src:ro -v "$HERE/..":/ports:ro -v "$WORK":/work -v "$HERE/dist":/dist debian:bookworm bash -euc '
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq --no-install-recommends build-essential cmake ninja-build rsync binutils libsdl2-dev libfreetype-dev >/dev/null
cd /work
mkdir -p src
rsync -a --delete /src/CMakeLists.txt /src/src /src/third_party src/  # a copy: the checkout itself is never changed
cat /ports/aok/deck_socket.inc >> src/src/thor/Thor.cpp
cmake -G Ninja -S src -B obj -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_FLAGS="-DOPENAOK_TANDEM -I/ports" >/dev/null
cmake --build obj -j"$JOBS"
rm -rf /dist/* && cp obj/OpenAoK /dist/ && strip /dist/OpenAoK
echo "glibc needed: $(objdump -T /dist/OpenAoK | grep -o "GLIBC_[0-9.]*" | sort -uV | tail -1)"
echo "libraries needed: $(objdump -p /dist/OpenAoK | awk "/NEEDED/{print \$2}" | tr "\n" " ")"
chown -R "$OWNER" /work /dist
'
ls -l "$HERE/dist"
