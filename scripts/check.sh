#!/usr/bin/env bash
set -euo pipefail

# scripts/check.sh - Standard CI and local repository health check
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== [1/2] Checking Python syntax compilation ==="
python3 -m compileall -q "$REPO_ROOT/src" "$REPO_ROOT/scripts"
echo "✅ All Python files compiled successfully without syntax errors."

echo ""
echo "=== [2/2] Running Repository Invariants & Guardrails ==="
python3 "$REPO_ROOT/scripts/verify_integrity.py" --fast

echo ""
echo "🎉 All repository verification checks passed successfully!"
