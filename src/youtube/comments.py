"""
src/youtube/comments.py - YouTube Video Pinned Comment Dispatcher & Lifecycle Manager.

Posts discussion-sparking top-level/pinned comments to published YouTube videos via
YouTube Data API v3 (commentThreads.insert). Intercepts and classifies API exceptions
(comments disabled, quota limits, permissions, network failures) without interrupting
the publishing pipeline, marking failed comments gracefully.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from src.config import BASE_DIR, is_test_environment
from src.log import get_logger

logger = get_logger("youtube.comments")


@dataclass(slots=True, frozen=True)
class PinnedCommentResult:
    video_id: str
    status: str  # "posted" | "failed" | "disabled"
    comment_id: Optional[str] = None
    error: Optional[str] = None
    text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_id": self.video_id,
            "status": self.status,
            "comment_id": self.comment_id,
            "error": self.error,
            "text": self.text,
        }


def _resolve_youtube_service(token_path: Optional[str] = None, channel: Optional[str] = None) -> Optional[Any]:
    """Resolves authenticated YouTube service from token path or channel fallback."""
    resolved_path: Optional[Path] = None
    if token_path and Path(token_path).is_file():
        resolved_path = Path(token_path)
    elif channel:
        cand = BASE_DIR / "secrets" / "tokens" / f"{channel}.json"
        if cand.is_file():
            resolved_path = cand

    if not resolved_path:
        return None

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        token_data = json.loads(resolved_path.read_text(encoding="utf-8"))
        creds = Credentials(
            token=token_data.get("access_token") or token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes"),
        )
        return build("youtube", "v3", credentials=creds, cache_discovery=False)
    except Exception as exc:
        logger.warning("Failed to build YouTube service for comments: %s", exc)
        return None


def post_pinned_comment(
    video_id: str,
    comment_text: str,
    token_path: Optional[str] = None,
    channel: Optional[str] = None,
    youtube_service: Optional[Any] = None,
) -> PinnedCommentResult:
    """
    Dispatches a top-level pinned comment under a published YouTube video.
    If comment posting fails for any reason (disabled comments, quota, network),
    catches the error and returns status='failed' or 'disabled' without raising.
    """
    clean_vid = (video_id or "").strip()
    clean_text = (comment_text or "").strip()

    if not clean_vid or not clean_text:
        return PinnedCommentResult(
            video_id=clean_vid,
            status="failed",
            error="Missing video_id or comment_text",
            text=clean_text,
        )

    is_mock = is_test_environment() or os.environ.get("TEST_MODE") == "1" or os.environ.get("MOCK_YOUTUBE_UPLOAD") == "1"
    if is_mock and not youtube_service:
        logger.info("Mock mode: simulated pinned comment for video %s", clean_vid)
        return PinnedCommentResult(
            video_id=clean_vid,
            status="posted",
            comment_id=f"mock_comment_{clean_vid}",
            text=clean_text,
        )

    service = youtube_service or _resolve_youtube_service(token_path, channel)
    if not service:
        logger.warning("No valid YouTube service or credentials found to post pinned comment for %s", clean_vid)
        return PinnedCommentResult(
            video_id=clean_vid,
            status="failed",
            error="YouTube credentials not found",
            text=clean_text,
        )

    body = {
        "snippet": {
            "videoId": clean_vid,
            "topLevelComment": {
                "snippet": {
                    "textOriginal": clean_text,
                }
            },
        }
    }

    try:
        response = service.commentThreads().insert(
            part="snippet",
            body=body,
        ).execute()

        comment_id = str(response.get("id") or "")
        logger.info("Successfully posted pinned comment %s for video %s", comment_id, clean_vid)
        return PinnedCommentResult(
            video_id=clean_vid,
            status="posted",
            comment_id=comment_id,
            text=clean_text,
        )
    except Exception as exc:
        exc_str = str(exc)
        status = "disabled" if "commentsDisabled" in exc_str else "failed"
        logger.warning("Could not post pinned comment on video %s (status=%s): %s", clean_vid, status, exc)
        return PinnedCommentResult(
            video_id=clean_vid,
            status=status,
            error=exc_str[:500],
            text=clean_text,
        )
