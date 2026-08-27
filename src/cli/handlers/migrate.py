"""Handler for 'migrate' subcommand and SQLite schema migrations."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from typing import Any

from src.config import DEFAULT_DB_PATH
from src.core.repository import migrate_database


def handle_migrate(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Execute SQLite schema migrations and index synchronizations."""
    db_path = getattr(args, "db_path", DEFAULT_DB_PATH)
    report = migrate_database(db_path, dry_run=getattr(args, "dry_run", False))

    if getattr(args, "json", False):
        print(json.dumps(asdict(report), indent=2, default=str))
    else:
        print(f"=== Database Migration Report (dry_run={report.dry_run}) ===")
        print(f"Applied versions: {list(report.applied_versions)}")
        print(f"Changed rows: {report.changed_rows}")
        print(f"Quick check: {report.quick_check}")
    return 0
