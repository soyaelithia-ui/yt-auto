"""Cleaner module for intermediate rendering, scratch files, caches, and test artifacts."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from src.config import BASE_DIR, SETTINGS
from src.log import get_logger

logger = get_logger("cleaner.intermediates")


def _get_active_settings():
    cleaner_mod = sys.modules.get("src.cleaner")
    if cleaner_mod and hasattr(cleaner_mod, "SETTINGS"):
        return cleaner_mod.SETTINGS
    return SETTINGS


def clean_run_intermediates(work_dir: str | Path) -> dict[str, int]:
    """Remove intermediate rendering artifacts from a work directory."""
    target_dir = Path(work_dir)
    report = {"freed_bytes": 0, "deleted_files_count": 0}
    if not target_dir.is_dir():
        return report
    patterns = [
        "prescaled_*.jpg",
        "concat_list.txt",
        "loop_concat_list.txt",
        "concat_procedural_scenes.txt",
        "*.tmp.*",
        "*.tmp",
        "safe_area_validation.jpg",
        "review_proxy_*.mp4",
        "ffmpeg_compose.log",
        "ffmpeg_*.log",
        "procedural_ambient_*.wav",
        "procedural_*.wav",
        "scene_*.mp4",
        "segment_*.mp4",
        "loop_*.mp4",
        "frame_*.png",
        "frame_*.jpg",
    ]
    seen_paths = set()
    for pattern in patterns:
        for item in target_dir.glob(pattern):
            if item.is_file() and not item.is_symlink() and item not in seen_paths:
                seen_paths.add(item)
                try:
                    size = item.stat().st_size
                    item.unlink()
                    report["freed_bytes"] += size
                    report["deleted_files_count"] += 1
                except OSError as exc:
                    logger.debug("Failed to remove intermediate file %s: %s", item, exc)
    return report


def sweep_post_render_scratch(work_dir: str | Path) -> dict[str, int]:
    """Convenience entrypoint for post-render intermediate scratch artifact sweeping."""
    return clean_run_intermediates(work_dir)


def clean_untracked_temp_files(dry_run: bool = False, root: str | Path | None = None) -> dict:
    """Purge orphaned .tmp.* files and root validation artifacts directly under work_root."""
    active_settings = _get_active_settings()
    work_dir = Path(root) if root is not None else active_settings.work_root
    report = {"freed_bytes": 0, "deleted_files_count": 0, "dry_run": dry_run}
    if not work_dir.exists():
        return report
    for item in list(work_dir.glob(".tmp.*")) + list(work_dir.glob("*.tmp")):
        if item.is_file() and not item.is_symlink():
            try:
                size = item.stat().st_size
                if not dry_run:
                    item.unlink()
                report["freed_bytes"] += size
                report["deleted_files_count"] += 1
            except OSError as exc:
                logger.debug("Failed to remove untracked temp file %s: %s", item, exc)
    root_safe_area = work_dir / "safe_area_validation.jpg"
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


def clean_tts_cache(
    work_root: str | Path | None = None,
    max_age_seconds: int | None = None,
    max_size_bytes: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Prune TTS cache files using TTL and LRU max size limits."""
    now = time.time()
    cache_dirs: list[Path] = []
    active_settings = _get_active_settings()
    if work_root is not None:
        target = Path(work_root)
        if target.name == "tts_cache":
            cache_dirs.append(target)
        else:
            cache_dirs.append(target / "tts_cache")
    else:
        candidates = [
            active_settings.work_root / "tts_cache",
            BASE_DIR / "work" / "cli" / "tts_cache",
            BASE_DIR / "work" / "tts_cache",
            BASE_DIR / "work" / "test" / "tts_cache",
        ]
        for c in candidates:
            if c.exists() and c.is_dir() and c not in cache_dirs:
                cache_dirs.append(c)

    report = {
        "freed_bytes": 0,
        "deleted_files_count": 0,
        "dry_run": dry_run,
        "details": [],
    }

    for c_dir in cache_dirs:
        if not c_dir.exists() or not c_dir.is_dir():
            continue

        entries: dict[str, dict[str, Any]] = {}
        for file_path in c_dir.rglob("*"):
            if not file_path.is_file() or file_path.is_symlink():
                continue
            key_stem = file_path.stem
            if key_stem not in entries:
                entries[key_stem] = {
                    "files": [],
                    "size": 0,
                    "mtime": 0.0,
                    "atime": 0.0,
                }
            st = file_path.stat()
            entries[key_stem]["files"].append(file_path)
            entries[key_stem]["size"] += st.st_size
            entries[key_stem]["mtime"] = max(entries[key_stem]["mtime"], st.st_mtime)
            entries[key_stem]["atime"] = max(entries[key_stem]["atime"], getattr(st, "st_atime", st.st_mtime))

        to_delete_keys = set()

        if max_age_seconds is not None and max_age_seconds >= 0:
            for key, info in entries.items():
                if (now - info["mtime"]) >= max_age_seconds:
                    to_delete_keys.add(key)

        if max_size_bytes is not None and max_size_bytes >= 0:
            remaining_keys = [k for k in entries if k not in to_delete_keys]
            remaining_keys.sort(key=lambda k: entries[k]["atime"])
            current_total = sum(entries[k]["size"] for k in remaining_keys)
            for k in remaining_keys:
                if current_total <= max_size_bytes:
                    break
                to_delete_keys.add(k)
                current_total -= entries[k]["size"]

        for k in to_delete_keys:
            info = entries[k]
            for f in info["files"]:
                try:
                    size = f.stat().st_size
                    if not dry_run:
                        f.unlink(missing_ok=True)
                    report["freed_bytes"] += size
                    report["deleted_files_count"] += 1
                except OSError as exc:
                    logger.debug("Failed to delete tts cache file %s: %s", f, exc)
            report["details"].append({"key": k, "bytes": info["size"]})

        if not dry_run:
            for sub in list(c_dir.iterdir()):
                if sub.is_dir() and not sub.is_symlink() and not any(sub.iterdir()):
                    try:
                        sub.rmdir()
                    except OSError as exc:
                        logger.debug("Could not rmdir empty subdir %s: %s", sub, exc)

    return report


def clean_proxy_cache(
    work_root: str | Path | None = None,
    max_age_seconds: int | None = None,
    max_size_bytes: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Prune video review proxy cache files using TTL and LRU max size limits."""
    now = time.time()
    cache_dirs: list[Path] = []
    active_settings = _get_active_settings()
    if work_root is not None:
        target = Path(work_root)
        if target.name == "proxy_cache":
            cache_dirs.append(target)
        else:
            cache_dirs.append(target / "proxy_cache")
    else:
        candidates = [
            active_settings.work_root / "proxy_cache",
            BASE_DIR / "work" / "cli" / "proxy_cache",
            BASE_DIR / "work" / "proxy_cache",
            BASE_DIR / "work" / "test" / "proxy_cache",
        ]
        for c in candidates:
            if c.exists() and c.is_dir() and c not in cache_dirs:
                cache_dirs.append(c)

    report = {
        "freed_bytes": 0,
        "deleted_files_count": 0,
        "dry_run": dry_run,
        "details": [],
    }

    for c_dir in cache_dirs:
        if not c_dir.exists() or not c_dir.is_dir():
            continue

        files: list[dict[str, Any]] = []
        for file_path in c_dir.glob("*.mp4"):
            if not file_path.is_file() or file_path.is_symlink():
                continue
            st = file_path.stat()
            files.append({
                "path": file_path,
                "size": st.st_size,
                "mtime": st.st_mtime,
                "atime": getattr(st, "st_atime", st.st_mtime),
            })

        to_delete = set()

        if max_age_seconds is not None and max_age_seconds >= 0:
            for item in files:
                if (now - item["mtime"]) >= max_age_seconds:
                    to_delete.add(item["path"])

        if max_size_bytes is not None and max_size_bytes >= 0:
            remaining = [item for item in files if item["path"] not in to_delete]
            remaining.sort(key=lambda item: item["atime"])
            current_total = sum(item["size"] for item in remaining)
            for item in remaining:
                if current_total <= max_size_bytes:
                    break
                to_delete.add(item["path"])
                current_total -= item["size"]

        for item in files:
            if item["path"] in to_delete:
                try:
                    size = item["size"]
                    if not dry_run:
                        item["path"].unlink(missing_ok=True)
                    report["freed_bytes"] += size
                    report["deleted_files_count"] += 1
                    report["details"].append({"file": item["path"].name, "bytes": size})
                except OSError as exc:
                    logger.debug("Failed to delete proxy cache file %s: %s", item["path"], exc)

        if not dry_run:
            for sub in list(c_dir.iterdir()):
                if sub.is_dir() and not sub.is_symlink() and not any(sub.iterdir()):
                    try:
                        sub.rmdir()
                    except OSError as exc:
                        logger.debug("Could not rmdir empty subdir %s: %s", sub, exc)

    return report


def clean_test_artifacts(
    test_work_root: str | Path | None = None,
    min_age_seconds: int = 0,
    dry_run: bool = False,
) -> dict:
    """Purge accumulated test artifacts and temporary execution directories under work/test."""
    now = time.time()
    test_root = Path(test_work_root) if test_work_root is not None else (BASE_DIR / "work" / "test")
    report = {
        "freed_bytes": 0,
        "deleted_files_count": 0,
        "deleted_dirs_count": 0,
        "dry_run": dry_run,
        "details": [],
    }
    if not test_root.exists():
        return report

    for item in test_root.iterdir():
        if item.is_symlink():
            continue
        if item.is_dir():
            mtime = item.stat().st_mtime
            if min_age_seconds > 0 and (now - mtime < min_age_seconds):
                continue
            size = 0
            file_count = 0
            for f in item.rglob("*"):
                if f.is_file() and not f.is_symlink():
                    size += f.stat().st_size
                    file_count += 1
            if not dry_run:
                import shutil
                shutil.rmtree(item)
            report["freed_bytes"] += size
            report["deleted_files_count"] += file_count
            report["deleted_dirs_count"] += 1
            report["details"].append({"item": item.name, "bytes": size})
        elif item.is_file():
            mtime = item.stat().st_mtime
            if min_age_seconds > 0 and (now - mtime < min_age_seconds):
                continue
            size = item.stat().st_size
            if not dry_run:
                item.unlink(missing_ok=True)
            report["freed_bytes"] += size
            report["deleted_files_count"] += 1
            report["details"].append({"item": item.name, "bytes": size})

    return report
