#!/usr/bin/env bash
# Unified integrity audit runner using repo-local .venv/bin/python3 and .venv/bin/pytest.
# Delegates to verify_integrity.py (enforcing Check #9: scripts/verify_mcp_sync.py).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="python3"
if [ -x "$SCRIPT_DIR/../.venv/bin/python3" ]; then
    PYTHON_BIN="$SCRIPT_DIR/../.venv/bin/python3"
fi
exec "$PYTHON_BIN" "$SCRIPT_DIR/verify_integrity.py" "$@"
