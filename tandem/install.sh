#!/bin/bash
# Installs Tandem for the current user on ArmadaOS (no root, nothing outside the home folder).
#   ./install.sh            install or update
#   ./install.sh --remove   remove again (favourites and play times are kept in ~/.local/state/tandem)
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${TANDEM_DEST:-${XDG_DATA_HOME:-$HOME/.local/share}/tandem}"  # TANDEM_DEST: the updater installs over the running copy
DESKTOP="${XDG_DATA_HOME:-$HOME/.local/share}/applications/tandem.desktop"

if [ "${1:-}" = "--remove" ]; then
    rm -rf "$DEST" "$DESKTOP" "$HOME/Desktop/tandem-zurueck.desktop" "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps/tandem.svg"
    echo "Toravo Tandem entfernt. Den Steam-Eintrag bitte in Steam selbst löschen (Eintrag > Verwalten > Entfernen)."
    exit 0
fi

command -v python3 >/dev/null || { echo "python3 fehlt" >&2; exit 1; }
python3 -c 'import PySide6.QtGui' 2>/dev/null || command -v "${TANDEM_BROWSER:-firefox}" >/dev/null || { echo "Weder PySide6 (native Oberfläche) noch Firefox gefunden – Firefox im Armada Store unter Anwendungen installieren." >&2; exit 1; }

mkdir -p "$DEST" "$(dirname "$DESKTOP")"
install -m 644 "$SRC/tandem.py" "$SRC/thor.py" "$SRC/bluetooth.py" "$SRC/controls.py" "$SRC/saves.py" "$SRC/battlenet.py" "$SRC/index.html" "$SRC/remote.html" "$SRC/test_tandem.py" "$SRC/addshortcut.py" "$SRC/wowpick.py" "$SRC/buttons-profile.yaml" "$SRC/VERSION" "$DEST/"
install -m 755 "$SRC/tandem-launch" "$SRC/gamescope-own" "$SRC/thor-record" "$DEST/"
mkdir -p "$DEST/ui/fonts"; install -m 644 "$SRC/ui/tandem_ui.py" "$SRC/ui/settings_view.py" "$SRC/ui/quick_view.py" "$SRC/ui/qr.py" "$SRC/ui/lang.py" "$SRC/ui/en.json" "$DEST/ui/"; install -m 644 "$SRC"/ui/fonts/* "$DEST/ui/fonts/"  # native front end
mkdir -p "$DEST/ui/themes"; install -m 644 "$SRC"/ui/themes/*.json "$DEST/ui/themes/"  # looks to choose from
mkdir -p "$DEST/ui/decks"; install -m 644 "$SRC"/ui/decks/*.py "$DEST/ui/decks/"  # its per-game bottom screens
# The way back from the desktop: an icon on it that returns to the game session, which is Tandem.
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"; mkdir -p "$ICONS"; install -m 644 "$SRC/tandem.svg" "$ICONS/tandem.svg"
if [ -d "$HOME/Desktop" ] && command -v steamos-session-select >/dev/null; then
    printf '[Desktop Entry]\nType=Application\nName=Zurück zu Tandem\nName[en]=Back to Tandem\nComment=Zurück in den Spielmodus\nIcon=tandem\nExec=steamos-session-select gamescope\nTerminal=false\nCategories=System;\n' > "$HOME/Desktop/tandem-zurueck.desktop"
    chmod 755 "$HOME/Desktop/tandem-zurueck.desktop"
fi
# Wide view for companion packs: mGBA with gba-duo-wide's wide view, if it was built (wide-core/build.sh)
CORES="$HOME/.var/app/org.libretro.RetroArch/config/retroarch/cores"
if [ -f "$SRC/wide-core/dist/mgba_wide_libretro.so" ] && [ -d "$CORES" ]; then install -D -m 755 "$SRC/wide-core/dist/mgba_wide_libretro.so" "$CORES/tandem-wide/mgba_libretro.so"; fi  # named like the stock core: see RA_WIDE_CORE
# Native ports that were built (ports/<name>/build.sh). They live next to Tandem's folder, so that an update of Tandem
# leaves them and their saved games (ports/<name>/data) alone.
PORTS="${XDG_DATA_HOME:-$HOME/.local/share}/tandem-ports"
for port in "$SRC"/ports/*/; do
    [ -d "$port/dist" ] || continue
    name="$(basename "$port")"; mkdir -p "$PORTS/$name"; rm -rf "$PORTS/$name/dist"
    cp -r "$port/dist" "$PORTS/$name/"; install -m 755 "$port/run" "$PORTS/$name/"
    for py in "$port"/*.py; do [ -f "$py" ] && install -m 644 "$py" "$PORTS/$name/dist/"; done  # as build.sh copies them: a dist built before a script change must not run the old one (or none)
done
mkdir -p "$DEST/decks"; for deck in "$SRC"/decks/*.html; do [ -f "$deck" ] && install -m 644 "$deck" "$DEST/decks/"; done  # second-screen pages per game
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Toravo Tandem
Comment=Dual-Screen-Oberfläche für den AYN Thor
Exec=$DEST/tandem-launch
Icon=applications-games
Terminal=false
Categories=Game;
EOF

(cd "$DEST" && python3 test_tandem.py >/dev/null 2>&1) && echo "Selbsttest: ok" || echo "Selbsttest: FEHLER – bitte 'python3 $DEST/test_tandem.py' ausführen und die Ausgabe melden."

if command -v steamos-add-to-steam >/dev/null; then
    steamos-add-to-steam "$DESKTOP" && echo "Toravo Tandem ist in Steam eingetragen (Bibliothek > Steam-fremd)."
else
    echo "Bitte von Hand eintragen: Desktop-Modus > Steam > Spiele > Steam-fremdes Spiel hinzufügen > Toravo Tandem."
fi
echo "Fertig. Für den unteren Bildschirm: Armada Control > Settings > unteren Bildschirm einschalten, dann Toravo Tandem starten."
