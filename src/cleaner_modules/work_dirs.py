"""Cleaner module for run directories, expired failed runs, and orphan dev dirs."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from src.cleaner_modules.intermediates import (
    clean_proxy_cache,
    clean_test_artifacts,
    clean_tts_cache,
    clean_untracked_temp_files,
)
from src.config import BASE_DIR, SETTINGS, is_test_environment
from src.log import get_logger

logger = get_logger("cleaner.work_dirs")


def _get_active_settings():
    cleaner_mod = sys.modules.get("src.cleaner")
    if cleaner_mod and hasattr(cleaner_mod, "SETTINGS"):
        return cleaner_mod.SETTINGS
    return SETTINGS


def clean_system_cache(
    min_age_seconds: int | None = None,
    dry_run: bool = False,
    root: str | Path | None = None,
) -> dict:
    """Remove only expired work directories carrying a valid project run marker."""
    now = time.time()
    active_settings = _get_active_settings()
    work_dir = Path(root) if root is not None else active_settings.work_root
    report = {
        "freed_bytes": 0,
        "deleted_files_count": 0,
        "deleted_dirs_count": 0,
        "dry_run": dry_run,
        "details": [],
    }
    if not work_dir.exists():
        return report
    if min_age_seconds is None:
        try:
            min_age_seconds = int(os.environ.get("LOCAL_RETENTION_SECONDS", "604800"))
        except ValueError:
            logger.warning("Cleanup blocked: LOCAL_RETENTION_SECONDS is invalid")
            return report
    if min_age_seconds < 0:
        logger.info("Cleanup disabled by negative LOCAL_RETENTION_SECONDS")
        return report
    for run_dir in work_dir.iterdir():
        if not run_dir.is_dir() or run_dir.is_symlink():
            continue
        marker = run_dir / ".run.json"
        if not marker.is_file() or now - marker.stat().st_mtime < min_age_seconds:
            continue
        try:
            metadata = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        run_id = str(metadata.get("run_id") or "")
        if not run_id or run_dir.name != run_id:
            continue
        if metadata.get("active") is not False or metadata.get("retention_satisfied") is not True:
            continue
        files_count = 0
        size = 0
        for item in run_dir.rglob("*"):
            if item.is_file() and not item.is_symlink():
                size += item.stat().st_size
                files_count += 1
        if not dry_run:
            shutil.rmtree(run_dir)
        report["freed_bytes"] += size
        report["deleted_files_count"] += files_count
        report["deleted_dirs_count"] += 1
        report["details"].append({"run_id": run_id, "bytes": size})
    return report


def clean_expired_failed_runs(
    min_age_seconds: int | None = None,
    dry_run: bool = False,
    root: str | Path | None = None,
) -> dict:
    """Reclaim failed run directories (active == False, retention_satisfied != True) older than min_age_seconds."""
    now = time.time()
    active_settings = _get_active_settings()
    work_dir = Path(root) if root is not None else active_settings.work_root
    report = {
        "freed_bytes": 0,
        "deleted_files_count": 0,
        "deleted_dirs_count": 0,
        "dry_run": dry_run,
        "details": [],
    }
    if not work_dir.exists():
        return report
    if min_age_seconds is None:
        if is_test_environment():
            min_age_seconds = 0
        else:
            try:
                min_age_seconds = int(os.environ.get("FAILED_RUN_RETENTION_SECONDS", "1800"))
            except ValueError:
                min_age_seconds = 1800
    if min_age_seconds < 0:
        return report
    for run_dir in work_dir.iterdir():
        if not run_dir.is_dir() or run_dir.is_symlink():
            continue
        marker = run_dir / ".run.json"
        if not marker.is_file() or now - marker.stat().st_mtime < min_age_seconds:
            continue
        try:
            metadata = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        run_id = str(metadata.get("run_id") or "")
        if not run_id or run_dir.name != run_id:
            continue
        if metadata.get("active") is False and metadata.get("retention_satisfied") is not True:
            files_count = 0
            size = 0
            for item in run_dir.rglob("*"):
                if item.is_file() and not item.is_symlink():
                    size += item.stat().st_size
                    files_count += 1
            if not dry_run:
                shutil.rmtree(run_dir)
            report["freed_bytes"] += size
            report["deleted_files_count"] += files_count
            report["deleted_dirs_count"] += 1
            report["details"].append({"run_id": run_id, "bytes": size})
    return report


def clean_orphaned_development_dirs(
    work_root: str | Path | None = None,
    min_age_seconds: int = 3600,
    dry_run: bool = False,
) -> dict:
    """Purge orphaned development directories without valid active runs."""
    now = time.time()
    base_work = Path(work_root) if work_root is not None else (BASE_DIR / "work")
    report = {
        "freed_bytes": 0,
        "deleted_files_count": 0,
        "deleted_dirs_count": 0,
        "dry_run": dry_run,
        "details": [],
    }
    if not base_work.exists():
        return report

    reserved_names = {
        "cli",
        "test",
        "prod",
        "hybrid_renders",
        "realtime",
        "tts_cache",
        "proxy_cache",
        "assets",
        "data",
    }

    for child in base_work.iterdir():
        if not child.is_dir() or child.is_symlink():
            continue
        if child.name in reserved_names:
            continue

        marker = child / ".run.json"
        is_orphan = False

        if child.name.startswith("scp_short_") or child.name.startswith("orphan_") or child.name.startswith("dev_"):
            is_orphan = True
        elif not marker.is_file():
            is_orphan = True
        else:
            try:
                data = json.loads(marker.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or data.get("active") is not True:
                    is_orphan = True
            except (OSError, ValueError):
                is_orphan = True

        if is_orphan:
            mtime = child.stat().st_mtime
            if min_age_seconds > 0 and (now - mtime < min_age_seconds):
                continue

            size = 0
            file_count = 0
            for item in child.rglob("*"):
                if item.is_file() and not item.is_symlink():
                    size += item.stat().st_size
                    file_count += 1

            if not dry_run:
                shutil.rmtree(child)

            report["freed_bytes"] += size
            report["deleted_files_count"] += file_count
            report["deleted_dirs_count"] += 1
            report["details"].append({"dir": child.name, "bytes": size})

    return report


def clean_all_work_roots(
    work_roots: Sequence[str | Path] | None = None,
    dry_run: bool = False,
    include_caches: bool = True,
    include_tests: bool = True,
    max_cache_age_seconds: int | None = None,
    max_cache_size_bytes: int | None = None,
) -> dict:
    """Safely scan multiple work roots, prune expired runs, orphan dev dirs, and expired caches."""
    if work_roots is None:
        base_work = BASE_DIR / "work"
        candidates = [base_work, base_work / "cli", base_work / "prod"]
        if include_tests:
            candidates.append(base_work / "test")
        work_roots = [p for p in candidates if p.exists() and p.is_dir()]
    else:
        work_roots = [Path(p) for p in work_roots]

    report: dict[str, Any] = {
        "freed_bytes": 0,
        "deleted_files_count": 0,
        "deleted_dirs_count": 0,
        "dry_run": dry_run,
        "roots_scanned": [str(r) for r in work_roots],
        "categories": {
            "satisfied_runs": {"freed_bytes": 0, "deleted_dirs_count": 0},
            "failed_runs": {"freed_bytes": 0, "deleted_dirs_count": 0},
            "temp_files": {"freed_bytes": 0, "deleted_files_count": 0},
            "orphan_dev_dirs": {"freed_bytes": 0, "deleted_dirs_count": 0},
            "tts_cache": {"freed_bytes": 0, "deleted_files_count": 0},
            "proxy_cache": {"freed_bytes": 0, "deleted_files_count": 0},
            "test_artifacts": {"freed_bytes": 0, "deleted_dirs_count": 0},
        },
        "details": [],
    }

    for root_path in work_roots:
        sys_rep = clean_system_cache(dry_run=dry_run, root=root_path)
        report["freed_bytes"] += sys_rep.get("freed_bytes", 0)
        report["deleted_files_count"] += sys_rep.get("deleted_files_count", 0)
        report["deleted_dirs_count"] += sys_rep.get("deleted_dirs_count", 0)
        report["categories"]["satisfied_runs"]["freed_bytes"] += sys_rep.get("freed_bytes", 0)
        report["categories"]["satisfied_runs"]["deleted_dirs_count"] += sys_rep.get("deleted_dirs_count", 0)
        report["details"].extend(sys_rep.get("details", []))

        fail_rep = clean_expired_failed_runs(dry_run=dry_run, root=root_path)
        report["freed_bytes"] += fail_rep.get("freed_bytes", 0)
        report["deleted_files_count"] += fail_rep.get("deleted_files_count", 0)
        report["deleted_dirs_count"] += fail_rep.get("deleted_dirs_count", 0)
        report["categories"]["failed_runs"]["freed_bytes"] += fail_rep.get("freed_bytes", 0)
        report["categories"]["failed_runs"]["deleted_dirs_count"] += fail_rep.get("deleted_dirs_count", 0)
        report["details"].extend(fail_rep.get("details", []))

        temp_rep = clean_untracked_temp_files(dry_run=dry_run, root=root_path)
        report["freed_bytes"] += temp_rep.get("freed_bytes", 0)
        report["deleted_files_count"] += temp_rep.get("deleted_files_count", 0)
        report["categories"]["temp_files"]["freed_bytes"] += temp_rep.get("freed_bytes", 0)
        report["categories"]["temp_files"]["deleted_files_count"] += temp_rep.get("deleted_files_count", 0)

    orphan_rep = clean_orphaned_development_dirs(
        work_root=BASE_DIR / "work",
        min_age_seconds=0 if is_test_environment() else 3600,
        dry_run=dry_run,
    )
    report["freed_bytes"] += orphan_rep.get("freed_bytes", 0)
    report["deleted_files_count"] += orphan_rep.get("deleted_files_count", 0)
    report["deleted_dirs_count"] += orphan_rep.get("deleted_dirs_count", 0)
    report["categories"]["orphan_dev_dirs"]["freed_bytes"] += orphan_rep.get("freed_bytes", 0)
    report["categories"]["orphan_dev_dirs"]["deleted_dirs_count"] += orphan_rep.get("deleted_dirs_count", 0)
    report["details"].extend(orphan_rep.get("details", []))

    if include_caches:
        for root_path in work_roots:
            tts_rep = clean_tts_cache(
                work_root=root_path,
                max_age_seconds=max_cache_age_seconds,
                max_size_bytes=max_cache_size_bytes,
                dry_run=dry_run,
            )
            report["freed_bytes"] += tts_rep.get("freed_bytes", 0)
            report["deleted_files_count"] += tts_rep.get("deleted_files_count", 0)
            report["categories"]["tts_cache"]["freed_bytes"] += tts_rep.get("freed_bytes", 0)
            report["categories"]["tts_cache"]["deleted_files_count"] += tts_rep.get("deleted_files_count", 0)
            report["details"].extend(tts_rep.get("details", []))

            proxy_rep = clean_proxy_cache(
                work_root=root_path,
                max_age_seconds=max_cache_age_seconds,
                max_size_bytes=max_cache_size_bytes,
                dry_run=dry_run,
            )
            report["freed_bytes"] += proxy_rep.get("freed_bytes", 0)
            report["deleted_files_count"] += proxy_rep.get("deleted_files_count", 0)
            report["categories"]["proxy_cache"]["freed_bytes"] += proxy_rep.get("freed_bytes", 0)
            report["categories"]["proxy_cache"]["deleted_files_count"] += proxy_rep.get("deleted_files_count", 0)
            report["details"].extend(proxy_rep.get("details", []))

    if include_tests:
        test_rep = clean_test_artifacts(dry_run=dry_run)
        report["freed_bytes"] += test_rep.get("freed_bytes", 0)
        report["deleted_files_count"] += test_rep.get("deleted_files_count", 0)
        report["deleted_dirs_count"] += test_rep.get("deleted_dirs_count", 0)
        report["categories"]["test_artifacts"]["freed_bytes"] += test_rep.get("freed_bytes", 0)
        report["categories"]["test_artifacts"]["deleted_dirs_count"] += test_rep.get("deleted_dirs_count", 0)
        report["details"].extend(test_rep.get("details", []))

    return report
