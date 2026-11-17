#!/bin/bash
# Builds dist/: the VCMI fork "Heroes III Thor Edition" (client and server, no launcher, no map editor) for Linux aarch64
# with its deck on Tandem's bottom screen. -DTHOR_TANDEM turns on the deck's Linux side (client/thor/ThorDeck.cpp): it
# talks through ../tandem_deck.h (a local socket) where the Android build uses JNI. dist/ also gets what the handheld
# lacks: Boost, TBB, squish, an SDL2_mixer without outside codecs and a small FFmpeg for the game's videos,
# and the fork's own tools that make VCMI data out of the Steam "HD Edition" (roe-bridge, see ./setup.py).
# No game data is involved: it stays the player's own.
# Runs in a Debian container so the result needs no newer glibc than the handheld has.
#   SRC=/path/to/thor-edition ./build.sh     needs Docker on a machine of the handheld's architecture (aarch64)
#   JOBS=8 WORK=/somewhere/else SRC=… ./build.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "${SRC:?SRC=/path/to/thor-edition (a checkout of the fork with its submodules)}" && pwd)"
WORK="${WORK:-$HERE/build}"  # downloads and objects stay here between runs
mkdir -p "$WORK" "$HERE/dist"

docker run --rm -e JOBS="${JOBS:-$(nproc)}" -e OWNER="$(id -u):$(id -g)" -v "$SRC":/src:ro -v "$HERE/..":/ports:ro -v "$WORK":/work -v "$HERE/dist":/dist debian:bookworm bash -euc '
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq --no-install-recommends build-essential cmake ninja-build binutils ca-certificates curl xz-utils pkg-config \
    libboost-dev libboost-date-time-dev libboost-filesystem-dev libboost-locale-dev libboost-program-options-dev zlib1g-dev libminizip-dev \
    libsdl2-dev libsdl2-image-dev libsdl2-ttf-dev libtbb-dev libsquish-dev >/dev/null
cd /work
DEPS=/work/deps

# SDL2_mixer with its built-in decoders only (the game has MP3 music and WAV sounds): the distribution one drags in a dozen codec libraries
if [ ! -f $DEPS/lib/libSDL2_mixer.so ]; then
    curl -fsSL https://github.com/libsdl-org/SDL_mixer/releases/download/release-2.8.1/SDL2_mixer-2.8.1.tar.gz | tar xz
    cmake -G Ninja -S SDL2_mixer-2.8.1 -B mixer -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=$DEPS -DCMAKE_INSTALL_LIBDIR=lib -DSDL2MIXER_VENDORED=OFF \
        -DSDL2MIXER_SAMPLES=OFF -DSDL2MIXER_OPUS=OFF -DSDL2MIXER_MOD=OFF -DSDL2MIXER_MIDI=OFF -DSDL2MIXER_WAVPACK=OFF -DSDL2MIXER_GME=OFF \
        -DSDL2MIXER_FLAC=OFF -DSDL2MIXER_VORBIS=STB >/dev/null
    cmake --build mixer -j"$JOBS" && cmake --install mixer >/dev/null
fi
# FFmpeg, small: only what plays the game videos (Theora/Vorbis in the HD Edition, Bink and Smacker in the original)
if [ ! -f $DEPS/lib/libavcodec.so ]; then
    curl -fsSL https://ffmpeg.org/releases/ffmpeg-6.1.2.tar.xz | tar xJ
    (cd ffmpeg-6.1.2 && ./configure --prefix=$DEPS --enable-shared --disable-static --disable-programs --disable-doc --disable-network \
        --disable-autodetect --disable-everything --enable-swscale --enable-swresample --enable-protocol=file \
        --enable-demuxer=ogg,bink,smacker,avi,mov,matroska --enable-parser=theora,vorbis,vp3 \
        --enable-decoder=theora,vp3,vorbis,bink,binkaudio_dct,binkaudio_rdft,smacker,smackaud,pcm_s16le >/dev/null && make -j"$JOBS" >/dev/null && make install >/dev/null)
fi

cmake -G Ninja -S /src -B /work/obj -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=$DEPS -DCMAKE_INSTALL_PREFIX=/work/stage -DENABLE_MONOLITHIC_INSTALL=ON \
    -DENABLE_LAUNCHER=OFF -DENABLE_EDITOR=OFF -DENABLE_TRANSLATIONS=OFF -DENABLE_MMAI=OFF -DENABLE_DISCORD=OFF -DENABLE_GITVERSION=OFF \
    -DCMAKE_CXX_FLAGS="-DTHOR_TANDEM -I/ports" >/work/configure.log
cmake --build /work/obj -j"$JOBS"
rm -rf /work/stage && cmake --install /work/obj >/dev/null

rm -rf /dist/* && cp -a /work/stage/. /dist/ && rm -rf /dist/share /dist/vcmibuilder  # desktop entries and a tool for other data
# the libraries the handheld does not have (or has in another version), next to the program (its RPATH is $ORIGIN)
for bin in /dist/vcmiclient /dist/vcmiserver /dist/*.so /dist/AI/*.so; do LD_LIBRARY_PATH=$DEPS/lib:/dist ldd "$bin"; done \
    | awk "/=> \\//{print \$3}" | grep -E "boost|tbb|squish|icu|SDL2_mixer|$DEPS/lib" | sort -u | xargs -I{} cp -L {} /dist/
# the fork'"'"'s own way from the Steam HD Edition to VCMI data (run by setup.py on the first start)
mkdir -p /dist/roe-bridge && cp /src/thor/roe-bridge/*.py /src/android/res/raw/roe_support.zip /dist/roe-bridge/ && cp /ports/homm3/setup.py /dist/
find /dist -type f \( -name "*.so*" -o -name vcmiclient -o -name vcmiserver \) -exec strip {} +
echo "glibc needed: $(find /dist -type f \( -name "*.so*" -o -name "vcmi*" \) -exec objdump -T {} + 2>/dev/null | grep -o "GLIBC_[0-9.]*" | sort -uV | tail -1)"
echo "libraries needed: $(find /dist -type f \( -name "*.so*" -o -name "vcmi*" \) -exec objdump -p {} + 2>/dev/null | awk "/NEEDED/{print \$2}" | sort -u | tr "\n" " ")"
chown -R "$OWNER" /work /dist
'
du -sh "$HERE/dist"; ls "$HERE/dist"
