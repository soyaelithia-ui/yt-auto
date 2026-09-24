"""Direct Session & Cookies-Based YouTube Uploader (yt-auto v3.1).

Enables deterministic video publication via persistent authenticated browser sessions
(Playwright / InnerTube / Decrypted Netscape & JSON cookies), bypassing YouTube Data API v3
quota limitations (10,000 pts / ~6 uploads daily limit).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.core.cookies import SessionHealthResult, SessionHealthValidator, SessionStatus
from src.log import get_logger

logger = get_logger("session_uploader")


class SessionUploadError(RuntimeError):
    """Raised when session-based upload encounters a fatal or unrecoverable error."""

    def __init__(self, message: str, status: Optional[SessionStatus] = None, details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.status = status
        self.details = details or {}


class SessionUploader:
    """Zero-quota YouTube publisher using direct authenticated sessions."""

    def __init__(
        self,
        channel: str = "moku",
        secrets_dir: Optional[Union[str, Path]] = None,
        expiring_soon_hours: float = 48.0,
    ) -> None:
        self.channel = str(channel).lower().strip()
        self.secrets_dir = Path(secrets_dir) if secrets_dir else None
        self.expiring_soon_hours = float(expiring_soon_hours)
        self._cookie_path: Optional[Path] = None

    @property
    def cookies_path(self) -> Optional[Path]:
        """Convenience property resolving the cookie path."""
        return self.resolve_cookie_path()

    @property
    def cookie_path(self) -> Optional[Path]:
        """Convenience property resolving the cookie path."""
        return self.resolve_cookie_path()

    def resolve_cookie_path(self) -> Optional[Path]:
        """Resolve cookie file path for the active channel."""
        if not self._cookie_path or not self._cookie_path.exists():
            self._cookie_path = SessionHealthValidator.resolve_cookie_file_for_channel(
                self.channel, secrets_dir=self.secrets_dir
            )
        return self._cookie_path

    def check_health(self) -> SessionHealthResult:
        """Evaluate session health, validity, and expiration."""
        cookie_path = self.resolve_cookie_path()
        if not cookie_path:
            return SessionHealthResult(
                status=SessionStatus.INVALID,
                detail=f"No cookie file found for channel '{self.channel}'",
                total_cookies=0,
            )
        return SessionHealthValidator.validate_file(
            cookie_path, expiring_soon_hours=self.expiring_soon_hours
        )

    def preflight_check(self) -> None:
        """Fail-closed preflight verification before attempting media processing or upload."""
        health = self.check_health()
        if health.status in (SessionStatus.INVALID, SessionStatus.EXPIRED, SessionStatus.INCOMPLETE):
            raise SessionUploadError(
                f"Preflight session check failed for channel '{self.channel}': {health.detail}",
                status=health.status,
                details={"channel": self.channel, "status": health.status.value, "detail": health.detail},
            )
        if health.status == SessionStatus.EXPIRING_SOON:
            logger.warning(
                "Session cookies for channel '%s' are expiring soon: %s",
                self.channel,
                health.detail,
            )

    def upload(
        self,
        video_path: Union[str, Path],
        title: str,
        description: str,
        tags: Optional[List[str]] = None,
        thumbnail_path: Optional[Union[str, Path]] = None,
        dry_run: bool = False,
        visibility: str = "public",
        **kwargs,
    ) -> Dict[str, Any]:
        """Upload video using direct session authentication without API quota consumption."""
        v_path = Path(video_path)
        if not v_path.is_file() or v_path.stat().st_size == 0:
            raise FileNotFoundError(f"Video file missing or empty: {video_path}")

        # Check session health unless explicitly in dry_run test mode
        health = self.check_health()
        if not dry_run and health.status in (SessionStatus.INVALID, SessionStatus.EXPIRED, SessionStatus.INCOMPLETE):
            raise SessionUploadError(
                f"Cannot upload to '{self.channel}': Session is {health.status.value} ({health.detail})",
                status=health.status,
            )

        if dry_run or os.environ.get("DRY_RUN") == "1":
            logger.info("SessionUploader dry_run enabled. Simulating successful publication.")
            return {
                "status": "DRY_RUN",
                "method": "SESSION_PLAYWRIGHT",
                "channel": self.channel,
                "video_id": f"sim_{int(time.time())}",
                "title": title,
                "health": health.status.value,
            }

        cookie_file = self.resolve_cookie_path()
        if not cookie_file or not cookie_file.is_file():
            raise FileNotFoundError(f"Cookies file not found for channel '{self.channel}'")

        # 1. Primary Attempt: InnerTube Direct HTTP (0 RAM, 2-3s)
        try:
            from src.core.cookies import parse_cookies_file
            from src.youtube.innertube_uploader import upload_video_via_innertube

            parsed_cookies = parse_cookies_file(cookie_file)
            logger.info("Attempting primary session upload via InnerTube HTTP for '%s'...", self.channel)
            tube_result = upload_video_via_innertube(
                video_path=v_path,
                title=title,
                description=description,
                cookies=parsed_cookies,
                tags=tags,
                thumbnail_path=thumbnail_path,
                channel_id=kwargs.get("expected_channel_id") or kwargs.get("channel_id"),
                visibility=visibility,
                dry_run=dry_run,
            )
            return tube_result
        except Exception as innertube_err:
            logger.warning(
                "InnerTube upload failed for '%s' (%s); falling back to Playwright Stealth...",
                self.channel,
                innertube_err,
            )

        # 2. Fallback Attempt: Playwright Stealth Browser
        from src.youtube.uploader import upload_video_via_playwright

        return upload_video_via_playwright(
            video_path=str(v_path),
            title=title,
            description=description,
            tags=tags,
            thumbnail_path=str(thumbnail_path) if thumbnail_path else None,
            channel=self.channel,
            cookie_path=str(cookie_file),
            visibility=visibility,
            **kwargs,
        )


def upload_video_via_session(
    video_path: Union[str, Path],
    title: str,
    description: str,
    channel: str = "moku",
    thumbnail_path: Optional[Union[str, Path]] = None,
    dry_run: bool = False,
    **kwargs,
) -> Dict[str, Any]:
    """Convenience function for direct session-based video upload."""
    uploader = SessionUploader(channel=channel)
    return uploader.upload(
        video_path=video_path,
        title=title,
        description=description,
        thumbnail_path=thumbnail_path,
        dry_run=dry_run,
        **kwargs,
    )
