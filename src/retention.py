"""Safe local-retention markers for verified YouTube publications."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from src.config import BASE_DIR, SETTINGS
from src.log import get_logger


logger = get_logger("retention")


def _warning(reason: str) -> bool:
    logger.warning("Local retention marker not updated: %s", reason)
    return False


def _find_work_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        roots.append(Path(os.path.realpath(os.fspath(SETTINGS.work_root))))
    except Exception:
        pass
    for sub in ["", "cli", "prod", "test"]:
        cand = (
            Path(os.path.realpath(os.fspath(BASE_DIR / "work" / sub)))
            if sub
            else Path(os.path.realpath(os.fspath(BASE_DIR / "work")))
        )
        if cand not in roots:
            roots.append(cand)
    return roots


def mark_run_retention_satisfied(
    video_path: str | os.PathLike[str],
    published_id: str | None = None,
    published_url: str | None = None,
) -> bool:
    """Atomically mark a verified publication without deleting local files."""
    try:
        video = Path(os.path.realpath(os.fspath(video_path)))
        if not video.is_file():
            return _warning("published video is not a local file")

        work_roots = _find_work_roots()
        relative = None
        work_root = None
        for root in work_roots:
            try:
                rel = video.relative_to(root)
                if len(rel.parts) >= 2 and rel.name != ".run.json":
                    relative = rel
                    work_root = root
                    break
            except ValueError:
                continue

        if relative is None or work_root is None:
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


def is_run_retention_satisfied(run_dir: str | os.PathLike[str]) -> bool:
    """Check whether a run directory has its retention satisfied flag set."""
    try:
        path = Path(run_dir)
        marker = path / ".run.json"
        if not marker.is_file():
            return False
        metadata = json.loads(marker.read_text(encoding="utf-8"))
        return isinstance(metadata, dict) and metadata.get("retention_satisfied") is True
    except Exception:
        return False


def get_run_metadata(run_dir: str | os.PathLike[str]) -> dict[str, Any] | None:
    """Read run metadata from .run.json safely."""
    try:
        path = Path(run_dir)
        marker = path / ".run.json"
        if not marker.is_file():
            return None
        metadata = json.loads(marker.read_text(encoding="utf-8"))
        return metadata if isinstance(metadata, dict) else None
    except Exception:
        return None
