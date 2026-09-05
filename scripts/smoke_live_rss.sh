#!/usr/bin/env bash
# Manual live RSS smoke (stages 8–9). Prefer pytest gate in CI.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi
cd "$ROOT"
exec "$PYTHON" -m pytest tests/unit/test_live_rss_gate.py -q --timeout=120 "$@"
