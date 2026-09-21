"""Retention-aware cleanup limited to run-id tagged project resources."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.config import BASE_DIR, DRIVE_KEY_PATH, SETTINGS, is_test_environment
from src.log import get_logger


logger = get_logger("cleaner")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, RuntimeError):
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


def clean_system_cache(
    min_age_seconds: int | None = None,
    dry_run: bool = False,
    root: str | Path | None = None,
) -> dict:
    """Remove only expired work directories carrying a valid project run marker."""
    now = time.time()
    work_dir = Path(root) if root is not None else SETTINGS.work_root
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
    work_dir = Path(root) if root is not None else SETTINGS.work_root
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
        "concat_procedural_scenes.txt",
        "*.tmp.*",
        "*.tmp",
        "safe_area_validation.jpg",
        # R6 / R2: review proxies and compose logs
        "review_proxy_*.mp4",
        "ffmpeg_compose.log",
        "ffmpeg_*.log",
        # R2 audio and scene intermediate chunks
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


def sweep_post_render_scratch(work_dir: str | Path) -> dict:
    """Convenience entrypoint for post-render intermediate scratch artifact sweeping."""
    return clean_run_intermediates(work_dir)


def delete_local_post_publication(
    work_dir: str | Path,
    video_path: str | Path | None = None,
) -> dict[str, Any]:
    """Physically remove local video and audio files from work/<run_id> after verified YouTube + Drive publish.

    Preserves lightweight metadata (.run.json, story.json, telemetry, logs).
    """
    target_dir = Path(work_dir)
    report: dict[str, Any] = {
        "freed_bytes": 0,
        "deleted_files_count": 0,
        "deleted_files": [],
        "errors": [],
    }
    if not target_dir.is_dir():
        return report

    # 1. Video file deletion
    video_targets: set[Path] = set()
    if video_path:
        v = Path(video_path)
        if v.is_file():
            video_targets.add(v)
    for mp4 in target_dir.glob("*.mp4"):
        if mp4.is_file() and not mp4.is_symlink():
            video_targets.add(mp4)

    for v in video_targets:
        try:
            size = v.stat().st_size
            v.unlink()
            report["freed_bytes"] += size
            report["deleted_files_count"] += 1
            report["deleted_files"].append(v.name)
        except OSError as exc:
            report["errors"].append(f"Failed to delete video {v.name}: {exc}")
            logger.warning("Failed to delete local video %s: %s", v, exc)

    # 2. TTS and audio file deletion (.wav, .mp3, .aac, .m4a)
    audio_patterns = ["*.wav", "*.mp3", "*.aac", "*.m4a"]
    for pat in audio_patterns:
        for audio in target_dir.glob(pat):
            if audio.is_file() and not audio.is_symlink():
                try:
                    size = audio.stat().st_size
                    audio.unlink()
                    report["freed_bytes"] += size
                    report["deleted_files_count"] += 1
                    report["deleted_files"].append(audio.name)
                except OSError as exc:
                    report["errors"].append(f"Failed to delete audio {audio.name}: {exc}")
                    logger.warning("Failed to delete local audio %s: %s", audio, exc)

    # 3. Clean intermediate scratch files
    intermediates = clean_run_intermediates(target_dir)
    report["freed_bytes"] += intermediates.get("freed_bytes", 0)
    report["deleted_files_count"] += intermediates.get("deleted_files_count", 0)

    logger.info(
        "Local post-publication cleanup completed for %s: %d files deleted, %d bytes freed",
        target_dir.name,
        report["deleted_files_count"],
        report["freed_bytes"],
    )
    return report


def clean_untracked_temp_files(dry_run: bool = False, root: str | Path | None = None) -> dict:
    """Purge orphaned .tmp.* files and root validation artifacts directly under work_root."""
    work_dir = Path(root) if root is not None else SETTINGS.work_root
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


def clean_orphaned_development_dirs(
    work_root: str | Path | None = None,
    min_age_seconds: int = 3600,
    dry_run: bool = False,
) -> dict:
    """Purge orphaned development directories (e.g. scp_short_*) without valid active runs."""
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


def clean_tts_cache(
    work_root: str | Path | None = None,
    max_age_seconds: int | None = None,
    max_size_bytes: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Prune TTS cache files using TTL and LRU max size limits."""
    now = time.time()
    cache_dirs: list[Path] = []
    if work_root is not None:
        target = Path(work_root)
        if target.name == "tts_cache":
            cache_dirs.append(target)
        else:
            cache_dirs.append(target / "tts_cache")
    else:
        candidates = [
            SETTINGS.work_root / "tts_cache",
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

        # TTL eviction
        if max_age_seconds is not None and max_age_seconds >= 0:
            for key, info in entries.items():
                if (now - info["mtime"]) >= max_age_seconds:
                    to_delete_keys.add(key)

        # LRU eviction by size
        if max_size_bytes is not None and max_size_bytes >= 0:
            remaining_keys = [k for k in entries if k not in to_delete_keys]
            # Sort oldest accessed first
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

        # Remove empty subdirectories
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
    if work_root is not None:
        target = Path(work_root)
        if target.name == "proxy_cache":
            cache_dirs.append(target)
        else:
            cache_dirs.append(target / "proxy_cache")
    else:
        candidates = [
            SETTINGS.work_root / "proxy_cache",
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
        # 1. Clean satisfied runs
        sys_rep = clean_system_cache(dry_run=dry_run, root=root_path)
        report["freed_bytes"] += sys_rep.get("freed_bytes", 0)
        report["deleted_files_count"] += sys_rep.get("deleted_files_count", 0)
        report["deleted_dirs_count"] += sys_rep.get("deleted_dirs_count", 0)
        report["categories"]["satisfied_runs"]["freed_bytes"] += sys_rep.get("freed_bytes", 0)
        report["categories"]["satisfied_runs"]["deleted_dirs_count"] += sys_rep.get("deleted_dirs_count", 0)
        report["details"].extend(sys_rep.get("details", []))

        # 2. Clean failed runs
        fail_rep = clean_expired_failed_runs(dry_run=dry_run, root=root_path)
        report["freed_bytes"] += fail_rep.get("freed_bytes", 0)
        report["deleted_files_count"] += fail_rep.get("deleted_files_count", 0)
        report["deleted_dirs_count"] += fail_rep.get("deleted_dirs_count", 0)
        report["categories"]["failed_runs"]["freed_bytes"] += fail_rep.get("freed_bytes", 0)
        report["categories"]["failed_runs"]["deleted_dirs_count"] += fail_rep.get("deleted_dirs_count", 0)
        report["details"].extend(fail_rep.get("details", []))

        # 3. Clean untracked temp files
        temp_rep = clean_untracked_temp_files(dry_run=dry_run, root=root_path)
        report["freed_bytes"] += temp_rep.get("freed_bytes", 0)
        report["deleted_files_count"] += temp_rep.get("deleted_files_count", 0)
        report["categories"]["temp_files"]["freed_bytes"] += temp_rep.get("freed_bytes", 0)
        report["categories"]["temp_files"]["deleted_files_count"] += temp_rep.get("deleted_files_count", 0)

    # 4. Clean orphan development directories under BASE_DIR / "work"
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

    # 5. Clean caches if requested
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

    # 6. Clean test artifacts if requested
    if include_tests:
        test_rep = clean_test_artifacts(dry_run=dry_run)
        report["freed_bytes"] += test_rep.get("freed_bytes", 0)
        report["deleted_files_count"] += test_rep.get("deleted_files_count", 0)
        report["deleted_dirs_count"] += test_rep.get("deleted_dirs_count", 0)
        report["categories"]["test_artifacts"]["freed_bytes"] += test_rep.get("freed_bytes", 0)
        report["categories"]["test_artifacts"]["deleted_dirs_count"] += test_rep.get("deleted_dirs_count", 0)
        report["details"].extend(test_rep.get("details", []))

    return report
