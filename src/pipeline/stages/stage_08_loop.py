"""Stage 8: Build scene manifest and resolve stream-copy / subtitle mux flags."""

from __future__ import annotations

import json

from src.core.guard import memory_checkpoint
from src.core.profiling import CanonicalStage
from src.log import get_logger
from src.media.visual_coherence import timing_scales_to_audio
from src.pipeline.context import PipelineContext

logger = get_logger("pipeline.stages.stage_08_loop")


def _build_video_loop_manifest(ctx: PipelineContext) -> None:
    """Configure stream-copy video loop manifest."""
    ctx.stream_copy_mode = True
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


def _build_image_animation_manifest(ctx: PipelineContext) -> None:
    """Configure image animation manifest with scaled timing and Ken Burns motion."""
    ctx.stream_copy_mode = False
    ctx.mux_subtitles = False  # Subtitles burned directly via libass in unified encoder

    audio_dur = float(ctx.audio.get("duration_sec", 0.0) if isinstance(ctx.audio, dict) else ctx.audio["duration_sec"])
    if ctx.shot_durations and audio_dur > 0:
        ctx.shot_durations = timing_scales_to_audio(ctx.shot_durations, audio_dur)

    if ctx.is_multiscene_mode:
        ctx.manifest_payload = ctx.planner_agent.plan_manifest(
            script=ctx.script_payload,
            visual_plan=ctx.visual_plan_payload,
            story_id=ctx.story_id,
            narration_path=str(ctx.audio_path),
            music_path=str(ctx.music_track_path) if ctx.music_track_path else "",
            music_volume=ctx.bg_volume,
            lane_id=ctx.lane.id,
            channel_name=ctx.channel_name,
            resolution=list(ctx.lane.expected_resolution),
            fps=ctx.lane.fps,
            actual_audio_duration=audio_dur,
        )
        ctx.scene_manifest_path.write_text(
            json.dumps(ctx.manifest_payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        ctx.manifest_path = ctx.scene_manifest_path
    else:
        from src.scene_manifest import build_scene_manifest

        manifest_slot = ctx.story.get("object_class") or ctx.channel_name
        ctx.manifest_path = build_scene_manifest(
            work_dir=ctx.work_dir,
            scp_id=ctx.story_id,
            title=ctx.title,
            object_class=manifest_slot,
            attribution=ctx.story.get("attribution") or ctx.title or "Fuente original",
            narration_path=ctx.audio_path,
            music_path=ctx.music_track_path,
            duration_sec=audio_dur,
            scene_images=ctx.scene_bg_list,
            subtitles=[],
            resolution=tuple(ctx.lane.expected_resolution),
            fps=ctx.lane.fps,
            stamp_text=f"[{ctx.channel_name.upper()}]",
            channel_name=ctx.channel_name,
            shot_durations=ctx.shot_durations,
        )


def _build_legacy_manifest(ctx: PipelineContext) -> None:
    """Build manifest for beats / director legacy modes."""
    subtitles_active = ctx.subtitles_active
    ass_path = getattr(ctx, "ass_path", None)
    ctx.mux_subtitles = bool(subtitles_active and ass_path and ass_path.is_file())

    is_horizontal_director = (
        getattr(ctx.lane, "orientation", "") == "horizontal"
        and getattr(ctx.lane, "visual_pipeline", "") == "director"
    )
    if is_horizontal_director:
        _build_video_loop_manifest(ctx)
        return

    ctx.stream_copy_mode = not ctx.is_multiscene_mode

    if ctx.is_multiscene_mode:
        ctx.manifest_payload = ctx.planner_agent.plan_manifest(
            script=ctx.script_payload,
            visual_plan=ctx.visual_plan_payload,
            story_id=ctx.story_id,
            narration_path=str(ctx.audio_path),
            music_path=str(ctx.music_track_path) if ctx.music_track_path else "",
            music_volume=ctx.bg_volume,
            lane_id=ctx.lane.id,
            channel_name=ctx.channel_name,
            resolution=list(ctx.lane.expected_resolution),
            fps=ctx.lane.fps,
            actual_audio_duration=float(ctx.audio.get("duration_sec", 0.0) or 0.0),
        )
        ctx.scene_manifest_path.write_text(
            json.dumps(ctx.manifest_payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        ctx.manifest_path = ctx.scene_manifest_path
        return

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


def stage_08_loop_scene(ctx: PipelineContext) -> None:
    """Stage 8: Build scene manifest and resolve stream-copy / subtitle mux flags."""
    with ctx.profiler.phase(CanonicalStage.LOOP_SCENE):
        memory_checkpoint("8_loop_scene")
        pipeline = getattr(getattr(ctx, "lane", None), "visual_pipeline", "beats")
        is_horizontal_director = (
            getattr(ctx.lane, "orientation", "") == "horizontal"
            and getattr(ctx.lane, "visual_pipeline", "") == "director"
        )

        if is_horizontal_director or pipeline == "video_loop":
            _build_video_loop_manifest(ctx)
        elif pipeline == "image_animation":
            _build_image_animation_manifest(ctx)
        else:
            _build_legacy_manifest(ctx)

        memory_checkpoint("8_loop_scene")
