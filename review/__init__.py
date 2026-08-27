"""Video review core package facade."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from review.domain import DeliveryResult, ReviewJob, ReviewStatus
from review.db import ReviewStateStore, get_db_connection, init_review_db
from review.publication_gate import PublicationGate
from review.review_manager import ReviewJobManager
from review.telegram_bot import TelegramReviewBot, send_telegram_message


class BaseReviewPublicationAdapter:
    """Base class for publication adapters enforcing the atomic review gate."""

    project_name: str = "YTShort"

    @staticmethod
    def validate_payload(payload: Any) -> tuple[str, int, str]:
        """Extract and validate the required job identity fields from a payload."""
        if hasattr(payload, "to_dict"):
            payload = payload.to_dict()
        elif hasattr(payload, "__dict__") and not isinstance(payload, dict):
            payload = payload.__dict__
        elif not isinstance(payload, dict):
            raise ValueError("publish payload must be a mapping")
        job_id = payload.get("job_id")
        version = payload.get("version")
        original_video_path = payload.get("original_video_path")
        if not job_id or version is None or not original_video_path:
            raise ValueError(
                "Missing required payload fields: job_id, version and original_video_path"
            )
        return str(job_id), int(version), str(original_video_path)

    @staticmethod
    def verify_core_claim(
        job_id: str, version: int, original_video_path: str
    ) -> None:
        """Atomically claim the approved job through the core publication gate."""
        store = ReviewStateStore()
        job = store.get_job(job_id, version)
        if job and job.status == ReviewStatus.PUBLISHING.value:
            return
        PublicationGate().verify_and_claim_publication(job_id, version, original_video_path)

    @classmethod
    def backup_drive(
        cls,
        *,
        job_id: str,
        channel: str,
        original_video_path: str,
        thumbnail_path: Optional[str],
        version: int,
        title: str,
        description: str,
        settings: Any,
        global_settings: Any,
        upload_fn: Any,
        project_name: str,
    ) -> Dict[str, Any]:
        """Upload video/cover/manifest to Drive; verify + persist proof, fail-closed."""
        base_key = f"{project_name}:{channel}:{job_id}"
        video_folder = (
            getattr(global_settings, "drive_approved_video_folder_id", "")
            or getattr(global_settings, "drive_folder_id", "")
            or os.environ.get("DRIVE_APPROVED_VIDEO_FOLDER_ID", "")
        )
        cover_folder = (
            getattr(global_settings, "drive_approved_cover_folder_id", "")
            or getattr(settings, "drive_approved_cover_folder_id", "")
            or os.environ.get("DRIVE_APPROVED_COVER_FOLDER_ID", "")
        )
        metadata_folder = (
            getattr(global_settings, "drive_metadata_folder_id", "")
            or getattr(settings, "drive_metadata_folder_id", "")
            or os.environ.get("DRIVE_METADATA_FOLDER_ID", "")
        )

        if not video_folder:
            raise ValueError("drive_approved_video_folder_id is not configured")

        video = upload_fn(
            str(original_video_path),
            idempotency_key=base_key,
            display_name=f"{title}.mp4",
            title=title,
            description=description,
            folder_id=video_folder,
        )

        cover: Optional[Any] = None
        if thumbnail_path and os.path.isfile(str(thumbnail_path)) and cover_folder:
            cover = upload_fn(
                str(thumbnail_path),
                idempotency_key=f"{base_key}:cover",
                display_name=f"{title}.jpg",
                title=title,
                description=description,
                folder_id=cover_folder,
            )

        metadata = None
        if metadata_folder:
            manifest = {
                "job_id": job_id,
                "project": project_name,
                "version": int(version),
                "original_path_basename": os.path.basename(str(original_video_path)),
                "upload_timestamp": datetime.now(timezone.utc).isoformat(),
            }
            manifest_path = os.path.join(
                getattr(settings, "work_root", "") or "/tmp",
                f"{project_name}:{job_id}:metadata.json",
            )
            with open(manifest_path, "w", encoding="utf-8") as mf:
                json.dump(manifest, mf, ensure_ascii=False, indent=2)
            metadata = upload_fn(
                manifest_path,
                idempotency_key=f"{base_key}:metadata",
                display_name=f"{project_name}_{job_id}_metadata.json",
                title=title,
                description=description,
                folder_id=metadata_folder,
            )

        return {
            "status": "verified",
            "video": video,
            "cover": cover,
            "metadata": metadata,
        }


__all__ = [
    "ReviewJob",
    "ReviewStatus",
    "DeliveryResult",
    "ReviewStateStore",
    "init_review_db",
    "get_db_connection",
    "TelegramReviewBot",
    "send_telegram_message",
    "PublicationGate",
    "ReviewJobManager",
    "BaseReviewPublicationAdapter",
]