#!/bin/bash
# Patches an official ArmadaOS AYN Thor .img.gz into a ready-to-flash Toravo Tandem OS .img.xz
# Preserves 100% of ArmadaOS's OpenABL/EFI/kernel/Btrfs layout and bootc update support while
# pre-installing Toravo Tandem into the image so it boots straight into Tandem on first start.
#
# Usage: sudo ./os/patch-armada-img.sh /path/to/armada-20261109.img.gz
set -euo pipefail

[ $# -ge 1 ] || { echo "Verwendung: sudo $0 <armada-*.img.gz>" >&2; exit 1; }
[ "$(id -u)" = 0 ] || { echo "Bitte mit sudo ausführen." >&2; exit 1; }

BASE_GZ="$1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VER="$(tr -d ' \n' < "$ROOT/tandem/VERSION")"
OUT_DIR="$ROOT/dist"
IMG_BASE="toravo-tandem-os-${VER}-arm64"
RAW_IMG="$OUT_DIR/${IMG_BASE}.img"
MNT="$(mktemp -d)"
LOOP=""

cleanup() {
    set +e
    mountpoint -q "$MNT" && umount -R "$MNT"
    [ -n "$LOOP" ] && losetup -d "$LOOP"
    rm -rf "$MNT"
}
trap cleanup EXIT

mkdir -p "$OUT_DIR"
rm -f "$RAW_IMG" "${RAW_IMG}.xz" "${RAW_IMG}.xz.sha256"

echo "== [1/4] Entpacke $(basename "$BASE_GZ") -> $(basename "$RAW_IMG") =="
gzip -dc "$BASE_GZ" > "$RAW_IMG"

echo "== [2/4] Hänge Btrfs-Root-Partition ein =="
LOOP="$(losetup -fP --show "$RAW_IMG")"
PART=""
for p in "${LOOP}"p*; do
    FSTYPE="$(blkid -o value -s TYPE "$p" 2>/dev/null || true)"
    if [ "$FSTYPE" = "btrfs" ]; then
        PART="$p"
        break
    fi
done
[ -n "$PART" ] || { echo "Keine Btrfs-Partition im Image gefunden!" >&2; exit 1; }
echo "Gefunden: $PART (btrfs)"
mount -o compress=zstd "$PART" "$MNT"

echo "== [3/4] Installiere Toravo Tandem $VER + Autostart-Hook ins Image =="
# Locate the var/home/armada or home/armada directory inside the Btrfs subvolume tree
HOME_DIR=""
for cand in \
    "$MNT/home/armada" \
    "$MNT/var/home/armada" \
    "$MNT/ostree/deploy/default/var/home/armada" \
    "$MNT/root/var/home/armada"; do
    if [ -d "$cand" ]; then
        HOME_DIR="$cand"
        break
    fi
done
if [ -z "$HOME_DIR" ]; then
    HOME_DIR="$(find "$MNT" -maxdepth 5 -type d -name armada 2>/dev/null | grep -E '/home/armada$' | head -n 1 || true)"
fi
if [ -z "$HOME_DIR" ]; then
    # Fallback: create under var/home/armada (or ostree/deploy/*/var/home/armada)
    VAR_BASE="$(find "$MNT" -maxdepth 4 -type d -name home 2>/dev/null | head -n 1 || true)"
    [ -n "$VAR_BASE" ] || VAR_BASE="$MNT/var/home"
    HOME_DIR="$VAR_BASE/armada"
    mkdir -p "$HOME_DIR"
fi
echo "Ziel-Home im Image: $HOME_DIR"

DEST="$HOME_DIR/.local/share/tandem"
CFG="$HOME_DIR/.config/tandem"
SESS="$HOME_DIR/.config/gamescope-session-plus/sessions.d"
APPS="$HOME_DIR/.local/share/applications"
ICONS="$HOME_DIR/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$DEST" "$CFG" "$SESS" "$APPS" "$ICONS" "$HOME_DIR/Desktop"

cp -a "$ROOT/tandem/." "$DEST/"
rm -rf "$DEST/__pycache__" "$DEST/ui/__pycache__" "$DEST/ui/decks/__pycache__"
chmod 755 "$DEST/tandem-launch" "$DEST/gamescope-own" "$DEST/thor-record"
install -m 644 "$ROOT/os/gamescope-steam-hook" "$SESS/steam"
touch "$CFG/own-session"
[ -f "$DEST/tandem.svg" ] && install -m 644 "$DEST/tandem.svg" "$ICONS/tandem.svg"

cat > "$APPS/tandem.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Toravo Tandem
Comment=Dual-Screen-Oberfläche für den AYN Thor
Exec=/var/home/armada/.local/share/tandem/tandem-launch
Icon=tandem
Terminal=false
Categories=Game;
EOF

cat > "$HOME_DIR/Desktop/tandem-zurueck.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Zurück zu Tandem
Name[en]=Back to Tandem
Comment=Zurück in den Spielmodus
Icon=tandem
Exec=steamos-session-select gamescope
Terminal=false
Categories=System;
EOF
chmod 755 "$HOME_DIR/Desktop/tandem-zurueck.desktop"
chown -R 1000:1000 "$HOME_DIR/.local" "$HOME_DIR/.config" "$HOME_DIR/Desktop"

# Install kernel sysctl gaming tuning & wheel udev hardware permissions into the image's /etc
ETC_DIR="$(find "$MNT" -maxdepth 5 -type d -name sysctl.d 2>/dev/null | grep '/etc/sysctl.d$' | head -n 1 || true)"
if [ -n "$ETC_DIR" ]; then
    ETC_ROOT="$(dirname "$ETC_DIR")"
    mkdir -p "$ETC_ROOT/sysctl.d" "$ETC_ROOT/udev/rules.d" "$ETC_ROOT/systemd/zram-generator.conf.d" "$ETC_ROOT/armada"
    install -m 644 "$ROOT/os/99-toravo-perf.conf" "$ETC_ROOT/sysctl.d/99-toravo-perf.conf"
    install -m 644 "$ROOT/os/99-toravo-hw.rules" "$ETC_ROOT/udev/rules.d/99-toravo-hw.rules"
    cat > "$ETC_ROOT/systemd/zram-generator.conf.d/99-toravo-lz4.conf" <<'ZEOF'
[zram0]
compression-algorithm = lz4
ZEOF
    cat > "$ETC_ROOT/armada/game-tweaks.json" <<'TEOF'
{
  "games": {},
  "global": {
    "cores": "big",
    "fexProfile": "fast",
    "gamescopeCores": "little",
    "nice": -10,
    "scheduler": "lavd",
    "turnipDriver": "winnative"
  }
}
TEOF
    echo "HyperDrive game-tweaks, LZ4 ZRAM, sysctl + udev rules installed into $ETC_ROOT"
fi

# Append mitigations=off to BLS kernel options in /boot/loader/entries (eliminates ARM64 Spectre-BHB syscall overhead)
for bls in "$MNT"/boot/loader*/entries/*.conf "$MNT"/ostree/boot.*/default/*/*/boot/loader/entries/*.conf; do
    [ -f "$bls" ] || continue
    if grep -q '^options ' "$bls" && ! grep -q 'mitigations=off' "$bls"; then
        sed -i 's/^options \(.*\)$/options \1 mitigations=off/' "$bls"
        echo "Added mitigations=off to $bls"
    fi
done

sync
umount -R "$MNT"
losetup -d "$LOOP"
LOOP=""

echo "== [4/4] Komprimiere ${IMG_BASE}.img -> ${IMG_BASE}.img.xz (multithreaded) =="
xz -T0 -6 -f "$RAW_IMG"
(cd "$OUT_DIR" && sha256sum "${IMG_BASE}.img.xz" > "${IMG_BASE}.img.xz.sha256")
ls -lh "$OUT_DIR/${IMG_BASE}.img.xz" "$OUT_DIR/${IMG_BASE}.img.xz.sha256"
echo "FERTIG: $OUT_DIR/${IMG_BASE}.img.xz"
