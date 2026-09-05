#!/usr/bin/env bash
# scripts/verify_integrity.sh - Cadence Integrity Audit & Anti-Regression Kill Switch
# Enforces the Project Governance Policy: Mandatory check every 25 commits or pre-run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo "======================================================================"
echo "🔍 [INTEGRITY AUDIT] Checking Repository Invariants & Governance SLA"
echo "======================================================================"

FAILURES=0

# 1. Check Git Worktrees (Must have zero stale/prunable worktrees)
git worktree prune
STALE_WORKTREES=$(git worktree list --porcelain | grep -c "^prunable" || true)
UNTRACKED_WORKTREES=0
while IFS= read -r line; do
    if [[ "$line" =~ ^worktree[[:space:]]+(.*) ]]; then
        wt_path="${BASH_REMATCH[1]}"
        if [ ! -d "$wt_path" ]; then
            UNTRACKED_WORKTREES=$((UNTRACKED_WORKTREES + 1))
        fi
    fi
done < <(git worktree list --porcelain)

if [ "$STALE_WORKTREES" -gt 0 ] || [ "$UNTRACKED_WORKTREES" -gt 0 ]; then
    echo "❌ [FAIL] Stale or unlinked worktrees detected!"
    git worktree list
    FAILURES=$((FAILURES + 1))
else
    ACTIVE_COUNT=$(git worktree list | wc -l)
    echo "✅ [PASS] Git worktree hygiene: $ACTIVE_COUNT valid worktree(s), zero stale/prunable."
fi

# 2. Check for Resurrected Obsolete Architecture Blueprints
if ls docs/architecture/0*.md > /dev/null 2>&1; then
    echo "❌ [FAIL] Obsolete architecture documents detected in docs/architecture/0*.md!"
    ls -l docs/architecture/0*.md
    FAILURES=$((FAILURES + 1))
else
    echo "✅ [PASS] Architecture docs: zero obsolete blueprints."
fi

# 3. Check for Retired Legacy Subsystems and Imports
RETIRED_DIRS=0
if [ -d "src/rendering" ] || [ -d "src/compositing" ] || [ -d "src/export" ]; then
    echo "❌ [FAIL] Retired v2 legacy directories detected (src/rendering, src/compositing, src/export)!"
    FAILURES=$((FAILURES + 1))
    RETIRED_DIRS=1
fi

RETIRED_IMPORTS=$(grep -rn --exclude-dir=".venv" --exclude-dir=".git" -E "from[[:space:]]+src\.(rendering|compositing|export)|import[[:space:]]+src\.(rendering|compositing|export)" src/ tests/ || true)
if [ -n "$RETIRED_IMPORTS" ]; then
    echo "❌ [FAIL] Imports from retired legacy subsystems detected in codebase:"
    echo "$RETIRED_IMPORTS"
    FAILURES=$((FAILURES + 1))
elif [ "$RETIRED_DIRS" -eq 0 ]; then
    echo "✅ [PASS] Subsystem isolation: zero legacy rendering directories and zero retired imports."
fi

# 4. Check for Forbidden Playwright Imports in Media/Pipeline
PLAYWRIGHT_VIOLATIONS=$(grep -rn --exclude-dir=".venv" --exclude-dir=".git" -E "import.*playwright|from[[:space:]]+playwright" src/ | grep -v "src/youtube/" || true)
if [ -n "$PLAYWRIGHT_VIOLATIONS" ]; then
    echo "❌ [FAIL] Forbidden Playwright import detected outside src/youtube/uploader.py:"
    echo "$PLAYWRIGHT_VIOLATIONS"
    FAILURES=$((FAILURES + 1))
else
    echo "✅ [PASS] Zero-Browser Policy: zero Playwright imports in media and pipeline."
fi

# 5. Check Git Hooks Configuration
HOOKS_PATH=$(git config core.hooksPath || echo "")
if [ "$HOOKS_PATH" != ".githooks" ] || [ ! -x ".githooks/pre-commit" ]; then
    echo "❌ [FAIL] Anti-regression pre-commit hook is not configured or executable! (core.hooksPath=$HOOKS_PATH)"
    FAILURES=$((FAILURES + 1))
else
    echo "✅ [PASS] Git pre-commit hook is active and enforced via .githooks."
fi

# 6. Run Fast Anti-Regression Test Suite and Verify Test Collectability
PYTEST_CMD=""
if [ -x "$REPO_ROOT/.venv/bin/pytest" ]; then
    PYTEST_CMD="$REPO_ROOT/.venv/bin/pytest"
elif command -v pytest > /dev/null 2>&1; then
    PYTEST_CMD="pytest"
fi

echo "⏳ Checking test suite collectability across all modules..."
if [ -n "$PYTEST_CMD" ] && "$PYTEST_CMD" --collect-only -q > /dev/null 2>&1; then
    echo "✅ [PASS] Test suite collectability: 100% collectable with zero import errors."
else
    echo "❌ [FAIL] Pytest collection errors detected! Unimportable or broken test files present."
    FAILURES=$((FAILURES + 1))
fi

echo "⏳ Running automated anti-regression test suite..."
if [ -n "$PYTEST_CMD" ] && "$PYTEST_CMD" tests/unit/test_anti_regression_guardrails.py -q > /dev/null 2>&1; then
    echo "✅ [PASS] Anti-regression test suite (REG-01 to REG-13) passed 100%."
else
    echo "❌ [FAIL] Anti-regression test suite failed or pytest not executable!"
    FAILURES=$((FAILURES + 1))
fi

# 7. Check for Vendored Bloat and Minified Bundles
if [ -d ".github/skills" ] || [ -d "assets/vendor" ] || git ls-files | grep -E '\.min\.js$' > /dev/null 2>&1; then
    echo "❌ [FAIL] Vendored bloat detected (.github/skills, assets/vendor, or *.min.js)!"
    FAILURES=$((FAILURES + 1))
else
    echo "✅ [PASS] Anti-Bloat: zero vendored skills or third-party minified libraries."
fi

# 8. Caption burn must not return on the loop pipeline
if grep -q "burn_subtitles" src/pipeline.py; then
    echo "❌ [FAIL] Caption burn flag reintroduced in src/pipeline.py (REG-13)."
    FAILURES=$((FAILURES + 1))
elif grep -q "stream_copy_mode = True" src/pipeline.py; then
    echo "✅ [PASS] Loop pipeline muxes captions; no burn_subtitles."
else
    echo "❌ [FAIL] src/pipeline.py lost stream_copy_mode = True (REG-13)."
    FAILURES=$((FAILURES + 1))
fi

echo "======================================================================"
if [ "$FAILURES" -gt 0 ]; then
    echo "🛑 [REFUSAL TRIGGERED] $FAILURES integrity checks failed!"
    echo "🚨 POLICY MANDATE: Work MUST be halted immediately. Alert the operator."
    echo "   Do NOT implement new features or run pipelines until sanitized."
    echo "======================================================================"
    exit 1
else
    COMMIT_COUNT=$(git rev-list --count HEAD)
    echo "🎉 [STATUS: HEALTHY] All invariants verified at commit #$COMMIT_COUNT."
    echo "🚀 Safe to proceed with development or production pipelines."
    echo "======================================================================"
    exit 0
fi
