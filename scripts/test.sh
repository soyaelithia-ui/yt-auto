#!/usr/bin/env bash
# Local CI gate for yt-auto. This is the source of truth — GitHub Actions
# on ubuntu-latest is billing-blocked and must not be treated as a check.
# Mirrors .github/workflows/tests.yml plus the repo integrity audit.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if [ -x "$REPO_ROOT/.venv/bin/pytest" ]; then
  PYTEST_CMD="$REPO_ROOT/.venv/bin/pytest"
elif command -v pytest >/dev/null 2>&1; then
  PYTEST_CMD="$(command -v pytest)"
else
  echo "error: no pytest (repo .venv or PATH)" >&2
  exit 1
fi

export YT_PROFILE="${YT_PROFILE:-test}"

echo "== integrity =="
"$SCRIPT_DIR/verify_integrity.sh"

echo "== live RSS gate =="
"$PYTEST_CMD" tests/unit/test_live_rss_gate.py -q --timeout=120

echo "== D2 timing gate =="
"$PYTEST_CMD" tests/unit/test_d2_timing_gate.py -q --timeout=120

echo "== offline suite (not live) =="
export YT_LIVE_RSS_PEAK_MB="${YT_LIVE_RSS_PEAK_MB:-768}"
"$PYTEST_CMD" -m "not live" -q --timeout=600

echo "local CI gate passed"
