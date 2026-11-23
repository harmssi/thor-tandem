#!/bin/bash
# Safe interactive flasher for macOS & Linux: writes toravo-tandem-os-*.img.xz onto a USB drive or SD card.
# Usage: sudo ./os/flash-thor.sh dist/toravo-tandem-os-0.6.0-arm64.img.xz /dev/diskX (or /dev/sdX)
set -euo pipefail

if [ $# -lt 2 ]; then
    echo "Verwendung: sudo $0 <toravo-tandem-os-*.img.xz> <Ziel-Laufwerk z.B. /dev/disk4 oder /dev/sdb>"
    exit 1
fi

IMG="$1"
DEV="$2"
[ -f "$IMG" ] || { echo "Fehler: Image nicht gefunden: $IMG" >&2; exit 1; }
[ "$(id -u)" = 0 ] || { echo "Bitte mit sudo ausführen." >&2; exit 1; }

if [ -f "${IMG}.sha256" ]; then
    echo "Prüfe SHA-256 von $(basename "$IMG") …"
    (cd "$(dirname "$IMG")" && (shasum -a 256 -c "$(basename "$IMG").sha256" 2>/dev/null || sha256sum -c "$(basename "$IMG").sha256"))
fi

echo "WARNUNG: Alle Daten auf $DEV werden überschrieben!"
if command -v diskutil >/dev/null 2>&1; then
    diskutil info "$DEV" | grep -E "Device / Media Name|Disk Size|Protocol|Removable" || true
else
    lsblk -o NAME,SIZE,MODEL,TRAN "$DEV" || true
fi
printf "Zum Fortfahren genau JA tippen: "
read -r ANS
[ "$ANS" = "JA" ] || { echo "Abgebrochen."; exit 1; }

if command -v diskutil >/dev/null 2>&1; then
    diskutil unmountDisk "$DEV"
    RDEV="${DEV/\/dev\/disk/\/dev\/rdisk}"
    echo "Schreibe $(basename "$IMG") auf $RDEV …"
    xz -dc "$IMG" | dd of="$RDEV" bs=4m status=progress
    sync
    diskutil eject "$DEV"
else
    umount "${DEV}"* 2>/dev/null || true
    echo "Schreibe $(basename "$IMG") auf $DEV …"
    xz -dc "$IMG" | dd of="$DEV" bs=4M status=progress conv=fsync
    sync
fi
echo "Fertig! Medium in den AYN Thor stecken und über OpenABL starten."
