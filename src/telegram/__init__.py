"""Telegram notification, review gate, and interactive automation bot module."""

from __future__ import annotations

from review import DeliveryResult, TelegramReviewBot, send_telegram_message
from src.telegram.approval import (
    AUTO_PUBLISH_TIMEOUT_HOURS,
    check_pending_approvals,
    get_expired_pending_videos,
    process_approval_timeout,
    trigger_youtube_upload,
    update_video_status,
)
from src.telegram.callbacks import PollerHeartbeat, poll_callbacks
from src.telegram.interactive_bot import InteractiveTelegramBot
from src.telegram.notifier import TelegramNotifier, send_video_for_review

__all__ = [
    "AUTO_PUBLISH_TIMEOUT_HOURS",
    "DeliveryResult",
    "InteractiveTelegramBot",
    "PollerHeartbeat",
    "TelegramNotifier",
    "TelegramReviewBot",
    "check_pending_approvals",
    "get_expired_pending_videos",
    "poll_callbacks",
    "process_approval_timeout",
    "send_telegram_message",
    "send_video_for_review",
    "trigger_youtube_upload",
    "update_video_status",
]

