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

SCOPE="${1:-smoke}"
if [ "$#" -gt 0 ]; then
  shift
fi

case "$SCOPE" in
  smoke)
    echo "======================================================================"
    echo "🧪 [yt-auto] Running Fast Smoke Gate (< 30s)"
    echo "   Modular domains: core | media | audio | narrative | mcp | review | observability | pipeline"
    echo "   Full CI gate:    ./scripts/test.sh all"
    echo "======================================================================"
    "$SCRIPT_DIR/verify_integrity.sh" --fast
    echo "== live RSS gate =="
    "$PYTEST_CMD" tests/unit/test_live_rss_gate.py -q --timeout=120
    echo "== D2 timing gate =="
    "$PYTEST_CMD" tests/unit/test_d2_timing_gate.py -q --timeout=120
    echo "✅ Smoke gate passed successfully."
    ;;
  fast)
    echo "== fast integrity & anti-regression =="
    "$SCRIPT_DIR/verify_integrity.sh" --fast
    ;;
  core)
    echo "== running core domain tests =="
    "$PYTEST_CMD" -m "core" "$@"
    ;;
  media)
    echo "== running media domain tests =="
    "$PYTEST_CMD" -m "media" "$@"
    ;;
  audio)
    echo "== running audio domain tests =="
    "$PYTEST_CMD" -m "audio" "$@"
    ;;
  narrative)
    echo "== running narrative domain tests =="
    "$PYTEST_CMD" -m "narrative" "$@"
    ;;
  mcp)
    echo "== running MCP domain tests =="
    "$PYTEST_CMD" -m "mcp" "$@"
    ;;
  review)
    echo "== running review domain tests =="
    "$PYTEST_CMD" -m "review" "$@"
    ;;
  observability)
    echo "== running observability domain tests =="
    "$PYTEST_CMD" -m "observability" "$@"
    ;;
  pipeline)
    echo "== running pipeline domain tests =="
    "$PYTEST_CMD" -m "pipeline" "$@"
    ;;
  catalog)
    echo "== running empirical catalog media tests =="
    "$PYTEST_CMD" -m "catalog_media" "$@"
    ;;
  stress)
    echo "== running computational stress tests =="
    "$PYTEST_CMD" -m "stress" "$@"
    ;;
  unit)
    echo "== running unit tests =="
    "$PYTEST_CMD" tests/unit/ "$@"
    ;;
  integration)
    echo "== running integration tests =="
    "$PYTEST_CMD" tests/integration/ "$@"
    ;;
  e2e)
    echo "== running e2e tests =="
    "$PYTEST_CMD" tests/e2e/ "$@"
    ;;
  all|ci)
    echo "== integrity audit =="
    "$SCRIPT_DIR/verify_integrity.sh"

    echo "== live RSS gate =="
    "$PYTEST_CMD" tests/unit/test_live_rss_gate.py -q --timeout=120

    echo "== D2 timing gate =="
    "$PYTEST_CMD" tests/unit/test_d2_timing_gate.py -q --timeout=120

    echo "== full offline suite (not live) =="
    export YT_LIVE_RSS_PEAK_MB="${YT_LIVE_RSS_PEAK_MB:-768}"
    "$PYTEST_CMD" -q --timeout=600 "$@"

    echo "🎉 Local CI full regression passed cleanly."
    ;;
  help|--help|-h)
    echo "Usage: ./scripts/test.sh [scope] [pytest_args...]"
    echo ""
    echo "Domain scopes (8-35s):"
    echo "  core           SQLite, models, scheduler, locks, channels"
    echo "  media          Video compositors, loops, subtitles, overlays"
    echo "  audio          TTS, synth, voice mastering, ducking"
    echo "  narrative      Script curation, archetypes, LLM prompts"
    echo "  mcp            MCP server, tools, resources, sync"
    echo "  review         Telegram review bot, approval state machine"
    echo "  observability  Metrics, analytics, events, healthcheck"
    echo "  pipeline       CLI, daemons, orchestrator"
    echo ""
    echo "Lifecycle & CI scopes:"
    echo "  smoke          Fast pre-commit check (default, < 30s)"
    echo "  fast           Ultra-fast integrity audit (< 10s)"
    echo "  unit           All unit tests"
    echo "  integration    Integration test suite"
    echo "  e2e            End-to-end rendering suite"
    echo "  all | ci       Full comprehensive regression gate"
    echo "  catalog        Empirical catalog tests (requires committed media)"
    echo "  stress         Heavy soak/stress benchmarks"
    ;;
  *)
    # Direct pass-through for custom pytest arguments or paths
    "$PYTEST_CMD" "$SCOPE" "$@"
    ;;
esac
