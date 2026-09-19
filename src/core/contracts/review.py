"""Review contract representing human-in-the-loop and automated code review payloads."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

_FIELD_KEYS = frozenset([
    "job_id",
    "channel",
    "title",
    "original_video_path",
    "description",
    "content_type",
    "project",
    "version",
    "status",
    "telegram_chat_id",
    "telegram_message_id",
    "published_id",
    "published_url",
    "publication_consumed",
    "thumbnail_path",
    "script",
    "subtitle_path",
    "work_dir",
    "drive_url",
    "created_at",
    "reviewed_at",
    "delivery_error",
    "metadata",
])
_PROPERTY_KEYS = frozenset(["id", "video_path"])
_ALL_KEYS = _FIELD_KEYS | _PROPERTY_KEYS


def _safe_int(val: Any, default: int = 0) -> int:
    if val is None or val == "":
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _safe_optional_int(val: Any) -> int | None:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


@dataclass(slots=True)
class ReviewContract(Mapping):
    """Strongly-typed contract for review jobs and submission payloads."""

    job_id: str
    channel: str
    title: str
    original_video_path: str = ""
    description: str = ""
    content_type: str = "short"
    project: str = "YTShort"
    version: int = 1
    status: str = "PENDING_REVIEW"
    telegram_chat_id: int | None = None
    telegram_message_id: int | None = None
    published_id: str | None = None
    published_url: str | None = None
    publication_consumed: int = 0
    thumbnail_path: str | None = None
    script: str | None = None
    subtitle_path: str | None = None
    work_dir: str | None = None
    drive_url: str | None = None
    created_at: str | None = None
    reviewed_at: str | None = None
    delivery_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    _extra: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Alias for job_id."""
        return self.job_id

    @id.setter
    def id(self, val: str) -> None:
        self.job_id = str(val)

    @property
    def video_path(self) -> str:
        """Alias for original_video_path."""
        return self.original_video_path

    @video_path.setter
    def video_path(self, val: str) -> None:
        self.original_video_path = str(val)

    @property
    def is_approved(self) -> bool:
        return self.status == "APPROVED"

    @property
    def is_pending(self) -> bool:
        return self.status in ("PENDING_REVIEW", "pending_approval", "WAITING_HUMAN_VERIFICATION")

    @property
    def is_published(self) -> bool:
        return self.status == "PUBLISHED"

    @property
    def is_rejected(self) -> bool:
        return self.status == "REJECTED"

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "job_id": self.job_id,
            "id": self.job_id,
            "channel": self.channel,
            "title": self.title,
            "original_video_path": self.original_video_path,
            "video_path": self.original_video_path,
            "description": self.description,
            "content_type": self.content_type,
            "project": self.project,
            "version": self.version,
            "status": self.status,
            "telegram_chat_id": self.telegram_chat_id,
            "telegram_message_id": self.telegram_message_id,
            "published_id": self.published_id,
            "published_url": self.published_url,
            "publication_consumed": self.publication_consumed,
            "thumbnail_path": self.thumbnail_path,
            "script": self.script,
            "subtitle_path": self.subtitle_path,
            "work_dir": self.work_dir,
            "drive_url": self.drive_url,
            "created_at": self.created_at,
            "reviewed_at": self.reviewed_at,
            "delivery_error": self.delivery_error,
            "metadata": dict(self.metadata),
        }
        res.update(self._extra)
        return res

    def to_job_kwargs(self) -> dict[str, Any]:
        """Convert to kwargs suitable for ReviewJob initialization."""
        return {
            "job_id": self.job_id,
            "channel": self.channel,
            "title": self.title,
            "original_video_path": self.original_video_path,
            "description": self.description,
            "content_type": self.content_type,
            "project": self.project,
            "version": self.version,
            "status": self.status,
            "telegram_chat_id": self.telegram_chat_id,
            "telegram_message_id": self.telegram_message_id,
            "published_id": self.published_id,
            "published_url": self.published_url,
            "publication_consumed": self.publication_consumed,
            "created_at": self.created_at,
            "reviewed_at": self.reviewed_at,
            "delivery_error": self.delivery_error,
            "metadata": dict(self.metadata),
        }

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key: str) -> Any:
        if key == "id":
            return self.job_id
        if key == "video_path":
            return self.original_video_path
        if key in _FIELD_KEYS:
            return getattr(self, key)
        if key in self._extra:
            return self._extra[key]
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key == "id":
            self.job_id = str(value)
        elif key == "video_path":
            self.original_video_path = str(value)
        elif key in _FIELD_KEYS:
            setattr(self, key, value)
        else:
            self._extra[key] = value

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())

    def __contains__(self, key: Any) -> bool:
        k = str(key)
        return k in _ALL_KEYS or k in self._extra

    def __getattr__(self, name: str) -> Any:
        extra = object.__getattribute__(self, "_extra")
        if name in extra:
            return extra[name]
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "id":
            object.__setattr__(self, "job_id", str(value))
        elif name == "video_path":
            object.__setattr__(self, "original_video_path", str(value))
        elif name in _FIELD_KEYS or name == "_extra":
            object.__setattr__(self, name, value)
        else:
            try:
                object.__setattr__(self, name, value)
            except AttributeError:
                extra = object.__getattribute__(self, "_extra")
                extra[name] = value

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReviewContract:
        d = dict(data)
        jid_primary = d.pop("job_id", None)
        jid_alias = d.pop("id", None)
        job_id = str(jid_primary if jid_primary is not None else (jid_alias if jid_alias is not None else ""))

        channel = str(d.pop("channel", "") or "")
        title = str(d.pop("title", "") or "")

        orig_vid_primary = d.pop("original_video_path", None)
        orig_vid_alias = d.pop("video_path", None)
        original_video_path = str(
            orig_vid_primary if orig_vid_primary is not None else (orig_vid_alias if orig_vid_alias is not None else "")
        )

        description = str(d.pop("description", "") or "")
        content_type = str(d.pop("content_type", "short") or "short")
        project = str(d.pop("project", "YTShort") or "YTShort")
        version = _safe_int(d.pop("version", 1), 1)
        status = str(d.pop("status", "PENDING_REVIEW") or "PENDING_REVIEW")
        telegram_chat_id = _safe_optional_int(d.pop("telegram_chat_id", None))
        telegram_message_id = _safe_optional_int(d.pop("telegram_message_id", None))
        published_id = d.pop("published_id", None)
        published_url = d.pop("published_url", None)
        publication_consumed = _safe_int(d.pop("publication_consumed", 0), 0)
        thumbnail_path = d.pop("thumbnail_path", None)
        script = d.pop("script", None)
        subtitle_path = d.pop("subtitle_path", None)
        work_dir = d.pop("work_dir", None)
        drive_url = d.pop("drive_url", None)
        created_at = d.pop("created_at", None)
        reviewed_at = d.pop("reviewed_at", None)
        delivery_error = d.pop("delivery_error", None)
        metadata = d.pop("metadata", None)
        if not isinstance(metadata, dict):
            metadata = {}

        return cls(
            job_id=job_id,
            channel=channel,
            title=title,
            original_video_path=original_video_path,
            description=description,
            content_type=content_type,
            project=project,
            version=version,
            status=status,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            published_id=str(published_id) if published_id is not None else None,
            published_url=str(published_url) if published_url is not None else None,
            publication_consumed=publication_consumed,
            thumbnail_path=str(thumbnail_path) if thumbnail_path is not None else None,
            script=str(script) if script is not None else None,
            subtitle_path=str(subtitle_path) if subtitle_path is not None else None,
            work_dir=str(work_dir) if work_dir is not None else None,
            drive_url=str(drive_url) if drive_url is not None else None,
            created_at=str(created_at) if created_at is not None else None,
            reviewed_at=str(reviewed_at) if reviewed_at is not None else None,
            delivery_error=str(delivery_error) if delivery_error is not None else None,
            metadata=metadata,
            _extra=d,
        )

    @classmethod
    def from_job(cls, job: Any) -> ReviewContract:
        """Construct from ReviewJob instance."""
        if hasattr(job, "__dict__"):
            return cls.from_dict(job.__dict__)
        if isinstance(job, Mapping):
            return cls.from_dict(job)
        raise TypeError(f"Cannot construct ReviewContract from {type(job)}")

    def validate(self) -> None:
        """Validate core review invariant constraints."""
        if not self.job_id.strip():
            raise ValueError("job_id cannot be empty")
        if not self.channel.strip():
            raise ValueError("channel cannot be empty")
        if not self.title.strip():
            raise ValueError("title cannot be empty")
