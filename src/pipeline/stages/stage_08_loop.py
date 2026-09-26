"""Stage 8: Build scene manifest and resolve stream-copy / subtitle mux flags."""

from __future__ import annotations

import json

from src.core.guard import memory_checkpoint
from src.core.profiling import CanonicalStage
from src.log import get_logger
from src.pipeline.context import PipelineContext

logger = get_logger("pipeline.stages.stage_08_loop")


def _build_video_loop_manifest(ctx: PipelineContext) -> None:
    """Configure stream-copy video loop manifest."""
    stream_copy_mode = True
    ctx.stream_copy_mode = stream_copy_mode
    ass_path = getattr(ctx, "ass_path", None)
    ctx.mux_subtitles = bool(ctx.subtitles_active and ass_path and ass_path.is_file())

    from src.scene_manifest import build_scene_manifest

    manifest_slot = ctx.story.get("object_class") or ctx.channel_name
    duration = float(ctx.audio.get("duration_sec", 0.0) if isinstance(ctx.audio, dict) else ctx.audio["duration_sec"])

    ctx.manifest_path = build_scene_manifest(
        work_dir=ctx.work_dir,
        scp_id=ctx.story_id,
        title=ctx.title,
        object_class=manifest_slot,
        attribution=ctx.story.get("attribution") or ctx.title or "Fuente original",
        narration_path=ctx.audio_path,
        music_path=ctx.music_track_path,
        duration_sec=duration,
        scene_images=ctx.scene_bg_list,
        subtitles=[],
        resolution=tuple(ctx.lane.expected_resolution),
        fps=ctx.lane.fps,
        stamp_text=f"[{ctx.channel_name.upper()}]",
        channel_name=ctx.channel_name,
        shot_durations=ctx.shot_durations,
    )


def _build_asset_manifest(ctx: PipelineContext) -> None:
    """Build the asset-only manifest used by every production lane.

    Video scenes are already resolved to local loop files by Stage 4.  This stage
    only records those paths and mux flags; it never requests a renderer, camera
    motion, overlay, or procedural scene plan.
    """
    _build_video_loop_manifest(ctx)


def stage_08_loop_scene(ctx: PipelineContext) -> None:
    """Stage 8: Build scene manifest and resolve stream-copy / subtitle mux flags."""
    with ctx.profiler.phase(CanonicalStage.LOOP_SCENE):
        memory_checkpoint("8_loop_scene")
        _build_asset_manifest(ctx)

        memory_checkpoint("8_loop_scene")
