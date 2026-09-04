#!/usr/bin/env bash
# Read-only FFmpeg hot-path smoke: parse live argv evidence. Never exec the log.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

PYTHON=""
if [ -x ".venv/bin/python3" ]; then
    PYTHON=".venv/bin/python3"
elif [ -x "/home/moku/projects/yt-auto/.venv/bin/python3" ]; then
    PYTHON="/home/moku/projects/yt-auto/.venv/bin/python3"
else
    PYTHON="python3"
fi

exec "$PYTHON" -m src.media.ffmpeg_hot_path_smoke "$@"
