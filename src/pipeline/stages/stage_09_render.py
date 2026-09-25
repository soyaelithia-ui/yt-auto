"""Stage 9: Local asset video composition via stream-copy."""

from __future__ import annotations

from src.core.contracts import RenderSpec
from src.core.guard import memory_checkpoint
from src.core.profiling import CanonicalStage
from src.core.render_guard import _LONG_RENDER_SEMAPHORE, _SHORT_RENDER_SEMAPHORE
from src.log import get_logger
from src.pipeline.context import PipelineContext, active_heartbeat_scope

logger = get_logger("pipeline.stages.stage_09_render")


def _render_video_loop(ctx: PipelineContext, render_spec: RenderSpec) -> None:
    """Execute stream-copy video composition with soft subtitle muxing (REG-13)."""
    if getattr(ctx, "loop_engine", None) is None:
        from src.media.loop_engine import LoopVideoEngine
        ctx.loop_engine = LoopVideoEngine()

    mux_subtitles = render_spec.include_subtitles
    bg_path = (
        render_spec.background_path
        or getattr(ctx, "resolved_loop_path", None)
        or (ctx.scene_bg_list[0] if getattr(ctx, "scene_bg_list", None) else "")
    )
    ctx.compositor_metrics = ctx.loop_engine.render(
        render_spec.manifest_path or ctx.manifest_path,
        render_spec.output_video_path or ctx.video_path,
        audio_path=render_spec.audio_path or ctx.audio_path,
        subtitle_path=render_spec.subtitle_path if mux_subtitles else None,
        background_path=str(bg_path),
        bg_music_path=render_spec.bg_music_path or ctx.music_track_path,
        music_volume=render_spec.music_volume,
        duration_sec=float(render_spec.duration_sec or ctx.audio["duration_sec"]),
        category=render_spec.category or ctx.target_category,
        orientation=render_spec.orientation,
        include_subtitles=mux_subtitles,
        stream_copy=True,
        scene_images=render_spec.scene_images,
        shot_durations=render_spec.shot_durations,
        shot_roles=render_spec.shot_roles,
        channel=ctx.channel_name,
    )
    quality_metrics = (
        (ctx.compositor_metrics.get("quality_metrics") if isinstance(ctx.compositor_metrics, dict) else {})
        or {}
    )
    ctx.visual_integrity_report = {"engine": "loop"}
    if quality_metrics and isinstance(quality_metrics, dict):
        if "longest_black_seconds" in quality_metrics:
            ctx.visual_integrity_report["longest_black_seconds"] = quality_metrics["longest_black_seconds"]
            ctx.visual_integrity_report["black_segments"] = quality_metrics.get("black_segments", [])
        if quality_metrics.get("perceptual_luminance") is not None:
            ctx.visual_integrity_report["perceptual_luminance"] = quality_metrics["perceptual_luminance"]


def stage_09_video_rendering(ctx: PipelineContext) -> None:
    """Stage 9: Video composition from local assets only."""
    with ctx.profiler.phase(CanonicalStage.VIDEO_RENDERING):
        memory_checkpoint("9_video_rendering")

        render_spec = RenderSpec.from_pipeline_context(ctx)
        try:
            render_spec.validate()
        except ValueError as exc:
            logger.warning("RenderSpec validation warning: %s", exc)
        ctx.render_spec = render_spec

        raw_dur = getattr(ctx.lane, "duration_target_sec", None)
        if raw_dur is None or isinstance(raw_dur, type(ctx)):
            raw_dur = getattr(ctx.lane, "target_duration_sec", 0.0)
        try:
            target_dur = float(raw_dur)
        except (TypeError, ValueError):
            target_dur = 0.0

        is_long = bool(
            ctx.is_long_lane
            or getattr(ctx.lane, "target_format", "") == "longform"
            or target_dur >= 600.0
        )
        is_horizontal = getattr(ctx.lane, "orientation", "") == "horizontal"

        # Resource Work Refusal check (Section 5 AGENTS.md, REG-14)
        if (is_long or ctx.is_long_lane) and is_horizontal:
            burn = (
                getattr(render_spec, "burn_subtitles", False)
                or getattr(ctx, "burn_subtitles", False)
                or getattr(render_spec, "subtitles_burned", False)
            )
            reencode = bool(getattr(render_spec, "reencode", False))
            if burn or reencode:
                raise ValueError(
                    "RESOURCE WORK REFUSAL: Burning subtitles or re-encoding video on 16:9 horizontal "
                    "longform violates Section 5 of AGENTS.md and REG-14. Use stream-copy (-c:v copy) "
                    "and soft-muxing (-c:s mov_text)."
                )

        render_sem = _LONG_RENDER_SEMAPHORE if (is_long or ctx.is_long_lane) else _SHORT_RENDER_SEMAPHORE
        with render_sem, active_heartbeat_scope(ctx):
            _render_video_loop(ctx, render_spec)

        ctx.repository.record_artifact(
            ctx.run_id, "video", local_path=str(ctx.video_path), size_bytes=ctx.video_path.stat().st_size
        )
        memory_checkpoint("9_video_rendering")
