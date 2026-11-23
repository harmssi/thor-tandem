#!/bin/bash
# Builds Toravo Tandem OS (ARM64 bootc container image + bootable AYN Thor raw .img.xz)
# Run on an ARM64 Linux host with Docker (e.g. harmssi-ai DGX Spark).
#
# Usage:
#   ./os/build-image.sh              # builds OCI image + dist/toravo-tandem-os-<ver>-arm64.img.xz
#   ./os/build-image.sh --oci-only   # builds only the bootc OCI image
#   IMAGE_TAG=ghcr.io/harmssi/toravo-tandem-os:latest ./os/build-image.sh --push
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VER="$(tr -d ' \n' < "$ROOT/tandem/VERSION")"
IMAGE_TAG="${IMAGE_TAG:-localhost/toravo-tandem-os:$VER}"
OUT_DIR="$ROOT/dist"
IMG_BASE="toravo-tandem-os-${VER}-arm64"
OCI_ONLY=0
PUSH=0

for arg in "$@"; do
    case "$arg" in
        --oci-only) OCI_ONLY=1 ;;
        --push) PUSH=1 ;;
    esac
done

mkdir -p "$OUT_DIR"

echo "== [1/3] Baue bootc-Image $IMAGE_TAG (FROM ghcr.io/armada-os/armada:beta) =="
docker build \
    --platform linux/arm64 \
    -f "$ROOT/os/Containerfile" \
    -t "$IMAGE_TAG" \
    -t "localhost/toravo-tandem-os:latest" \
    "$ROOT"

if [ "$PUSH" = 1 ]; then
    echo "== Push $IMAGE_TAG =="
    docker push "$IMAGE_TAG"
fi

if [ "$OCI_ONLY" = 1 ]; then
    echo "Fertig (OCI-only): $IMAGE_TAG"
    exit 0
fi

echo "== [2/3] Erzeuge bootfähiges AYN-Thor-Disk-Image (.img) via bootc install to-disk =="
RAW_IMG="$OUT_DIR/${IMG_BASE}.img"
SIZE_GB="${IMG_SIZE_GB:-16}"
rm -f "$RAW_IMG" "${RAW_IMG}.xz" "${RAW_IMG}.xz.sha256"
truncate -s "${SIZE_GB}G" "$RAW_IMG"

# bootc install to-disk --via-loopback writes GPT + EFI + /boot + Btrfs root directly from the built OCI image!
docker run --rm --privileged \
    --pid=host \
    --security-opt label=type:unconfined_t \
    -v /dev:/dev \
    -v /var/lib/containers:/var/lib/containers \
    -v "$OUT_DIR:/output" \
    "$IMAGE_TAG" \
    bootc install to-disk \
        --via-loopback \
        --filesystem btrfs \
        --wipe \
        --generic-image \
        --skip-fetch-check \
        "/output/${IMG_BASE}.img"

echo "== [3/3] Komprimiere ${IMG_BASE}.img -> ${IMG_BASE}.img.xz (multithreaded) =="
xz -T0 -6 -f "$RAW_IMG"
(cd "$OUT_DIR" && sha256sum "${IMG_BASE}.img.xz" > "${IMG_BASE}.img.xz.sha256")
ls -lh "$OUT_DIR/${IMG_BASE}.img.xz" "$OUT_DIR/${IMG_BASE}.img.xz.sha256"
echo "FERTIG: $OUT_DIR/${IMG_BASE}.img.xz (einfach mit Balena Etcher / Rufus / Raspberry Pi Imager auf SD oder USB flashen!)"
