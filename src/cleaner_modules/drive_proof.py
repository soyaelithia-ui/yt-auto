"""Drive verification and remote-proven artifact cleanup."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Mapping

from src.config import DRIVE_KEY_PATH, SETTINGS, is_test_environment
from src.log import get_logger

logger = get_logger("cleaner.drive_proof")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, RuntimeError):
        return False


def _get_active_settings():
    cleaner_mod = sys.modules.get("src.cleaner")
    if cleaner_mod and hasattr(cleaner_mod, "SETTINGS"):
        return cleaner_mod.SETTINGS
    return SETTINGS


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

    active_settings = _get_active_settings()
    if not (
        _inside(target, active_settings.work_root)
        or _inside(target, active_settings.artifact_root)
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
            getattr(active_settings, "drive_folder_id", ""),
            getattr(active_settings, "drive_published_folder_id", ""),
            getattr(active_settings, "drive_approved_video_folder_id", ""),
            getattr(active_settings, "drive_root_folder_id", ""),
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
