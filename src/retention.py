"""Safe local-retention markers for verified YouTube publications."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from src.config import SETTINGS
from src.log import get_logger


logger = get_logger("retention")


def _warning(reason: str) -> bool:
    logger.warning("Local retention marker not updated: %s", reason)
    return False


def mark_run_retention_satisfied(
    video_path: str | os.PathLike[str],
    published_id: str | None = None,
    published_url: str | None = None,
) -> bool:
    """Atomically mark a verified publication without deleting local files."""
    try:
        work_root = Path(os.path.realpath(os.fspath(SETTINGS.work_root)))
        video = Path(os.path.realpath(os.fspath(video_path)))
        if not video.is_file():
            return _warning("published video is not a local file")
        relative = video.relative_to(work_root)
        if len(relative.parts) < 2 or relative.name == ".run.json":
            return _warning("published video is not under work/<run_id>")
        run_id = relative.parts[0]
        run_dir = work_root / run_id
        marker = run_dir / ".run.json"
        if Path(os.path.realpath(os.fspath(marker))) != marker:
            return _warning("run marker resolves outside work")
        if not marker.is_file():
            return _warning("valid run marker was not found")
        metadata = json.loads(marker.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            return _warning("run marker is not a JSON object")
        if metadata.get("run_id") != run_id:
            return _warning("run marker run_id does not match its directory")
        if metadata.get("active") is not False:
            return _warning("run marker is still active")

        metadata["retention_satisfied"] = True
        if isinstance(published_id, str) and published_id.strip():
            metadata["published_id"] = published_id
        if isinstance(published_url, str) and published_url.strip():
            metadata["published_url"] = published_url

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".run.json.", dir=os.fspath(marker.parent)
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
                json.dump(metadata, temporary, ensure_ascii=False, sort_keys=True)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, marker)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
        return True
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return _warning(f"invalid or inaccessible run marker ({type(exc).__name__})")
