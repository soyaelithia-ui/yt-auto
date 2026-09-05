#!/usr/bin/env bash
# scripts/test.sh - Unified Canonical Test Runner for yt-auto
# Executes the full repository integrity audit and core functional validation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo "🧪 ======================================================================"
echo "🧪 [TEST RUNNER] Ejecutando verificación integral de yt-auto"
echo "🧪 ======================================================================"

# 1. Ejecutar auditoría estricta de invariantes y gobernanza
"$SCRIPT_DIR/verify_integrity.sh"

# 2. Localizar el ejecutable de pytest canónico
PYTEST_CMD=""
if [ -x "$REPO_ROOT/.venv/bin/pytest" ]; then
    PYTEST_CMD="$REPO_ROOT/.venv/bin/pytest"
elif command -v pytest > /dev/null 2>&1; then
    PYTEST_CMD="pytest"
fi

if [ -z "$PYTEST_CMD" ]; then
    echo "❌ ERROR: No se encontró el entorno virtual con pytest."
    exit 1
fi

echo ""
echo "⏳ [SUITE FUNCIONAL] Ejecutando validación de calidad y subtítulos..."
"$PYTEST_CMD" tests/unit/test_subtitles_ass.py -q
"$PYTEST_CMD" tests/test_e2e_validation.py -k longform -q

echo ""
echo "======================================================================"
echo "🎉 [100% HEALTHY] Todas las pruebas e invariantes pasaron exitosamente."
echo "======================================================================"
exit 0
