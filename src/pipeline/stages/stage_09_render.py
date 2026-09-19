"""Stage 9: Video composition via stream-copy or MultiSceneCompositor."""

from __future__ import annotations

from src.core.contracts import RenderSpec
from src.core.guard import memory_checkpoint
from src.core.profiling import CanonicalStage
from src.core.render_guard import _LONG_RENDER_SEMAPHORE, _SHORT_RENDER_SEMAPHORE
from src.log import get_logger
from src.pipeline.context import PipelineContext, active_heartbeat_scope

logger = get_logger("pipeline.stages.stage_09_render")


def stage_09_video_rendering(ctx: PipelineContext) -> None:
    """Stage 9: Video composition via stream-copy or MultiSceneCompositor."""
    with ctx.profiler.phase(CanonicalStage.VIDEO_RENDERING):
        memory_checkpoint("9_video_rendering")

        render_spec = RenderSpec.from_pipeline_context(ctx)
        try:
            render_spec.validate()
        except ValueError as exc:
            logger.warning("RenderSpec validation warning: %s", exc)
        ctx.render_spec = render_spec

        stream_copy_mode = render_spec.stream_copy
        mux_subtitles = render_spec.include_subtitles

        render_sem = _LONG_RENDER_SEMAPHORE if ctx.is_long_lane else _SHORT_RENDER_SEMAPHORE
        with render_sem, active_heartbeat_scope(ctx):
            if ctx.is_multiscene_mode:
                from src.media.encode_defaults import default_render_crf, default_render_preset

                ctx.compositor_metrics = ctx.multi_compositor.render(
                    manifest_path=render_spec.manifest_path or ctx.manifest_path,
                    output_video_path=render_spec.output_video_path or ctx.video_path,
                    crf=render_spec.crf or default_render_crf(),
                    preset=render_spec.preset or default_render_preset(),
                    subtitle_path=render_spec.subtitle_path,
                )
                ctx.visual_integrity_report = {
                    "passed": True,
                    "bypassed": False,
                    "engine": "multi_scene_dual_engine",
                    "scenes_count": len(ctx.manifest_payload.get("scenes", [])),
                }
            else:
                ctx.compositor_metrics = ctx.loop_engine.render(
                    render_spec.manifest_path or ctx.manifest_path,
                    render_spec.output_video_path or ctx.video_path,
                    audio_path=render_spec.audio_path or ctx.audio_path,
                    subtitle_path=render_spec.subtitle_path if mux_subtitles else None,
                    background_path=str(render_spec.background_path or ctx.resolved_loop_path),
                    bg_music_path=render_spec.bg_music_path or ctx.music_track_path,
                    music_volume=render_spec.music_volume,
                    duration_sec=float(render_spec.duration_sec or ctx.audio["duration_sec"]),
                    category=render_spec.category or ctx.target_category,
                    orientation=render_spec.orientation,
                    include_subtitles=mux_subtitles,
                    stream_copy=stream_copy_mode,
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

        ctx.repository.record_artifact(
            ctx.run_id, "video", local_path=str(ctx.video_path), size_bytes=ctx.video_path.stat().st_size
        )
