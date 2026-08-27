"""Fail-closed publication adapter used after review's gate."""

from __future__ import annotations

import json
import sys
from typing import Any, Dict

from src.branding import get_channel_branding
from src.config import SETTINGS, get_channel_settings
from src.drive import move_drive_file, upload_to_drive_verified
from src.log import get_logger
from src.retention import mark_run_retention_satisfied
from src.youtube.uploader import upload_video

from review import BaseReviewPublicationAdapter

PROJECT = "YTShort"
logger = get_logger("review_publication_adapter")


class YTShortPublicationAdapter(BaseReviewPublicationAdapter):
    project_name = PROJECT


def _required_payload(payload: Dict[str, Any]) -> tuple[str, int, str]:
    return BaseReviewPublicationAdapter.validate_payload(payload)


def _verify_core_claim(job_id: str, version: int, original_video_path: str) -> None:
    BaseReviewPublicationAdapter.verify_core_claim(job_id, version, original_video_path)


def _backup_drive(
    *,
    job_id: str,
    channel: str,
    original_video_path: str,
    thumbnail_path: str | None,
    version: int,
    title: str,
    description: str,
    settings: Any,
) -> dict[str, Any]:
    upload_fn = getattr(sys.modules[__name__], "upload_to_drive_verified", upload_to_drive_verified)

    def verified_upload(file_path: str, **kwargs: Any) -> Any:
        """Adapt the review-core upload contract to the Drive client contract."""
        return upload_fn(
            file_path,
            folder_id=str(kwargs["folder_id"]),
            sa_key_path=str(getattr(SETTINGS, "drive_key_path", "")),
            display_name=kwargs.get("display_name"),
            idempotency_key=kwargs.get("idempotency_key"),
        )

    return BaseReviewPublicationAdapter.backup_drive(
        job_id=job_id,
        channel=channel,
        original_video_path=original_video_path,
        thumbnail_path=thumbnail_path,
        version=version,
        title=title,
        description=description,
        settings=settings,
        global_settings=getattr(sys.modules[__name__], "SETTINGS", SETTINGS),
        upload_fn=verified_upload,
        project_name=PROJECT,
    )


def _sync_queue_db(
    job_id: str,
    youtube_result: Dict[str, Any],
    db_path: str | None = None,
) -> None:
    """Sync queue.db (runs, stories, publications) upon successful video publication."""
    try:
        import os
        import sqlite3
        from datetime import datetime, timezone

        target_db = db_path or str(getattr(SETTINGS, "database_path", ""))
        if not os.path.exists(target_db):
            return

        video_id = str(youtube_result.get("video_id") or youtube_result.get("id") or "").strip()
        url = str(youtube_result.get("url") or (f"https://www.youtube.com/watch?v={video_id}" if video_id else "")).strip()
        channel = str(youtube_result.get("channel") or "moku")
        visibility = str(youtube_result.get("visibility") or "public")
        title = str(youtube_result.get("title") or "")
        description = str(youtube_result.get("description") or "")
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with sqlite3.connect(target_db, timeout=30.0) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=15000;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("BEGIN IMMEDIATE;")
            story_row = conn.execute(
                "SELECT story_id, run_id FROM stories WHERE story_id = ?", (job_id,)
            ).fetchone()
            run_id = story_row[1] if story_row else None
            if not run_id:
                run_row = conn.execute(
                    "SELECT run_id FROM runs WHERE run_id = ?", (job_id,)
                ).fetchone()
                if run_row:
                    run_id = run_row[0]

            if run_id:
                conn.execute(
                    "UPDATE runs SET status = 'PUBLISHED', finished_at = ? WHERE run_id = ?",
                    (now_iso, run_id),
                )
            if story_row:
                conn.execute(
                    """UPDATE stories SET status = 'PUBLISHED', youtube_video_id = ?, youtube_url = ?, 
                       publication_visibility = ?, publication_channel = ?, updated_at = CURRENT_TIMESTAMP 
                       WHERE story_id = ?""",
                    (video_id, url, visibility, channel, job_id),
                )
            if run_id and video_id:
                pub_exists = conn.execute(
                    "SELECT 1 FROM publications WHERE run_id = ? AND video_id = ?",
                    (run_id, video_id),
                ).fetchone()
                if not pub_exists:
                    conn.execute(
                        """INSERT INTO publications(
                            run_id, story_id, provider, video_id, url, channel,
                            visibility, title, description, thumbnail_confirmed, verified_at
                        ) VALUES (?, ?, 'YOUTUBE_DATA_API_V3', ?, ?, ?, ?, ?, ?, 1, ?)""",
                        (run_id, job_id, video_id, url, channel, visibility, title, description, now_iso),
                    )
            conn.commit()
            logger.info("Synced queue.db for job_id=%s run_id=%s video_id=%s", job_id, run_id, video_id)
    except Exception as exc:
        logger.warning("Could not sync queue.db for job_id %s: %s", job_id, exc)


def publish(payload: Dict[str, Any]) -> Dict[str, Any]:
    job_id, version, original_video_path = _required_payload(payload)
    verify_fn = getattr(sys.modules[__name__], "_verify_core_claim", _verify_core_claim)
    verify_fn(job_id, version, original_video_path)

    channel = str(payload.get("channel") or "terror")
    settings = get_channel_settings(channel)
    branding = get_channel_branding(channel)
    title = str(payload.get("title") or "")
    description = str(payload.get("description") or "")
    backup_fn = getattr(sys.modules[__name__], "_backup_drive", _backup_drive)
    drive_backup = backup_fn(
        job_id=job_id,
        channel=channel,
        original_video_path=original_video_path,
        thumbnail_path=payload.get("thumbnail_path"),
        version=version,
        title=title,
        description=description,
        settings=settings,
    )
    uploader_fn = getattr(sys.modules[__name__], "upload_video", upload_video)
    youtube_result = uploader_fn(
        video_path=original_video_path,
        title=title,
        description=description,
        tags=branding.tags,
        channel=channel,
        thumbnail_path=payload.get("thumbnail_path"),
        token_path=str(settings.youtube_token_path),
        expected_channel_id=settings.expected_youtube_channel_id,
        job_id=job_id,
        version=version,
    )
    if not isinstance(youtube_result, dict):
        raise TypeError("YouTube uploader must return a JSON object")
    retention_satisfied = False
    retention_warning: str | None = None
    if (
        str(youtube_result.get("status") or "").upper() == "PUBLISHED"
        and youtube_result.get("verified") is True
    ):
        sync_fn = getattr(sys.modules[__name__], "_sync_queue_db", _sync_queue_db)
        sync_fn(job_id, youtube_result)

        retention_satisfied = mark_run_retention_satisfied(
            original_video_path,
            published_id=youtube_result.get("video_id"),
            published_url=youtube_result.get("url"),
        )
        if not retention_satisfied:
            retention_warning = "No se encontró un marcador de run válido; se conserva el material local"
            logger.warning(retention_warning)

        published_folder = str(getattr(SETTINGS, "drive_published_folder_id", "") or "").strip()
        if published_folder and isinstance(drive_backup, dict):
            for key in ("video", "cover", "metadata"):
                item = drive_backup.get(key)
                if isinstance(item, dict) and item.get("status") == "verified" and item.get("file_id"):
                    try:
                        moved = move_drive_file(
                            item["file_id"],
                            target_folder_id=published_folder,
                            sa_key_path=str(SETTINGS.drive_key_path),
                            token_path=str(settings.youtube_token_path),
                        )
                        item["moved_to_published"] = moved
                    except Exception as move_exc:
                        logger.warning("No se pudo mover el archivo de Drive %s a %s: %s", item["file_id"], published_folder, move_exc)
                        item["moved_to_published"] = False
    result = dict(youtube_result)
    result["youtube_result"] = youtube_result
    result["drive_backup"] = drive_backup
    result["retention_satisfied"] = retention_satisfied
    if retention_warning:
        result["retention_warning"] = retention_warning
    return result


def main() -> int:
    payload = json.load(sys.stdin)
    result = publish(payload)
    if not isinstance(result, dict):
        raise TypeError("Publication adapter must return a JSON object")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
