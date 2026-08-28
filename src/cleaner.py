"""Retention-aware cleanup limited to run-id tagged project resources."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Mapping

from src.config import DRIVE_KEY_PATH, SETTINGS, is_test_environment
from src.log import get_logger


logger = get_logger("cleaner")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def verify_and_cleanup(
    file_path: str,
    drive_file_id: str,
    sa_key_path: str = DRIVE_KEY_PATH,
    *,
    remote_proof: Mapping[str, Any] | None = None,
    retention_seconds: int | None = None,
) -> bool:
    """Delete only a retained project artifact with complete Drive proof."""
    target = Path(file_path)
    if not target.is_file():
        return False
    if not (
        _inside(target, SETTINGS.work_root)
        or _inside(target, SETTINGS.artifact_root)
    ):
        logger.warning("Cleanup blocked outside project work/artifact roots")
        return False
    if not drive_file_id or not remote_proof:
        logger.warning("Cleanup blocked: complete Drive proof is required")
        return False
    expected = {
        "id": drive_file_id,
        "name": target.name,
        "size": target.stat().st_size,
        "exists": True,
    }
    for key, value in expected.items():
        if remote_proof.get(key) != value:
            logger.warning("Cleanup blocked: Drive proof mismatch for %s", key)
            return False
    parents = remote_proof.get("parents") or []
    authorized_folders = {
        f
        for f in (
            getattr(SETTINGS, "drive_folder_id", ""),
            getattr(SETTINGS, "drive_published_folder_id", ""),
            getattr(SETTINGS, "drive_approved_video_folder_id", ""),
            getattr(SETTINGS, "drive_root_folder_id", ""),
        )
        if f
    }
    if authorized_folders and not any(p in authorized_folders for p in parents):
        logger.warning("Cleanup blocked: Drive folder was not confirmed in authorized folders (%s)", parents)
        return False
    retention = (
        retention_seconds
        if retention_seconds is not None
        else (0 if is_test_environment() else int(os.environ.get("LOCAL_RETENTION_SECONDS", "604800")))
    )
    if retention < 0 or (retention > 0 and time.time() - target.stat().st_mtime < retention):
        logger.info("Cleanup deferred by retention policy")
        return False
    target.unlink()
    logger.info("Deleted retained local artifact after verified Drive backup")
    return True


def clean_system_cache(min_age_seconds: int | None = None, dry_run: bool = False) -> dict:
    """Remove only expired work directories carrying a valid project run marker."""
    now = time.time()
    root = SETTINGS.work_root
    report = {
        "freed_bytes": 0,
        "deleted_files_count": 0,
        "deleted_dirs_count": 0,
        "dry_run": dry_run,
        "details": [],
    }
    if not root.exists():
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
    for run_dir in root.iterdir():
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
        size = sum(
            item.stat().st_size
            for item in run_dir.rglob("*")
            if item.is_file() and not item.is_symlink()
        )
        if not dry_run:
            shutil.rmtree(run_dir)
        report["freed_bytes"] += size
        report["deleted_dirs_count"] += 1
        report["details"].append({"run_id": run_id, "bytes": size})
    return report


def clean_expired_failed_runs(min_age_seconds: int | None = None, dry_run: bool = False) -> dict:
    """Reclaim failed run directories (active == False, retention_satisfied == False) older than min_age_seconds."""
    now = time.time()
    root = SETTINGS.work_root
    report = {
        "freed_bytes": 0,
        "deleted_files_count": 0,
        "deleted_dirs_count": 0,
        "dry_run": dry_run,
        "details": [],
    }
    if not root.exists():
        return report
    if min_age_seconds is None:
        if is_test_environment():
            min_age_seconds = 0
        else:
            try:
                min_age_seconds = int(os.environ.get("FAILED_RUN_RETENTION_SECONDS", "86400"))
            except ValueError:
                min_age_seconds = 86400
    if min_age_seconds < 0:
        return report
    for run_dir in root.iterdir():
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
            size = sum(
                item.stat().st_size
                for item in run_dir.rglob("*")
                if item.is_file() and not item.is_symlink()
            )
            if not dry_run:
                shutil.rmtree(run_dir)
            report["freed_bytes"] += size
            report["deleted_dirs_count"] += 1
            report["details"].append({"run_id": run_id, "bytes": size})
    return report


def clean_run_intermediates(work_dir: str | Path) -> dict:
    """Remove intermediate rendering artifacts from a work directory."""
    target_dir = Path(work_dir)
    report = {"freed_bytes": 0, "deleted_files_count": 0}
    if not target_dir.is_dir():
        return report
    patterns = [
        "prescaled_*.jpg",
        "concat_list.txt",
        "loop_concat_list.txt",
        "*.tmp.*",
        "safe_area_validation.jpg",
        # R6: review proxies and compose logs are lineage-recorded before any
        # cleanup runs, so sweeping them post-run is safe.
        "review_proxy_*.mp4",
        "ffmpeg_compose.log",
    ]
    for pattern in patterns:
        for item in target_dir.glob(pattern):
            if item.is_file() and not item.is_symlink():
                try:
                    size = item.stat().st_size
                    item.unlink()
                    report["freed_bytes"] += size
                    report["deleted_files_count"] += 1
                except OSError as exc:
                    logger.debug("Failed to remove intermediate file %s: %s", item, exc)
    return report


def clean_untracked_temp_files(dry_run: bool = False) -> dict:
    """Purge orphaned .tmp.* files and root validation artifacts directly under SETTINGS.work_root."""
    root = SETTINGS.work_root
    report = {"freed_bytes": 0, "deleted_files_count": 0, "dry_run": dry_run}
    if not root.exists():
        return report
    for item in root.glob(".tmp.*"):
        if item.is_file() and not item.is_symlink():
            try:
                size = item.stat().st_size
                if not dry_run:
                    item.unlink()
                report["freed_bytes"] += size
                report["deleted_files_count"] += 1
            except OSError as exc:
                logger.debug("Failed to remove untracked temp file %s: %s", item, exc)
    root_safe_area = root / "safe_area_validation.jpg"
    if root_safe_area.is_file():
        try:
            size = root_safe_area.stat().st_size
            if not dry_run:
                root_safe_area.unlink()
            report["freed_bytes"] += size
            report["deleted_files_count"] += 1
        except OSError as exc:
            logger.debug("Failed to remove root safe_area_validation.jpg: %s", exc)
    return report
