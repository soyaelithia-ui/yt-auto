"""Modular cleaner facade for retention-aware cleanup limited to run-id tagged project resources."""

from __future__ import annotations

from src.cleaner_modules.drive_proof import _inside, verify_and_cleanup
from src.cleaner_modules.intermediates import (
    clean_proxy_cache,
    clean_run_intermediates,
    clean_test_artifacts,
    clean_tts_cache,
    clean_untracked_temp_files,
    sweep_post_render_scratch,
)
from src.cleaner_modules.post_publish import delete_local_post_publication
from src.cleaner_modules.work_dirs import (
    clean_all_work_roots,
    clean_expired_failed_runs,
    clean_orphaned_development_dirs,
    clean_system_cache,
)
from src.config import BASE_DIR, DRIVE_KEY_PATH, SETTINGS, is_test_environment
from src.log import get_logger

logger = get_logger("cleaner")

__all__ = [
    "BASE_DIR",
    "DRIVE_KEY_PATH",
    "SETTINGS",
    "is_test_environment",
    "logger",
    "_inside",
    "verify_and_cleanup",
    "clean_system_cache",
    "clean_expired_failed_runs",
    "clean_run_intermediates",
    "sweep_post_render_scratch",
    "delete_local_post_publication",
    "clean_untracked_temp_files",
    "clean_orphaned_development_dirs",
    "clean_tts_cache",
    "clean_proxy_cache",
    "clean_test_artifacts",
    "clean_all_work_roots",
]
