#!/bin/bash
# Builds a Tandem release for the updater into dist/: tandem-<version>.tar.gz and manifest.json. Publishing is a separate, manual step.
set -euo pipefail
cd "$(dirname "$0")"
V=$(cat tandem/VERSION); mkdir -p dist
COPYFILE_DISABLE=1 tar --no-xattrs -czf "dist/tandem-$V.tar.gz" --exclude __pycache__ --exclude '*.bak*' tandem
printf '{"version": "%s", "file": "tandem-%s.tar.gz", "sha256": "%s"}\n' "$V" "$V" "$(shasum -a 256 "dist/tandem-$V.tar.gz" | cut -d' ' -f1)" > dist/manifest.json
cp get.sh dist/
cat dist/manifest.json
