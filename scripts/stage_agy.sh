#!/usr/bin/env bash
# Copy the host Antigravity CLI ELF into build/agy for the Docker image.
# The binary is gitignored; never commit it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/build/agy"
mkdir -p "$ROOT/build"

src="${AGY_BIN:-}"
if [[ -z "$src" ]]; then
  src="$(command -v agy || true)"
fi
if [[ -z "$src" || ! -e "$src" ]]; then
  echo "stage_agy: agy not found. Install the CLI or set AGY_BIN to the ELF path." >&2
  exit 1
fi
if [[ -L "$src" ]]; then
  src="$(readlink -f "$src")"
fi
if [[ ! -f "$src" ]]; then
  echo "stage_agy: $src is not a file (refusing to copy a directory)." >&2
  exit 1
fi

cp -f "$src" "$DEST"
chmod 755 "$DEST"
echo "stage_agy: copied $src -> $DEST"
