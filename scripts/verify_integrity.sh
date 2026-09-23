#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="python3"
if [ -x "$SCRIPT_DIR/../.venv/bin/python3" ]; then
    PYTHON_BIN="$SCRIPT_DIR/../.venv/bin/python3"
fi
exec "$PYTHON_BIN" "$SCRIPT_DIR/verify_integrity.py" "$@"
