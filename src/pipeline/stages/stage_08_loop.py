"""Stage 8: Build scene manifest and resolve stream-copy / subtitle mux flags."""

from __future__ import annotations

import json

from src.core.guard import memory_checkpoint
from src.core.profiling import CanonicalStage
from src.log import get_logger
from src.pipeline.context import PipelineContext

logger = get_logger("pipeline.stages.stage_08_loop")


def stage_08_loop_scene(ctx: PipelineContext) -> None:
    """Stage 8: Build scene manifest and resolve stream-copy / subtitle mux flags."""
    with ctx.profiler.phase(CanonicalStage.LOOP_SCENE):
        memory_checkpoint("8_loop_scene")
        subtitles_active = ctx.subtitles_active
        ass_path = ctx.ass_path
        mux_subtitles = bool(subtitles_active and ass_path.is_file())
        stream_copy_mode = True
        ctx.mux_subtitles = mux_subtitles
        ctx.stream_copy_mode = stream_copy_mode

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

        ctx.manifest_path = build_scene_manifest(
            work_dir=ctx.work_dir,
            scp_id=ctx.story_id,
            title=ctx.title,
            object_class=manifest_slot,
            attribution=ctx.story.get("attribution") or ctx.title or "Fuente original",
            narration_path=ctx.audio_path,
            music_path=ctx.music_track_path,
            duration_sec=float(ctx.audio["duration_sec"]),
            scene_images=ctx.scene_bg_list,
            subtitles=[],
            resolution=tuple(ctx.lane.expected_resolution),
            fps=ctx.lane.fps,
            stamp_text=f"[{ctx.channel_name.upper()}]",
            channel_name=ctx.channel_name,
            shot_durations=ctx.shot_durations,
        )
