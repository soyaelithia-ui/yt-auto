"""Story data contract representing queue stories and pipeline ingestion artifacts."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

_FIELD_KEYS = frozenset([
    "story_id",
    "channel",
    "title",
    "raw_content",
    "status",
    "source_id",
    "score",
    "attempt_count",
    "retry_count",
    "last_error",
    "error_msg",
    "failure_code",
    "next_attempt_at",
    "run_id",
    "lane_id",
    "source_url",
    "source_license",
    "discovered_at",
    "created_at",
    "updated_at",
    "youtube_video_id",
    "publication_visibility",
    "publication_channel",
    "drive_file_id",
    "upvote_ratio",
    "num_comments",
    "metadata",
])
_PROPERTY_KEYS = frozenset(["id", "content"])
_ALL_KEYS = _FIELD_KEYS | _PROPERTY_KEYS


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


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
class StoryRecord(Mapping):
    """Strongly-typed data contract for story records throughout queue, ingestion, and pipeline."""

    story_id: str
    channel: str
    title: str
    raw_content: str = ""
    status: str = "pending"
    source_id: str = ""
    score: float = 0.0
    attempt_count: int = 0
    retry_count: int = 0
    last_error: str | None = None
    error_msg: str | None = None
    failure_code: str | None = None
    next_attempt_at: int | None = None
    run_id: str | None = None
    lane_id: str | None = None
    source_url: str | None = None
    source_license: str | None = None
    discovered_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    youtube_video_id: str | None = None
    publication_visibility: str | None = None
    publication_channel: str | None = None
    drive_file_id: str | None = None
    upvote_ratio: float = 0.0
    num_comments: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    _extra: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Alias for story_id for backwards compatibility."""
        return self.story_id

    @id.setter
    def id(self, value: str) -> None:
        self.story_id = str(value)

    @property
    def content(self) -> str:
        """Alias for raw_content."""
        return self.raw_content

    @content.setter
    def content(self, value: str) -> None:
        self.raw_content = str(value)

    def to_dict(self) -> dict[str, Any]:
        """Convert to fully serializable dictionary including extra attributes."""
        res: dict[str, Any] = {
            "story_id": self.story_id,
            "id": self.story_id,
            "channel": self.channel,
            "title": self.title,
            "raw_content": self.raw_content,
            "content": self.content,
            "status": self.status,
            "source_id": self.source_id,
            "score": self.score,
            "attempt_count": self.attempt_count,
            "retry_count": self.retry_count,
            "last_error": self.last_error,
            "error_msg": self.error_msg,
            "failure_code": self.failure_code,
            "next_attempt_at": self.next_attempt_at,
            "run_id": self.run_id,
            "lane_id": self.lane_id,
            "source_url": self.source_url,
            "source_license": self.source_license,
            "discovered_at": self.discovered_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "youtube_video_id": self.youtube_video_id,
            "publication_visibility": self.publication_visibility,
            "publication_channel": self.publication_channel,
            "drive_file_id": self.drive_file_id,
            "upvote_ratio": self.upvote_ratio,
            "num_comments": self.num_comments,
            "metadata": dict(self.metadata),
        }
        res.update(self._extra)
        return res

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like access method conforming to Python Mapping."""
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key: str) -> Any:
        """Dict-like subscript access."""
        if key == "id":
            return self.story_id
        if key == "content":
            return self.raw_content
        if key in _FIELD_KEYS:
            return getattr(self, key)
        if key in self._extra:
            return self._extra[key]
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Dict-like subscript assignment."""
        if key == "id":
            self.story_id = str(value)
        elif key == "content":
            self.raw_content = str(value)
        elif key in _FIELD_KEYS:
            setattr(self, key, value)
        else:
            self._extra[key] = value

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())

    def __contains__(self, key: Any) -> bool:
        """Dict-like membership test."""
        k = str(key)
        return k in _ALL_KEYS or k in self._extra

    def __getattr__(self, name: str) -> Any:
        extra = object.__getattribute__(self, "_extra")
        if name in extra:
            return extra[name]
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "id":
            object.__setattr__(self, "story_id", str(value))
        elif name == "content":
            object.__setattr__(self, "raw_content", str(value))
        elif name in _FIELD_KEYS or name == "_extra":
            object.__setattr__(self, name, value)
        else:
            try:
                object.__setattr__(self, name, value)
            except AttributeError:
                extra = object.__getattribute__(self, "_extra")
                extra[name] = value

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StoryRecord:
        """Construct a StoryRecord from arbitrary mapping or dictionary."""
        d = dict(data)
        sid_primary = d.pop("story_id", None)
        sid_alias = d.pop("id", None)
        sid = str(sid_primary if sid_primary is not None else (sid_alias if sid_alias is not None else ""))

        channel = str(d.pop("channel", "") or "")
        title = str(d.pop("title", "") or "")

        content_primary = d.pop("raw_content", None)
        content_alias = d.pop("content", None)
        content = str(content_primary if content_primary is not None else (content_alias if content_alias is not None else ""))

        status = str(d.pop("status", "pending") or "pending")
        source_id = str(d.pop("source_id", "") or "")
        score = _safe_float(d.pop("score", 0.0), 0.0)
        attempt_count = _safe_int(d.pop("attempt_count", 0), 0)
        retry_count = _safe_int(d.pop("retry_count", 0), 0)
        last_error = d.pop("last_error", None)
        error_msg = d.pop("error_msg", None)
        failure_code = d.pop("failure_code", None)
        next_attempt_at = _safe_optional_int(d.pop("next_attempt_at", None))
        run_id = d.pop("run_id", None)
        lane_id = d.pop("lane_id", None)
        source_url = d.pop("source_url", None)
        source_license = d.pop("source_license", None)
        discovered_at = d.pop("discovered_at", None)
        created_at = d.pop("created_at", None)
        updated_at = d.pop("updated_at", None)
        youtube_video_id = d.pop("youtube_video_id", None)
        publication_visibility = d.pop("publication_visibility", None)
        publication_channel = d.pop("publication_channel", None)
        drive_file_id = d.pop("drive_file_id", None)
        upvote_ratio = _safe_float(d.pop("upvote_ratio", 0.0), 0.0)
        num_comments = _safe_int(d.pop("num_comments", 0), 0)
        metadata = d.pop("metadata", None)
        if not isinstance(metadata, dict):
            metadata = {}

        return cls(
            story_id=sid,
            channel=channel,
            title=title,
            raw_content=content,
            status=status,
            source_id=source_id,
            score=score,
            attempt_count=attempt_count,
            retry_count=retry_count,
            last_error=str(last_error) if last_error is not None else None,
            error_msg=str(error_msg) if error_msg is not None else None,
            failure_code=str(failure_code) if failure_code is not None else None,
            next_attempt_at=next_attempt_at,
            run_id=str(run_id) if run_id is not None else None,
            lane_id=str(lane_id) if lane_id is not None else None,
            source_url=str(source_url) if source_url is not None else None,
            source_license=str(source_license) if source_license is not None else None,
            discovered_at=str(discovered_at) if discovered_at is not None else None,
            created_at=str(created_at) if created_at is not None else None,
            updated_at=str(updated_at) if updated_at is not None else None,
            youtube_video_id=str(youtube_video_id) if youtube_video_id is not None else None,
            publication_visibility=str(publication_visibility) if publication_visibility is not None else None,
            publication_channel=str(publication_channel) if publication_channel is not None else None,
            drive_file_id=str(drive_file_id) if drive_file_id is not None else None,
            upvote_ratio=upvote_ratio,
            num_comments=num_comments,
            metadata=metadata,
            _extra=d,
        )

    @classmethod
    def from_row(cls, row: Any) -> StoryRecord:
        """Construct from sqlite3.Row or similar row mapping."""
        if hasattr(row, "keys"):
            return cls.from_dict({k: row[k] for k in row.keys()})
        if isinstance(row, Mapping):
            return cls.from_dict(row)
        raise TypeError(f"Cannot construct StoryRecord from row of type {type(row)}")
