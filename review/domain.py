"""Domain models for Telegram video review core and atomic publication flow."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class ReviewStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    WAITING_HUMAN_VERIFICATION = "WAITING_HUMAN_VERIFICATION"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


VALID_STATUSES = frozenset(status.value for status in ReviewStatus)

# Allowed one-step transitions. Every transition is validated before write
# so an invalid status name can never corrupt persisted review state.
ALLOWED_TRANSITIONS: Dict[str, frozenset[str]] = {
    ReviewStatus.PENDING_REVIEW.value: frozenset(
        {
            ReviewStatus.APPROVED.value,
            ReviewStatus.REJECTED.value,
            ReviewStatus.EXPIRED.value,
            ReviewStatus.WAITING_HUMAN_VERIFICATION.value,
            ReviewStatus.PUBLISHING.value,
        }
    ),
    ReviewStatus.WAITING_HUMAN_VERIFICATION.value: frozenset(
        {
            ReviewStatus.APPROVED.value,
            ReviewStatus.REJECTED.value,
            ReviewStatus.EXPIRED.value,
        }
    ),
    ReviewStatus.APPROVED.value: frozenset(
        {
            ReviewStatus.PUBLISHING.value,
            ReviewStatus.PUBLISHED.value,
            ReviewStatus.EXPIRED.value,
            ReviewStatus.REJECTED.value,
        }
    ),
    ReviewStatus.PUBLISHING.value: frozenset(
        {
            ReviewStatus.PUBLISHED.value,
            ReviewStatus.APPROVED.value,
            ReviewStatus.REJECTED.value,
            ReviewStatus.FAILED.value,
        }
    ),
    ReviewStatus.PUBLISHED.value: frozenset(),
    ReviewStatus.REJECTED.value: frozenset({ReviewStatus.APPROVED.value}),
    ReviewStatus.EXPIRED.value: frozenset(),
    ReviewStatus.FAILED.value: frozenset(),
}


@dataclass
class DeliveryResult:
    ok: bool
    error: Optional[str] = None
    message_id: Optional[int] = None
    job_id: Optional[str] = None
    detail: Optional[str] = None


@dataclass
class ReviewJob:
    job_id: str
    channel: str
    title: str
    original_video_path: str = ""
    description: str = ""
    content_type: str = "short"
    project: str = "YTShort"
    version: int = 1
    status: str = ReviewStatus.PENDING_REVIEW.value
    telegram_chat_id: Optional[int] = None
    telegram_message_id: Optional[int] = None
    published_id: Optional[str] = None
    published_url: Optional[str] = None
    publication_consumed: int = 0
    created_at: Optional[str] = None
    reviewed_at: Optional[str] = None
    delivery_error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def video_path(self) -> str:
        """Backward-compatible alias used by older callers."""
        return self.original_video_path

    @classmethod
    def from_row(cls, row: Any) -> "ReviewJob":
        raw_metadata = row["metadata"] if "metadata" in row.keys() else "{}"
        metadata: Dict[str, Any] = {}
        if raw_metadata:
            try:
                import json as _json
                loaded = _json.loads(str(raw_metadata))
                if isinstance(loaded, dict):
                    metadata = loaded
            except (TypeError, ValueError):
                metadata = {}
        return cls(
            job_id=row["job_id"],
            channel=row["channel"],
            title=row["title"],
            original_video_path=row["original_video_path"],
            description=row["description"],
            content_type=row["content_type"],
            project=row["project"],
            version=row["version"],
            status=str(row["status"]),
            telegram_chat_id=row["telegram_chat_id"],
            telegram_message_id=row["telegram_message_id"],
            published_id=row["published_id"],
            published_url=row["published_url"],
            publication_consumed=row["publication_consumed"],
            created_at=row["created_at"],
            reviewed_at=row["reviewed_at"],
            delivery_error=row["delivery_error"],
            metadata=metadata,
        )

    def to_dict(self) -> Dict[str, Any]:
        import dataclasses
        return dataclasses.asdict(self)

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def public_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "channel": self.channel,
            "title": self.title,
            "original_path_basename": _basename(self.original_video_path),
            "project": self.project,
            "version": self.version,
            "content_type": self.content_type,
        }


def _basename(path_value: str) -> str:
    from pathlib import Path

    return Path(str(path_value or "")).name


def validate_status_name(status: str | ReviewStatus) -> str:
    normalized = status.value if isinstance(status, ReviewStatus) else str(status)
    if normalized not in VALID_STATUSES:
        raise ValueError(f"Invalid review status: {normalized!r}")
    return normalized