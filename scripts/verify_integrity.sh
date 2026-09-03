#!/usr/bin/env bash
# scripts/verify_integrity.sh - Cadence Integrity Audit & Anti-Regression Kill Switch
# Enforces the Project Governance Policy: Mandatory check every 25 commits or pre-run.
set -euo pipefail

echo "======================================================================"
echo "🔍 [INTEGRITY AUDIT] Checking Repository Invariants & Governance SLA"
echo "======================================================================"

FAILURES=0

# 1. Check Git Worktrees (Must be exactly 1 active worktree)
ACTIVE_WORKTREES=$(git worktree list | wc -l)
if [ "$ACTIVE_WORKTREES" -ne 1 ]; then
    echo "❌ [FAIL] Stale worktrees detected! Expected 1, found $ACTIVE_WORKTREES:"
    git worktree list
    FAILURES=$((FAILURES + 1))
else
    echo "✅ [PASS] Git worktree hygiene: exactly 1 active worktree."
fi

# 2. Check for Resurrected Obsolete Architecture Blueprints
if ls docs/architecture/0*.md > /dev/null 2>&1; then
    echo "❌ [FAIL] Obsolete architecture documents detected in docs/architecture/0*.md!"
    ls -l docs/architecture/0*.md
    FAILURES=$((FAILURES + 1))
else
    echo "✅ [PASS] Architecture docs: zero obsolete blueprints."
fi

# 3. Check for Retired Legacy Subsystems
if [ -d "src/rendering" ] || [ -d "src/compositing" ] || [ -d "src/export" ]; then
    echo "❌ [FAIL] Retired v2 legacy directories detected (src/rendering, src/compositing, src/export)!"
    FAILURES=$((FAILURES + 1))
else
    echo "✅ [PASS] Subsystem isolation: zero legacy rendering directories."
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

# 6. Run Fast Anti-Regression Test Suite
echo "⏳ Running automated anti-regression test suite..."
if .venv/bin/pytest tests/unit/test_anti_regression_guardrails.py -q > /dev/null 2>&1; then
    echo "✅ [PASS] Anti-regression test suite (REG-01 to REG-30) passed 100%."
else
    echo "❌ [FAIL] Anti-regression test suite failed!"
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
