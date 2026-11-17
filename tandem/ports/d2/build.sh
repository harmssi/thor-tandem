#!/bin/bash
# Builds dist/ for Diablo II (Thor D2, a fork of D2Android): the mod (d2android-mod.dll + its loader D2Android.exe),
# D2DX (glide3x.dll), PlugY and placeholder-game.exe exactly as a Thor D2 APK carries them (tested builds), d2install.exe
# from the checkout's branch tandem-linux (it hands the CD key to Blizzard's installer in memory, not on the command line;
# a 32-bit Windows program, so any machine with i686-w64-mingw32-gcc builds it), the pinned checksums of the installers
# and of 1.13d, setup.py, pad.py (the controller) and PlugY.ini. No game data is involved: setup.py installs it from Blizzard's own
# installers with the player's CD keys.
#   SRC=/path/to/thor-d2 APK=/path/to/ThorD2-0.1.7.apk ./build.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "${SRC:?SRC=/path/to/thor-d2 (checkout, branch tandem-linux)}" && pwd)"
APK="${APK:?APK=/path/to/ThorD2-<version>.apk}"
CC="${CC:-i686-w64-mingw32-gcc}"
D="$HERE/dist"
rm -rf "$D"; mkdir -p "$D/mod" "$D/install" "$D/licenses"

FLAGS=(-O2 -s -std=gnu11 -Wall -Wextra -Wno-unused-parameter -Wno-cast-function-type -static-libgcc -fno-asynchronous-unwind-tables)
"$CC" "${FLAGS[@]}" -mwindows -o "$D/install/d2install.exe" "$SRC/tools/installer/d2install.c" -luser32
RES="$(mktemp -d)"; trap 'rm -rf "$RES"' EXIT
unzip -q -o "$APK" 'assets/d2/d2dx/*' 'assets/d2/plugy/*' 'assets/d2/mod/*' 'assets/d2/install/placeholder-game.exe' -d "$RES"
cp "$RES"/assets/d2/mod/* "$D/mod/"; cp "$RES/assets/d2/install/placeholder-game.exe" "$D/install/"

A="$SRC/winlator/app/src/main/assets"
cp "$A"/install/installer-sha256-*.txt "$A"/checksums-113d*.txt "$D/install/"
cp "$RES/assets/d2/d2dx/glide3x.dll" "$RES/assets/d2/plugy/PlugY.dll" "$D/"
mkdir -p "$D/PlugY"; cp "$RES"/assets/d2/plugy/PlugY/* "$D/PlugY/"
cp "$RES/assets/d2/d2dx/LICENSE.txt" "$D/licenses/D2DX-LICENSE.txt"; cp "$RES/assets/d2/plugy/LICENSE.txt" "$D/licenses/PlugY-LICENSE.txt"
cp "$SRC/LICENSE" "$D/licenses/ThorD2-LICENSE.txt"
cp "$HERE/setup.py" "$HERE/pad.py" "$HERE/PlugY.ini" "$D/"
cp -r "$HERE/art" "$D/"  # tile art for Tandem (the app icon of Thor D2)
python3 "$D/setup.py" --selftest && python3 "$D/pad.py" --selftest
ls -lR "$D" | head -40
