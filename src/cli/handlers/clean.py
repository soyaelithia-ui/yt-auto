"""Handler for 'clean' subcommand, temporary directories, and cache pruning."""
from __future__ import annotations

import argparse
from typing import Any

from src.cleaner import clean_system_cache


def handle_clean(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Purge temporary render artifacts, caches, and run-id work directories."""
    if getattr(args, "sessions", False):
        print("=== Session Lifecycle Report ===")
        print("AGY session management has been retired.")
        return 0

    report = clean_system_cache(dry_run=getattr(args, "dry_run", False))
    freed_mb = round(report["freed_bytes"] / (1024 * 1024), 2)
    print("=== Tagged Project Work Cleanup Report ===")
    print(f"Freed Space: {freed_mb} MB")
    print(f"Deleted Files: {report['deleted_files_count']} | Deleted Directories: {report['deleted_dirs_count']}")
    print(f"Execution Mode: {'DRY RUN (Simulation)' if report['dry_run'] else 'LIVE CLEANUP'}")
    return 0
