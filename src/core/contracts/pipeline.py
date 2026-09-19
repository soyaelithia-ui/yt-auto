"""Strongly-typed execution context for pipeline execution."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.core.contracts.render import RenderSpec
from src.core.contracts.review import ReviewContract
from src.core.contracts.story import StoryRecord
from src.core.domain import JobStatus, LeaseOwnershipError
from src.core.profiling import PipelineProfiler
from src.core.repository import QueueRepository
from src.log import get_logger

logger = get_logger("core.contracts.pipeline")


def _write_run_marker(path: Path, run_id: str, *, active: bool, retention_satisfied: bool = False) -> None:
    """Record run marker on disk."""
    path.mkdir(parents=True, exist_ok=True)
    (path / ".run.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "active": active,
                "retention_satisfied": retention_satisfied,
                "updated_at": int(time.time()),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


_CLAIMED_LEASE_FIELDS = frozenset([
    "story",
    "story_id",
    "run_id",
    "lane",
    "repository",
    "database",
    "owner",
    "lease_seconds",
    "settings",
    "branding",
])


@dataclass(slots=True)
class ClaimedLeaseContext(Mapping):
    """Strongly-typed contract for Stage 1 claim / lease output."""

    story: StoryRecord | dict[str, Any]
    story_id: str
    run_id: str
    lane: Any
    repository: QueueRepository
    database: str
    owner: str
    lease_seconds: int
    settings: Any
    branding: Any
    _extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        story_val = self.story.to_dict() if isinstance(self.story, StoryRecord) else self.story
        res: dict[str, Any] = {
            "story": story_val,
            "story_id": self.story_id,
            "run_id": self.run_id,
            "lane": self.lane,
            "repository": self.repository,
            "database": self.database,
            "owner": self.owner,
            "lease_seconds": self.lease_seconds,
            "settings": self.settings,
            "branding": self.branding,
        }
        res.update(self._extra)
        return res

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key: str) -> Any:
        if key in _CLAIMED_LEASE_FIELDS:
            return getattr(self, key)
        if key in self._extra:
            return self._extra[key]
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key in _CLAIMED_LEASE_FIELDS:
            setattr(self, key, value)
        else:
            self._extra[key] = value

    def __iter__(self) -> Iterator[str]:
        yield from _CLAIMED_LEASE_FIELDS
        yield from self._extra.keys()

    def __len__(self) -> int:
        return len(_CLAIMED_LEASE_FIELDS) + len(self._extra)

    def __contains__(self, key: Any) -> bool:
        k = str(key)
        return k in _CLAIMED_LEASE_FIELDS or k in self._extra

    def __getattr__(self, name: str) -> Any:
        extra = object.__getattribute__(self, "_extra")
        if name in extra:
            return extra[name]
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _CLAIMED_LEASE_FIELDS or name == "_extra":
            object.__setattr__(self, name, value)
        else:
            try:
                object.__setattr__(self, name, value)
            except AttributeError:
                extra = object.__getattribute__(self, "_extra")
                extra[name] = value


_PIPELINE_CTX_FIELDS = frozenset([
    "story",
    "story_id",
    "run_id",
    "channel_name",
    "channel_key",
    "lane",
    "repository",
    "database",
    "owner",
    "lease_seconds",
    "settings",
    "branding",
    "profiler",
    "directed",
    "generate_only",
    "engine_mode",
    "is_loop_mode",
    "is_multiscene_mode",
    "subtitles_active",
    "work_dir",
    "audio_path",
    "ass_path",
    "srt_path",
    "video_path",
    "thumbnail_path",
    "script_path",
    "visual_plan_path",
    "metadata_path",
    "scene_manifest_path",
    "loop_category",
    "script",
    "title",
    "content",
    "clean_script",
    "used_ids",
    "is_long_lane",
    "words_min",
    "words_max",
    "audio",
    "beats",
    "target_category",
    "resolved_loop_path",
    "music_track_path",
    "bg_volume",
    "scene_bg_list",
    "shot_durations",
    "manifest_payload",
    "manifest_path",
    "mux_subtitles",
    "stream_copy_mode",
    "loop_engine",
    "planner_agent",
    "multi_compositor",
    "script_payload",
    "visual_plan_payload",
    "compositor_metrics",
    "visual_integrity_report",
    "spanish_title",
    "youtube_title",
    "youtube_description",
    "text_fingerprints",
    "file_fingerprints",
    "render_spec",
    "review_contract",
])


@dataclass(slots=True)
class PipelineContext(Mapping):
    """Encapsulated production context passed through pipeline stages."""

    story: StoryRecord | dict[str, Any]
    story_id: str
    run_id: str
    channel_name: str
    channel_key: Any
    lane: Any
    repository: QueueRepository
    database: str
    owner: str
    lease_seconds: int
    settings: Any
    branding: Any
    profiler: PipelineProfiler
    directed: bool
    generate_only: bool
    engine_mode: str
    is_loop_mode: bool
    is_multiscene_mode: bool
    subtitles_active: bool
    work_dir: Path
    audio_path: Path
    ass_path: Path
    srt_path: Path
    video_path: Path
    thumbnail_path: Path
    script_path: Path
    visual_plan_path: Path
    metadata_path: Path
    scene_manifest_path: Path
    loop_category: str | None = None

    script: str = ""
    title: str = ""
    content: str = ""
    clean_script: str = ""
    used_ids: list[str] = field(default_factory=list)
    is_long_lane: bool = False
    words_min: int = 0
    words_max: int | None = None
    audio: dict[str, Any] = field(default_factory=dict)
    beats: list[dict[str, Any]] = field(default_factory=list)
    target_category: str = ""
    resolved_loop_path: str = ""
    music_track_path: str = ""
    bg_volume: float = 0.04
    scene_bg_list: list[str] = field(default_factory=list)
    shot_durations: list[float] = field(default_factory=list)
    manifest_payload: dict[str, Any] = field(default_factory=dict)
    manifest_path: Path | None = None
    mux_subtitles: bool = False
    stream_copy_mode: bool = True
    loop_engine: Any = None
    planner_agent: Any = None
    multi_compositor: Any = None
    script_payload: dict[str, Any] | None = None
    visual_plan_payload: dict[str, Any] | None = None
    compositor_metrics: dict[str, Any] = field(default_factory=dict)
    visual_integrity_report: dict[str, Any] = field(default_factory=dict)
    spanish_title: str = ""
    youtube_title: str = ""
    youtube_description: str = ""
    text_fingerprints: dict[str, str] = field(default_factory=dict)
    file_fingerprints: dict[str, str] = field(default_factory=dict)
    _heartbeat_ticker_active: bool = False
    render_spec: RenderSpec | None = None
    review_contract: ReviewContract | None = None
    _extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.lane is not None:
            dur = getattr(self.lane, "duration_min_sec", None)
            dur_is_long = (isinstance(dur, (int, float)) and dur >= 300) or (
                isinstance(dur, str) and dur.isdigit() and int(dur) >= 300
            )
            lane_id = getattr(self.lane, "id", None)
            lane_id_is_long = isinstance(lane_id, str) and "long" in lane_id.lower()
            if (
                getattr(self.lane, "orientation", "") == "horizontal"
                or getattr(self.lane, "qa_profile", "") == "longform"
                or dur_is_long
                or lane_id_is_long
            ):
                self.is_long_lane = True

    def heartbeat(self) -> bool:
        """Touch active lease heartbeat in database without raising if lease was lost."""
        try:
            return bool(self.repository.heartbeat(self.run_id, self.owner, lease_seconds=self.lease_seconds))
        except Exception as exc:
            logger.debug("Active heartbeat touch failed for run %s: %s", self.run_id, exc)
            return False

    def require_heartbeat(self) -> None:
        """Verify worker lease ownership is still valid."""
        if not self.repository.heartbeat(self.run_id, self.owner, lease_seconds=self.lease_seconds):
            raise LeaseOwnershipError("El lease dirigido ya no pertenece a este worker")

    def set_owned_status(
        self,
        status: str | JobStatus,
        *,
        error_code: str | None = None,
        error_detail: str | None = None,
        retry_at: int | None = None,
    ) -> bool:
        """Atomically transition story status only if lease ownership holds."""
        return self.repository.set_status(
            self.story_id,
            status,
            error_code=error_code,
            error_detail=error_detail,
            retry_at=retry_at,
            run_id=self.run_id,
            owner=self.owner,
        )

    def lease_lost_result(self) -> dict[str, Any]:
        """Construct failure payload when lease ownership is lost."""
        try:
            _write_run_marker(self.work_dir, self.run_id, active=False)
        except OSError as exc:
            logger.debug("Marker write failed during lease loss: %s", exc)
        try:
            self.profiler.record_error("El worker perdió ownership del run; no se mutó el estado", "LeaseLost")
            self.profiler.emit_telemetry(db_path=self.database)
        except Exception:
            pass
        return {
            "status": "LEASE_LOST",
            "story_id": self.story_id,
            "run_id": self.run_id,
            "channel": self.channel_name,
            "reason": "El worker perdió ownership del run; no se mutó el estado",
            "profiling": self.profiler.to_dict(),
        }

    def fail(
        self,
        code: str,
        detail: str,
        *,
        status: str | JobStatus = "FAILED",
        retry_delay: int | None = None,
    ) -> dict[str, Any]:
        """Record failure telemetry, update repository, and return structured outcome."""
        _write_run_marker(self.work_dir, self.run_id, active=False)
        try:
            self.profiler.record_error(detail, code)
            self.profiler.emit_telemetry(db_path=self.database)
        except Exception:
            pass
        retry_at = int(time.time()) + retry_delay if retry_delay is not None else None
        if self.set_owned_status(status, error_code=code, error_detail=detail, retry_at=retry_at):
            self.repository.finish_run(self.run_id, status, owner=self.owner)
            return {
                "status": str(status.value if isinstance(status, JobStatus) else status),
                "story_id": self.story_id,
                "run_id": self.run_id,
                "reason": detail,
                "profiling": self.profiler.to_dict(),
            }
        return self.lease_lost_result()

    def to_dict(self) -> dict[str, Any]:
        """Serialize context summary to dictionary."""
        story_dict = self.story.to_dict() if isinstance(self.story, StoryRecord) else self.story
        res: dict[str, Any] = {
            "story_id": self.story_id,
            "run_id": self.run_id,
            "channel_name": self.channel_name,
            "story": story_dict,
            "engine_mode": self.engine_mode,
            "is_loop_mode": self.is_loop_mode,
            "is_multiscene_mode": self.is_multiscene_mode,
            "work_dir": str(self.work_dir),
            "video_path": str(self.video_path),
            "spanish_title": self.spanish_title,
            "youtube_title": self.youtube_title,
            "is_long_lane": self.is_long_lane,
            "script": self.script,
            "title": self.title,
            "content": self.content,
            "words_min": self.words_min,
            "words_max": self.words_max,
            "audio": dict(self.audio),
            "target_category": self.target_category,
            "render_spec": self.render_spec.to_dict() if self.render_spec else None,
            "review_contract": self.review_contract.to_dict() if self.review_contract else None,
        }
        res.update(self._extra)
        return res

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key: str) -> Any:
        if key in _PIPELINE_CTX_FIELDS:
            return getattr(self, key)
        if key in self._extra:
            return self._extra[key]
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key in _PIPELINE_CTX_FIELDS:
            setattr(self, key, value)
        else:
            self._extra[key] = value

    def __iter__(self) -> Iterator[str]:
        yield from _PIPELINE_CTX_FIELDS
        yield from self._extra.keys()

    def __len__(self) -> int:
        return len(_PIPELINE_CTX_FIELDS) + len(self._extra)

    def __contains__(self, key: Any) -> bool:
        k = str(key)
        return k in _PIPELINE_CTX_FIELDS or k in self._extra

    def __getattr__(self, name: str) -> Any:
        extra = object.__getattribute__(self, "_extra")
        if name in extra:
            return extra[name]
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _PIPELINE_CTX_FIELDS or name in ("_heartbeat_ticker_active", "_extra"):
            object.__setattr__(self, name, value)
        else:
            try:
                object.__setattr__(self, name, value)
            except AttributeError:
                extra = object.__getattribute__(self, "_extra")
                extra[name] = value


# 100% backward-compatible alias for existing codebase and tests
RunContext = PipelineContext


@contextmanager
def active_heartbeat_scope(ctx: PipelineContext, interval: float = 15.0) -> Iterator[None]:
    """Emit periodic lease heartbeats in background during intensive pipeline phases."""
    if getattr(ctx, "_heartbeat_ticker_active", False):
        yield
        return

    stop_event = threading.Event()

    def _heartbeat_ticker() -> None:
        while not stop_event.wait(interval):
            try:
                ok = ctx.heartbeat()
                if not ok:
                    logger.debug(
                        "Active heartbeat returned False for run %s (lease lost or reaped)",
                        getattr(ctx, "run_id", "?"),
                    )
            except Exception as exc:
                logger.debug("Active heartbeat tick error: %s", exc)

    setattr(ctx, "_heartbeat_ticker_active", True)
    rid_prefix = str(getattr(ctx, "run_id", "") or "")[:8]
    ticker = threading.Thread(
        target=_heartbeat_ticker,
        name=f"heartbeat-{rid_prefix}",
        daemon=True,
    )
    ticker.start()
    try:
        ctx.require_heartbeat()
        yield
    finally:
        setattr(ctx, "_heartbeat_ticker_active", False)
        stop_event.set()
        ticker.join(timeout=2.0)
        try:
            ctx.require_heartbeat()
        except Exception:
            pass
