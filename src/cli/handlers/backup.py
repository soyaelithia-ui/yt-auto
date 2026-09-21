"""Handler for 'backup' subcommand and verified SQLite database backups."""
from __future__ import annotations

import argparse
import json

from src.config import DEFAULT_DB_PATH
from src.core.repository import backup_database


def handle_backup(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Create a verified, vacuum-sealed backup of the SQLite database."""
    db_path = getattr(args, "db_path", DEFAULT_DB_PATH)
    dest = getattr(args, "destination", None) or getattr(args, "dest", None)
    path = backup_database(db_path, dest)

    if getattr(args, "json", False):
        print(json.dumps({"backup": str(path), "verified": True}, indent=2))
    else:
        print(f"Database backup successfully created and verified at: {path}")
    return 0
