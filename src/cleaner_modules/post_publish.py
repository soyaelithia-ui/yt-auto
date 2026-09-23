"""Post-publication local media cleanup preserving lightweight metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.cleaner_modules.intermediates import clean_run_intermediates
from src.log import get_logger

logger = get_logger("cleaner.post_publish")


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

    # 2. Audio files (.wav, .mp3, .aac, .m4a)
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
