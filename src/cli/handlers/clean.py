"""Handler for 'clean' subcommand, temporary directories, and cache pruning."""
from __future__ import annotations

import argparse

from src.cleaner import (
    clean_expired_failed_runs,
    clean_system_cache,
    clean_untracked_temp_files,
)


def handle_clean(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Purge temporary render artifacts, caches, and run-id work directories."""
    if getattr(args, "sessions", False):
        print("=== Session Lifecycle Report ===")
        print("AGY session management has been retired.")
        return 0

    dry_run = getattr(args, "dry_run", False)

    # 1. Clean satisfied retention runs
    cache_report = clean_system_cache(dry_run=dry_run)

    # 2. Clean expired failed runs
    failed_report = clean_expired_failed_runs(dry_run=dry_run)

    # 3. Clean untracked temp files
    temp_report = clean_untracked_temp_files(dry_run=dry_run)

    total_freed_bytes = (
        cache_report.get("freed_bytes", 0)
        + failed_report.get("freed_bytes", 0)
        + temp_report.get("freed_bytes", 0)
    )
    total_files = (
        cache_report.get("deleted_files_count", 0)
        + failed_report.get("deleted_files_count", 0)
        + temp_report.get("deleted_files_count", 0)
    )
    total_dirs = cache_report.get("deleted_dirs_count", 0) + failed_report.get("deleted_dirs_count", 0)

    freed_mb = round(total_freed_bytes / (1024 * 1024), 2)
    print("=== Tagged Project Work Cleanup Report ===")
    print(f"Freed Space: {freed_mb} MB")
    print(f"Deleted Files: {total_files} | Deleted Directories: {total_dirs}")
    print(f"  - Expired Successful Runs: {cache_report.get('deleted_dirs_count', 0)} dirs ({round(cache_report.get('freed_bytes', 0) / (1024*1024), 2)} MB)")
    print(f"  - Expired Failed Runs: {failed_report.get('deleted_dirs_count', 0)} dirs ({round(failed_report.get('freed_bytes', 0) / (1024*1024), 2)} MB)")
    print(f"  - Orphan Temp Files: {temp_report.get('deleted_files_count', 0)} files ({round(temp_report.get('freed_bytes', 0) / (1024*1024), 2)} MB)")
    print(f"Execution Mode: {'DRY RUN (Simulation)' if dry_run else 'LIVE CLEANUP'}")
    return 0
