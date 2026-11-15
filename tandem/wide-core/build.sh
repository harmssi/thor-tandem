#!/bin/bash
# Builds dist/mgba_wide_libretro.so: the libretro mGBA core plus gba-duo's wide view (see README.md).
# Runs in a Debian container so the result needs no newer glibc than the RetroArch Flatpak's runtime has.
#   ./build.sh            needs Docker on a machine of the handheld's architecture (aarch64)
#   JOBS=2 WORK=/somewhere/else ./build.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${WORK:-$HERE/build}"  # sources and objects stay here between runs
mkdir -p "$WORK" "$HERE/dist"

docker run --rm -e JOBS="${JOBS:-4}" -e OWNER="$(id -u):$(id -g)" -v "$HERE":/src:ro -v "$WORK":/work -v "$HERE/dist":/dist debian:bookworm bash -euc '
MGBA=7a12d6d4b9acb14c0ae62c9166b6a2f3d08007f6  # libretro/mgba, the commit of the stock core (0.11-212-7a12d6d): same save states
LUA=lua-5.4.7
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq --no-install-recommends build-essential cmake git curl ca-certificates patch binutils >/dev/null
git config --global --add safe.directory "*"
cd /work
[ -d mgba ] || git clone -q https://github.com/libretro/mgba.git mgba
git -C mgba checkout -q -f $MGBA && git -C mgba clean -fdq
git -C mgba apply /src/mgba-libretro.diff
cp /src/tandem_wide.[ch] /src/gbaduo/*.[ch] mgba/src/platform/libretro/  # CMake takes every .c in that folder

if [ ! -f $LUA/src/liblua.a ]; then
    [ -f $LUA.tar.gz ] || curl -fsSLO https://www.lua.org/ftp/$LUA.tar.gz
    echo "9fbf5e28ef86c69858f6d3d34eccc32e911c1a28b4120ff3e84aaa70cfbf1e30  $LUA.tar.gz" | sha256sum -c -
    rm -rf $LUA && tar xzf $LUA.tar.gz
    patch -s -d $LUA -p1 < /src/lua-pattern-hook.diff
    # generic build as in the app: no dynamic loading; lua.c and luac.c are the command line tools
    (cd $LUA/src && rm lua.c luac.c && gcc -O2 -fPIC -DLUA_PATTERN_STEP_HOOK=gbaduo_pattern_step -c *.c && ar rcs liblua.a *.o)
fi

# GBADUO_HOST_TEST: script.c without Android/JNI; stddef.h: wide_affine.c uses size_t without it (fine with the libc of Android)
cmake -S mgba -B out -DCMAKE_BUILD_TYPE=Release -DLIBMGBA_ONLY=ON -DBUILD_LIBRETRO=ON \
    -DCMAKE_C_FLAGS="-DGBADUO_HOST_TEST -include stddef.h -I/work/$LUA/src" \
    -DCMAKE_C_STANDARD_LIBRARIES="/work/$LUA/src/liblua.a -lm -lpthread" >/dev/null
cmake --build out --target mgba_libretro -j"$JOBS"
cp out/mgba_libretro.so /dist/mgba_wide_libretro.so
echo "glibc needed: $(objdump -T /dist/mgba_wide_libretro.so | grep -o "GLIBC_[0-9.]*" | sort -uV | tail -1)"
chown -R "$OWNER" /work /dist
'
ls -l "$HERE/dist/mgba_wide_libretro.so"
