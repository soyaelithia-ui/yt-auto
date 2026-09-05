#!/usr/bin/env bash
# Read-only FFmpeg hot-path smoke: parse live argv evidence. Never exec the log.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Prefer repo venv, then active VIRTUAL_ENV, then python3 on PATH.
# Never hardcode a machine-local path.
PYTHON=""
if [ -x "$REPO_ROOT/.venv/bin/python3" ]; then
    PYTHON="$REPO_ROOT/.venv/bin/python3"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python3" ]; then
    PYTHON="$VIRTUAL_ENV/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="$(command -v python3)"
else
    echo "error: no python3 found (repo .venv, VIRTUAL_ENV, or PATH)" >&2
    exit 1
fi

exec "$PYTHON" -m src.media.ffmpeg_hot_path_smoke "$@"
