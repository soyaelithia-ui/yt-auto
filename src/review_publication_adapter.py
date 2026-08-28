"""Backward compatibility facade for src.review_adapter."""

from src.review_adapter import (
    BaseReviewPublicationAdapter,
    YTShortPublicationAdapter,
    _backup_drive,
    _required_payload,
    _sync_queue_db,
    _verify_core_claim,
    mark_run_retention_satisfied,
    move_drive_file,
    publish,
    upload_to_drive_verified,
    upload_video,
)

__all__ = [
    "BaseReviewPublicationAdapter",
    "YTShortPublicationAdapter",
    "publish",
    "upload_video",
    "upload_to_drive_verified",
    "move_drive_file",
    "mark_run_retention_satisfied",
    "_required_payload",
    "_verify_core_claim",
    "_backup_drive",
    "_sync_queue_db",
]

