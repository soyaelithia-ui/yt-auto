"""YouTube Data API v3 control plane: delete, privacy, and stats.

Owner directive: uploads go through Playwright (cookies). The API is reserved
for feedback/control operations only — delete videos, change visibility, and
read statistics. Every mutation verifies video ownership against the expected
channel BEFORE acting, so a typo cannot touch another channel's content.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from src.core.domain import canonical_channel

logger = logging.getLogger("youtube_control")

VALID_PRIVACY_STATUS = {"public", "private", "unlisted"}

__all__ = [
    "delete_video",
    "set_video_privacy",
    "get_video_stats",
    "expected_channel_id",
    "resolve_token_path",
    "_verify_ownership",
    "_service_for_channel",
]


def resolve_token_path(channel: str) -> str:
    """Return the OAuth token path configured for the canonical channel."""
    from src.core.google_auth import resolve_channel_token_path
    return resolve_channel_token_path(channel)


def expected_channel_id(channel: str) -> str | None:
    """Configured YouTube channel id for the canonical channel, when known."""
    from src.config import SETTINGS

    key = canonical_channel(channel)
    value = SETTINGS.channels[key].expected_youtube_channel_id
    return str(value).strip() or None if value else None


def _service_for_channel(channel: str):
    from src.youtube.uploader import _youtube_service

    return _youtube_service(resolve_token_path(channel))


def _verify_ownership(youtube: Any, video_id: str, channel: str) -> Dict[str, Any]:
    """Fetch the video and confirm it belongs to the expected channel."""
    response = (
        youtube.videos()
        .list(part="snippet,status,statistics,contentDetails", id=video_id)
        .execute()
    )
    items = response.get("items") or []
    if not items:
        raise LookupError(f"Video no encontrado en YouTube: {video_id}")
    item = items[0]
    actual_channel = (item.get("snippet") or {}).get("channelId") or ""
    wanted = expected_channel_id(channel)
    if wanted and actual_channel != wanted:
        raise PermissionError(
            f"El video {video_id} pertenece al canal {actual_channel}, "
            f"no al canal configurado '{channel}' ({wanted})"
        )
    return item


def delete_video(video_id: str, channel: str = "moku") -> Dict[str, Any]:
    """Delete a video from YouTube after verifying channel ownership."""
    video_id = (video_id or "").strip()
    if not video_id:
        return {"ok": False, "error": "video_id requerido"}
    try:
        canonical_channel(channel)
    except Exception as exc:
        return {"ok": False, "video_id": video_id, "error": f"Canal inválido: {exc}"}

    try:
        youtube = _service_for_channel(channel)
        _verify_ownership(youtube, video_id, channel)
        youtube.videos().delete(id=video_id).execute()
        logger.warning("Video DELETED via API: %s (channel=%s)", video_id, channel)
        return {"ok": True, "action": "deleted", "video_id": video_id, "channel": channel}
    except (LookupError, PermissionError) as exc:
        logger.error("Delete rejected for %s: %s", video_id, exc)
        return {"ok": False, "video_id": video_id, "error": str(exc)}
    except Exception as exc:  # googleapiclient errors, network, auth refresh
        logger.exception("YouTube delete failed for %s", video_id)
        return {"ok": False, "video_id": video_id, "error": str(exc)[:400]}


def set_video_privacy(
    video_id: str, privacy_status: str, channel: str = "moku"
) -> Dict[str, Any]:
    """Set visibility ('public' | 'private' | 'unlisted') after ownership check."""
    video_id = (video_id or "").strip()
    privacy_status = (privacy_status or "").strip().lower()
    if not video_id:
        return {"ok": False, "error": "video_id requerido"}
    if privacy_status not in VALID_PRIVACY_STATUS:
        return {
            "ok": False,
            "video_id": video_id,
            "error": f"privacy inválido; use uno de {sorted(VALID_PRIVACY_STATUS)}",
        }
    try:
        canonical_channel(channel)
    except Exception as exc:
        return {"ok": False, "video_id": video_id, "error": f"Canal inválido: {exc}"}

    try:
        youtube = _service_for_channel(channel)
        item = _verify_ownership(youtube, video_id, channel)
        current = ((item.get("status") or {}).get("privacyStatus")) or ""
        if current == privacy_status:
            return {
                "ok": True,
                "action": "noop",
                "video_id": video_id,
                "privacyStatus": current,
            }
        youtube.videos().update(
            part="status",
            body={"id": video_id, "status": {"privacyStatus": privacy_status}},
        ).execute()
        logger.info(
            "Privacy changed via API: %s '%s'->'%s' (channel=%s)",
            video_id,
            current,
            privacy_status,
            channel,
        )
        return {
            "ok": True,
            "action": "privacy",
            "video_id": video_id,
            "previous": current,
            "privacyStatus": privacy_status,
        }
    except (LookupError, PermissionError) as exc:
        logger.error("Privacy change rejected for %s: %s", video_id, exc)
        return {"ok": False, "video_id": video_id, "error": str(exc)}
    except Exception as exc:
        logger.exception("YouTube privacy update failed for %s", video_id)
        return {"ok": False, "video_id": video_id, "error": str(exc)[:400]}


def get_video_stats(video_id: str, channel: str = "moku") -> Dict[str, Any]:
    """Read-only snapshot of views/likes/comments and status for one video."""
    video_id = (video_id or "").strip()
    if not video_id:
        return {"ok": False, "error": "video_id requerido"}
    try:
        youtube = _service_for_channel(channel)
        item = _verify_ownership(youtube, video_id, channel)
        stats = item.get("statistics") or {}
        status = item.get("status") or {}
        snippet = item.get("snippet") or {}
        return {
            "ok": True,
            "video_id": video_id,
            "title": snippet.get("title"),
            "views": int(stats.get("viewCount") or 0),
            "likes": int(stats.get("likeCount") or 0),
            "comments": int(stats.get("commentCount") or 0),
            "privacyStatus": status.get("privacyStatus"),
            "uploadStatus": status.get("uploadStatus"),
        }
    except (LookupError, PermissionError) as exc:
        return {"ok": False, "video_id": video_id, "error": str(exc)}
    except Exception as exc:
        logger.exception("YouTube stats failed for %s", video_id)
        return {"ok": False, "video_id": video_id, "error": str(exc)[:400]}
