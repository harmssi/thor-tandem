#!/bin/bash
# Installs the newest Tandem release on ArmadaOS: curl -L https://github.com/harmssi/thor-tandem/releases/latest/download/get.sh | bash
set -euo pipefail
URL=https://github.com/harmssi/thor-tandem/releases/latest/download
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
curl -fsSL "$URL/manifest.json" -o "$TMP/manifest.json"
FILE=$(python3 -c 'import json,os,sys; print(os.path.basename(json.load(open(sys.argv[1]))["file"]))' "$TMP/manifest.json")
SHA=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "$TMP/manifest.json")
curl -fsSL "$URL/$FILE" -o "$TMP/$FILE"
echo "$SHA  $TMP/$FILE" | sha256sum -c - >/dev/null || { echo "Prüfsumme stimmt nicht – abgebrochen." >&2; exit 1; }
tar xzf "$TMP/$FILE" -C "$HOME"   # unpacks to ~/tandem
if [ -r /dev/tty ]; then python3 "$HOME/tandem/setup.py" </dev/tty; else python3 "$HOME/tandem/setup.py" --ja; fi
