"""Telegram notification and approval module."""

from __future__ import annotations

from src.telegram.approval import (
    AUTO_PUBLISH_TIMEOUT_HOURS,
    check_pending_approvals,
    get_expired_pending_videos,
    process_approval_timeout,
    trigger_youtube_upload,
    update_video_status,
)

__all__ = [
    "AUTO_PUBLISH_TIMEOUT_HOURS",
    "check_pending_approvals",
    "get_expired_pending_videos",
    "process_approval_timeout",
    "trigger_youtube_upload",
    "update_video_status",
]
