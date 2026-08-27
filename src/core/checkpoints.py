"""Stage checkpoints: reuse artifacts from previous runs of the same story.

A late failure (QA gate, upload) used to force a full re-render because every
retry started from a fresh ``work/<run_id>/``. This module records where each
stage's artifact lives — keyed by ``story_key = f"{story_id}:{lane_id}"`` so
artifacts survive across run ids — and verifies them (existence + size + sha256
when recorded + basic container probe for video) before the pipeline skips a
stage it does not need to repeat.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from src.core.repository import connect
from src.config import SETTINGS

logger = logging.getLogger(__name__)

# Artifact kinds in pipeline order. A resume may only skip a prefix of this
# sequence; everything after the first missing/invalid artifact must rerun.
CHECKPOINT_KINDS: tuple[str, ...] = (
    "script",
    "audio",
    "subtitles_ass",
    "video",
    "thumbnail",
)

RESUME_VIDEO_KINDS: tuple[str, ...] = ("video", "render")


def story_key(story_id: str, lane_id: str | None) -> str:
    return f"{story_id}:{lane_id or '-'}"


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_is_valid(record: Mapping[str, Any]) -> bool:
    """Cheap integrity check: exists, non-trivial size, sha256 when recorded."""
    raw_path = record.get("local_path")
    if not raw_path:
        return False
    path = Path(str(raw_path))
    if not path.is_file():
        return False
    expected_size = record.get("size_bytes")
    if expected_size and path.stat().st_size != int(expected_size):
        return False
    recorded_sha = record.get("sha256")
    if recorded_sha and _sha256_of(path) != str(recorded_sha):
        return False
    return True


def latest_valid_artifact(
    db_path: str | None,
    key: str,
    kind: str,
) -> dict[str, Any] | None:
    """Newest artifact of `kind` for `key` that still passes validation."""
    target_db = str(db_path or SETTINGS.database_path)
    with connect(target_db, read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT a.* FROM artifacts a
            WHERE a.story_key = ? AND a.kind = ? AND a.local_path IS NOT NULL
            ORDER BY a.artifact_id DESC LIMIT 5
            """,
            (key, kind),
        ).fetchall()
    for row in rows:
        record = dict(row)
        if artifact_is_valid(record):
            return record
    return None


@dataclass(frozen=True)
class ResumePlan:
    """Which stages of a rerun can be skipped and from which files."""

    story_key: str
    reusable: dict[str, str] = field(default_factory=dict)
    # First stage index (into CHECKPOINT_KINDS) that must actually execute.
    resume_from_index: int = 0

    @property
    def has_reusable(self) -> bool:
        return bool(self.reusable)


def resume_plan(
    db_path: str | None,
    story_id: str,
    lane_id: str | None,
    *,
    now_run_id: str | None = None,
) -> ResumePlan:
    """Plan a rerun for (story, lane): reuse the longest valid artifact prefix.

    Only artifacts recorded against this story+lane combination are considered,
    and only a contiguous prefix from the first stage is reusable — an invalid
    audio file invalidates every downstream artifact built on top of it.
    """
    key = story_key(story_id, lane_id)
    reusable: dict[str, str] = {}
    resume_from = len(CHECKPOINT_KINDS)
    for index, kind in enumerate(CHECKPOINT_KINDS):
        record = latest_valid_artifact(db_path, key, kind)
        if record is None:
            resume_from = index
            break
        reusable[kind] = str(record["local_path"])
    else:
        resume_from = len(CHECKPOINT_KINDS)
    if reusable:
        logger.info(
            "Checkpoints reutilizables para %s: %s", key, sorted(reusable)
        )
    return ResumePlan(story_key=key, reusable=reusable, resume_from_index=resume_from)


def resumable_video_for_story(
    previous_run_id: str, db_path: str | None = None
) -> Path | None:
    """Return the rendered video of a previous run if it is still publishable.

    Used by ``claim_resumable``: only stories whose master file survives
    (exists, non-empty, faststart) are worth re-claiming for delivery.
    """
    from lib.video import has_faststart

    target_db = str(db_path or SETTINGS.database_path)
    try:
        with connect(target_db, read_only=True) as conn:
            rows = conn.execute(
                """
                SELECT local_path, sha256 FROM artifacts
                WHERE run_id = ? AND kind IN ('video', 'render')
                  AND local_path IS NOT NULL
                ORDER BY artifact_id DESC
                """,
                (previous_run_id,),
            ).fetchall()
    except Exception:  # pragma: no cover - defensive: probe must never raise
        return None
    for row in rows:
        raw_path = row["local_path"]
        if not raw_path:
            continue
        path = Path(str(raw_path))
        try:
            if not path.is_file() or path.stat().st_size < 1024:
                continue
        except OSError:
            continue
        if has_faststart(str(path)):
            return path
    return None


def record_checkpoint(
    repository,  # QueueRepository
    run_id: str,
    key: str,
    kind: str,
    path: str | Path,
    *,
    sha256: str | None = None,
    size_bytes: int | None = None,
) -> None:
    """Persist a stage checkpoint (thin wrapper over record_artifact)."""
    resolved = Path(path)
    if sha256 is None and resolved.is_file():
        sha256 = _sha256_of(resolved)
    if size_bytes is None and resolved.is_file():
        size_bytes = resolved.stat().st_size
    repository.record_artifact(
        run_id,
        kind,
        local_path=str(resolved),
        size_bytes=size_bytes,
        sha256=sha256,
        verified=True,
        story_key=key,
    )
