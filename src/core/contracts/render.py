"""Render specification data contract for single-scene and multi-scene video composition."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_FIELD_KEYS = frozenset([
    "manifest_path",
    "output_video_path",
    "audio_path",
    "subtitle_path",
    "background_path",
    "bg_music_path",
    "music_volume",
    "duration_sec",
    "category",
    "orientation",
    "include_subtitles",
    "stream_copy",
    "scene_images",
    "shot_durations",
    "shot_roles",
    "crf",
    "preset",
    "fps",
    "width",
    "height",
    "threads",
    "metadata",
])
_PROPERTY_KEYS = frozenset(["video_path"])
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


@dataclass(slots=True)
class RenderSpec(Mapping):
    """Strongly-typed render parameters contract enforcing resource envelopes and composition specs."""

    manifest_path: Path | None = None
    output_video_path: Path | None = None
    audio_path: Path | None = None
    subtitle_path: Path | None = None
    background_path: str | None = None
    bg_music_path: str | None = None
    music_volume: float = 0.04
    duration_sec: float = 0.0
    category: str = ""
    orientation: str = "vertical"  # "vertical" | "horizontal"
    include_subtitles: bool = True
    stream_copy: bool = True
    scene_images: list[str] = field(default_factory=list)
    shot_durations: list[float] = field(default_factory=list)
    shot_roles: list[str] = field(default_factory=list)
    crf: int = 23
    preset: str = "veryfast"
    fps: int = 30
    width: int = 1080
    height: int = 1920
    threads: int = 2
    metadata: dict[str, Any] = field(default_factory=dict)
    _extra: dict[str, Any] = field(default_factory=dict)

    @property
    def video_path(self) -> Path | None:
        """Alias for output_video_path."""
        return self.output_video_path

    @video_path.setter
    def video_path(self, val: Path | str | None) -> None:
        self.output_video_path = Path(val) if val is not None else None

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "output_video_path": str(self.output_video_path) if self.output_video_path else None,
            "video_path": str(self.output_video_path) if self.output_video_path else None,
            "audio_path": str(self.audio_path) if self.audio_path else None,
            "subtitle_path": str(self.subtitle_path) if self.subtitle_path else None,
            "background_path": self.background_path,
            "bg_music_path": self.bg_music_path,
            "music_volume": self.music_volume,
            "duration_sec": self.duration_sec,
            "category": self.category,
            "orientation": self.orientation,
            "include_subtitles": self.include_subtitles,
            "stream_copy": self.stream_copy,
            "scene_images": list(self.scene_images),
            "shot_durations": list(self.shot_durations),
            "shot_roles": list(self.shot_roles),
            "crf": self.crf,
            "preset": self.preset,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "threads": self.threads,
            "metadata": dict(self.metadata),
        }
        res.update(self._extra)
        return res

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like access conforming to Mapping protocol."""
        try:
            return self[key]
        except KeyError:
            return default

    def __getitem__(self, key: str) -> Any:
        if key == "video_path":
            return self.output_video_path
        if key in _FIELD_KEYS:
            return getattr(self, key)
        if key in self._extra:
            return self._extra[key]
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key == "video_path":
            self.output_video_path = Path(value) if value is not None else None
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
        if name == "video_path":
            object.__setattr__(self, "output_video_path", Path(value) if value is not None else None)
        elif name in _FIELD_KEYS or name == "_extra":
            object.__setattr__(self, name, value)
        else:
            try:
                object.__setattr__(self, name, value)
            except AttributeError:
                extra = object.__getattribute__(self, "_extra")
                extra[name] = value

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RenderSpec:
        d = dict(data)
        manifest_path = d.pop("manifest_path", None)
        out_vid_primary = d.pop("output_video_path", None)
        out_vid_alias = d.pop("video_path", None)
        output_video_path = out_vid_primary if out_vid_primary is not None else out_vid_alias

        audio_path = d.pop("audio_path", None)
        subtitle_path = d.pop("subtitle_path", None)
        background_path = d.pop("background_path", None)
        bg_music_path = d.pop("bg_music_path", None)
        music_volume = _safe_float(d.pop("music_volume", 0.04), 0.04)
        duration_sec = _safe_float(d.pop("duration_sec", 0.0), 0.0)
        category = str(d.pop("category", "") or "")
        orientation = str(d.pop("orientation", "vertical") or "vertical")
        include_subtitles = bool(d.pop("include_subtitles", True))
        stream_copy = bool(d.pop("stream_copy", True))
        scene_images = list(d.pop("scene_images", None) or [])
        shot_durations = [_safe_float(x) for x in (d.pop("shot_durations", None) or [])]
        shot_roles = [str(x) for x in (d.pop("shot_roles", None) or [])]
        crf = _safe_int(d.pop("crf", 23), 23)
        preset = str(d.pop("preset", "veryfast") or "veryfast")
        fps = _safe_int(d.pop("fps", 30), 30)
        width = _safe_int(d.pop("width", 1080), 1080)
        height = _safe_int(d.pop("height", 1920), 1920)
        threads = _safe_int(d.pop("threads", 2), 2)
        metadata = d.pop("metadata", None)
        if not isinstance(metadata, dict):
            metadata = {}

        return cls(
            manifest_path=Path(manifest_path) if manifest_path else None,
            output_video_path=Path(output_video_path) if output_video_path else None,
            audio_path=Path(audio_path) if audio_path else None,
            subtitle_path=Path(subtitle_path) if subtitle_path else None,
            background_path=str(background_path) if background_path else None,
            bg_music_path=str(bg_music_path) if bg_music_path else None,
            music_volume=music_volume,
            duration_sec=duration_sec,
            category=category,
            orientation=orientation,
            include_subtitles=include_subtitles,
            stream_copy=stream_copy,
            scene_images=scene_images,
            shot_durations=shot_durations,
            shot_roles=shot_roles,
            crf=crf,
            preset=preset,
            fps=fps,
            width=width,
            height=height,
            threads=threads,
            metadata=metadata,
            _extra=d,
        )

    @classmethod
    def from_pipeline_context(cls, ctx: Any) -> RenderSpec:
        """Extract strongly-typed RenderSpec from PipelineContext."""
        audio_dur = 0.0
        if hasattr(ctx, "audio") and isinstance(ctx.audio, dict):
            audio_dur = _safe_float(ctx.audio.get("duration_sec", 0.0), 0.0)

        orientation = "vertical"
        if hasattr(ctx, "lane") and getattr(ctx.lane, "orientation", None):
            orientation = ctx.lane.orientation

        scenes = []
        if hasattr(ctx, "manifest_payload") and isinstance(ctx.manifest_payload, dict):
            scenes = ctx.manifest_payload.get("scenes") or []

        shot_roles = [
            str(sc.get("director_role") or "settled")
            for sc in scenes
            if isinstance(sc, dict)
        ]

        sub_path = None
        if getattr(ctx, "mux_subtitles", False):
            if hasattr(ctx, "ass_path") and ctx.ass_path and ctx.ass_path.is_file():
                sub_path = ctx.ass_path
            elif hasattr(ctx, "srt_path") and ctx.srt_path and ctx.srt_path.is_file():
                sub_path = ctx.srt_path

        threads = 4 if getattr(ctx, "is_long_lane", False) else 2
        lane_obj = getattr(ctx, "lane", None)
        fps = _safe_int(getattr(lane_obj, "fps", 30), 30)
        expected_res = getattr(lane_obj, "expected_resolution", None)
        width, height = (1920, 1080) if orientation == "horizontal" else (1080, 1920)
        if expected_res and len(expected_res) == 2:
            width = _safe_int(expected_res[0], width)
            height = _safe_int(expected_res[1], height)

        return cls(
            manifest_path=getattr(ctx, "manifest_path", None),
            output_video_path=getattr(ctx, "video_path", None),
            audio_path=getattr(ctx, "audio_path", None),
            subtitle_path=sub_path,
            background_path=str(getattr(ctx, "resolved_loop_path", "") or "") or None,
            bg_music_path=getattr(ctx, "music_track_path", "") or None,
            music_volume=getattr(ctx, "bg_volume", 0.04),
            duration_sec=audio_dur,
            category=getattr(ctx, "target_category", ""),
            orientation=orientation,
            include_subtitles=getattr(ctx, "mux_subtitles", False),
            stream_copy=getattr(ctx, "stream_copy_mode", True),
            scene_images=list(getattr(ctx, "scene_bg_list", []) or []),
            shot_durations=list(getattr(ctx, "shot_durations", []) or []),
            shot_roles=shot_roles,
            fps=fps,
            width=width,
            height=height,
            threads=threads,
        )

    def validate(self) -> None:
        """Validate rendering invariants (resource limits, duration, resolution)."""
        if self.duration_sec < 0:
            raise ValueError(f"duration_sec cannot be negative: {self.duration_sec}")
        if self.threads > 4:
            raise ValueError(f"threads cannot exceed 4 according to AGENTS.md guardrails: {self.threads}")
        if self.orientation not in ("vertical", "horizontal"):
            raise ValueError(f"orientation must be vertical or horizontal, got: {self.orientation}")
