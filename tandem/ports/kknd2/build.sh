#!/bin/bash
# Builds dist/: KKnD 2: Krossfire as "KKND2 Thor" (OpenRA with the mod OpenKrush, branch tandem-linux) for Linux aarch64
# with its deck on Tandem's bottom screen. thor/linux in the checkout is the Linux side of the Android app: the same start,
# the same controller code (thor/android/ThorInput.cs) and TandemDeck.cs, which feeds the deck through Tandem's deck
# socket where the Android app draws its own. Published self-contained (.NET 6 travels along, the handheld has none) with
# the engine and mod files in dist/game/ and Lua 5.1 in dist/lib/ (the handheld only has LuaJIT); SDL2, OpenAL and
# FreeType are the handheld's own. No game data is involved: it stays the player's own.
#   SRC=/path/to/thor-kknd2 ./build.sh     needs Docker on a machine of the handheld's architecture (aarch64)
#   WORK=/somewhere/else SRC=… ./build.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "${SRC:?SRC=/path/to/thor-kknd2 (a checkout of KKND2 Thor, branch tandem-linux)}" && pwd)"
WORK="${WORK:-$HERE/build}"  # sources, objects and NuGet packages stay here between runs
mkdir -p "$WORK" "$HERE/dist"

docker run --rm -e OWNER="$(id -u):$(id -g)" -v "$SRC":/src:ro -v "$WORK":/work -v "$HERE/dist":/dist debian:bookworm bash -euc '
export DEBIAN_FRONTEND=noninteractive DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1 NUGET_PACKAGES=/work/nuget DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1
apt-get update -qq && apt-get install -y -qq --no-install-recommends ca-certificates curl rsync unzip python3 binutils liblua5.1-0 >/dev/null
[ -x /work/dotnet/dotnet ] || { curl -sSL https://dot.net/v1/dotnet-install.sh -o /tmp/di.sh && bash /tmp/di.sh --channel 6.0 --install-dir /work/dotnet >/dev/null; }
export PATH=/work/dotnet:$PATH DOTNET_ROOT=/work/dotnet
rsync -a --delete --exclude .git --exclude bin/ --exclude obj/ --exclude /dist --exclude /thor/shots --exclude /thor/android/native-out \
    --exclude /thor/android/assets-out /src/ /work/src/
cd /work/src
[ -d engine/OpenRA.Game ] || { ./fetch-engine.sh && sh thor/apply-engine-patches.sh; }  # the engine pinned in mod.config, with the Thor changes
dotnet publish thor/linux/ThorKKND2.Linux.csproj -c Release -nologo -v q -o /work/out -p:TreatWarningsAsErrors=false
rm -rf /dist/* && cp -a /work/out/. /dist/ && rm -f /dist/*.pdb /dist/*.dll.config
rm -f /dist/SDL2.so /dist/soft_oal.so /dist/freetype6.so /dist/lua51.so  # the NuGet packages bring them for x86-64 only
mkdir -p /dist/lib /dist/game/engine/mods /dist/game/mods
cp -L /usr/lib/aarch64-linux-gnu/liblua5.1.so.0 /dist/lib/
cp -r engine/glsl engine/lua engine/VERSION engine/AUTHORS engine/COPYING "engine/global mix database.dat" /dist/game/engine/
cp -r engine/mods/common engine/mods/modcontent /dist/game/engine/mods/
for m in mods/*; do [ "$m" = mods/openkrush_gen1 ] || cp -r "$m" /dist/game/mods/; done  # gen1 (KKnD 1) is not part of it
echo "glibc needed: $(objdump -T /dist/ThorKKND2 /dist/*.so 2>/dev/null | grep -o "GLIBC_[0-9.]*" | sort -uV | tail -1)"
chown -R "$OWNER" /work /dist
'
du -sh "$HERE/dist"
