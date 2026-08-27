"""Compatibility wrappers and high-level notifier for the Telegram review core."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("telegram_notifier")

try:
    from dotenv import load_dotenv
    from pathlib import Path

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

from review import DeliveryResult, TelegramReviewBot
from review.telegram_bot import send_telegram_message as _send_message

telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
chat_id = (
    os.getenv("TELEGRAM_CHAT_ID")
    or os.getenv("TELEGRAM_ALLOWED_CHAT_ID")
    or os.getenv("TELEGRAM_HOME_CHANNEL")
    or ""
)

DEFAULT_BOT_TOKEN = telegram_token
DEFAULT_CHAT_ID = chat_id


class TelegramNotifier:
    """High-level notifier for sending status messages, render alerts, and video previews."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        bot: Optional[TelegramReviewBot] = None,
    ):
        self.bot_token = bot_token or DEFAULT_BOT_TOKEN
        self.chat_id = chat_id or DEFAULT_CHAT_ID
        self.bot = bot or TelegramReviewBot(
            bot_token=self.bot_token,
            allowed_chat_id=_chat_id(self.chat_id),
        )

    def send_message(
        self,
        text: str,
        parse_mode: Optional[str] = "Markdown",
    ) -> DeliveryResult:
        """Send a milestone/error notification with Markdown formatting and plain text fallback."""
        return send_telegram_message(
            text,
            chat_id=self.chat_id,
            bot_token=self.bot_token,
            parse_mode=parse_mode,
            bot=self.bot,
        )

    def send_status_update(
        self,
        status_text: str,
        job_id: Optional[str] = None,
        step: Optional[str] = None,
    ) -> DeliveryResult:
        """Send a concise pipeline status update."""
        header = "Estado"
        if job_id:
            header += f" · Job {job_id}"
        if step:
            header += f" · {step}"
        msg = f"{header}\n{status_text}"
        return self.send_message(msg, parse_mode="Markdown")

    def send_render_notification(
        self,
        job_id: str,
        stage: str,
        status: str,
        details: Optional[str] = None,
    ) -> DeliveryResult:
        """Send a concise rendering progress notification."""
        status_lower = status.lower()
        if status_lower in ("completed", "done", "success"):
            emoji = "✅"
        elif status_lower in ("started", "in_progress", "rendering"):
            emoji = "⏳"
        else:
            emoji = "❌"
        msg = f"{emoji} Render · Job {job_id} · {stage} · {status}"
        if details:
            msg += f"\n{details}"
        return self.send_message(msg, parse_mode="Markdown")

    def send_video_preview(
        self,
        video_path: str,
        metadata: Dict[str, Any],
        drive_url: Optional[str] = None,
    ) -> DeliveryResult:
        """Submit a video preview or resulting video file for human review (supports up to 2 GB)."""
        return send_video_for_review(
            video_path=video_path,
            metadata=metadata,
            chat_id=self.chat_id,
            bot_token=self.bot_token,
            drive_url=drive_url,
        )

    def send_document(
        self,
        document_path: str,
        caption: Optional[str] = None,
        parse_mode: Optional[str] = "Markdown",
    ) -> DeliveryResult:
        """Send an arbitrary document or package (up to 2 GB)."""
        return self.bot.send_document(
            document_path=document_path,
            caption=caption,
            chat_id=self.chat_id,
            parse_mode=parse_mode,
        )

    def send_photo(
        self,
        photo_path: str,
        caption: Optional[str] = None,
        parse_mode: Optional[str] = "Markdown",
    ) -> DeliveryResult:
        """Send a cover art photo."""
        return self.bot.send_photo(
            photo_path=photo_path,
            caption=caption,
            chat_id=self.chat_id,
            parse_mode=parse_mode,
        )

    def send_status_async(
        self,
        text: str,
        parse_mode: Optional[str] = "Markdown",
        callback: Optional[Any] = None,
    ):
        """Asynchronously send status message in background thread without blocking execution."""
        import concurrent.futures

        def worker():
            res = self.send_message(text, parse_mode=parse_mode)
            if callback and callable(callback):
                try:
                    callback(res)
                except Exception as exc:
                    logger.error(f"Async notification callback exception: {exc}")
            return res

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        future = executor.submit(worker)
        executor.shutdown(wait=False)
        return future


def _chat_id(value: Optional[str]) -> Optional[int]:
    candidate = value or DEFAULT_CHAT_ID
    try:
        return int(candidate) if candidate else None
    except (TypeError, ValueError):
        return None


def send_telegram_message(
    text: str,
    chat_id: Optional[str] = None,
    bot_token: Optional[str] = None,
    parse_mode: Optional[str] = "Markdown",
    bot: Optional[TelegramReviewBot] = None,
) -> DeliveryResult:
    """Send a milestone/error notification through the canonical transport."""
    target_chat_id = _chat_id(chat_id)
    target_token = bot_token or DEFAULT_BOT_TOKEN
    try:
        return _send_message(
            message=text,
            chat_id=target_chat_id,
            bot_token=target_token,
            parse_mode=parse_mode,
            bot=bot,
        )
    except Exception as exc:
        logger.error(f"Error in send_telegram_message: {exc}")
        return DeliveryResult(ok=False, error=str(exc))


def send_video_for_review(
    video_path: str,
    metadata: Dict[str, Any],
    chat_id: Optional[str] = None,
    bot_token: Optional[str] = None,
    drive_url: Optional[str] = None,
) -> DeliveryResult:
    """Submit a review request with preflight media integrity verification (supports up to 2 GB)."""
    meta = dict(metadata)
    if drive_url:
        meta["drive_url"] = drive_url

    # Strict Gating: Reject review submission if any scene is in BLOCKED_ASSET state
    if meta.get("has_blocked_assets"):
        logger.error("Delivery aborted: Video contains BLOCKED_ASSET scenes that failed visual audit limits.")
        return DeliveryResult(ok=False, error="Delivery aborted due to BLOCKED_ASSET scenes")

    effective_path = str(meta.get("preview_path") or video_path)

    if not os.path.exists(effective_path):
        return DeliveryResult(
            ok=False,
            error=f"FAILED_ARTIFACT_PROVENANCE: File does not exist: {effective_path}",
        )

    # PREFLIGHT MEDIA INTEGRITY AUDIT BEFORE TELEGRAM SUBMISSION
    from src.integrity import verify_media_integrity, compute_file_sha256
    integrity_res = verify_media_integrity(effective_path)
    if not integrity_res.get("passed"):
        err_msg = "; ".join(integrity_res.get("errors", ["Preflight media integrity failed"]))
        logger.error(f"Telegram submission ABORTED: Preflight integrity check failed for {effective_path}: {err_msg}")
        return DeliveryResult(ok=False, error=f"Telegram preflight media integrity failed: {err_msg}")

    # STRICT PROVENANCE LOCK: Compute delivery SHA-256 immediately before sending
    delivery_sha256 = compute_file_sha256(effective_path)

    if delivery_sha256 == "03b01c652d0a572b437d355d9adfd288621fdea9a7ac0d2c6c17533bad5aa1d8":
        return DeliveryResult(
            ok=False,
            error=f"FAILED_ARTIFACT_PROVENANCE: Blacklisted defective regression hash {delivery_sha256}",
        )

    verified_sha256 = meta.get("sha256_hash") or meta.get("verified_sha256") or integrity_res.get("sha256_hash")

    if not verified_sha256 or verified_sha256 != delivery_sha256:
        err_msg = f"FAILED_ARTIFACT_PROVENANCE: Verified hash ({verified_sha256}) != Delivery hash ({delivery_sha256})"
        logger.error(f"Telegram delivery ABORTED: {err_msg}")
        return DeliveryResult(ok=False, error=err_msg)

    meta["delivery_sha256"] = delivery_sha256
    meta["delivery_realpath"] = os.path.realpath(effective_path)
    meta["delivery_file_size"] = os.path.getsize(effective_path)

    bot = TelegramReviewBot(
        bot_token=bot_token or DEFAULT_BOT_TOKEN,
        allowed_chat_id=_chat_id(chat_id),
    )
    result = bot.send_video_for_review(effective_path, meta)

    if not result.ok:
        logger.error(f"Telegram sendVideo failed/rejected: {result.error}")
    return result


from src.telegram.approval import (
    AUTO_PUBLISH_TIMEOUT_HOURS,
    check_pending_approvals,
    get_expired_pending_videos,
    process_approval_timeout,
    trigger_youtube_upload,
    update_video_status,
)

__all__ = [
    "TelegramNotifier",
    "send_telegram_message",
    "send_video_for_review",
    "AUTO_PUBLISH_TIMEOUT_HOURS",
    "check_pending_approvals",
    "get_expired_pending_videos",
    "process_approval_timeout",
    "trigger_youtube_upload",
    "update_video_status",
]


if __name__ == "__main__":
    print(send_telegram_message("YouTube automation notification test"))
