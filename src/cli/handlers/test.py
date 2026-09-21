"""Handler for 'test' subcommand running the unified test and integrity suite."""
from __future__ import annotations

import argparse
import subprocess

from src.config import BASE_DIR


def handle_test(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Run the unified integrity and test suite."""
    test_script = BASE_DIR / "scripts" / "test.sh"
    if not test_script.is_file():
        test_script = BASE_DIR / "scripts" / "verify_integrity.sh"

    try:
        res = subprocess.run([str(test_script)], cwd=str(BASE_DIR), timeout=600)
        return res.returncode
    except subprocess.TimeoutExpired:
        print("❌ Test suite execution timed out after 600s.")
        return 1
