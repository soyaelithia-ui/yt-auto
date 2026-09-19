"""Stage 4: Visual plan planning, shot pacing, and background audio resolution."""

from __future__ import annotations

import json
from src.agents.art_director import ArtDirectorMoodAgent
from src.agents.scene_planner import ScenePlannerCompositorAgent
from src.agents.script_curator import CinematicScriptCuratorAgent
from src.asset_manager import get_asset_manager
from src.core.profiling import CanonicalStage
from src.log import get_logger
from src.pipeline.context import PipelineContext
from src.pipeline.utils import is_pipeline_test_environment as is_test_environment

logger = get_logger("pipeline.stages.stage_04_mood")


def stage_04_mood_theme(ctx: PipelineContext) -> None:
    """Stage 4: Visual plan planning, shot pacing, and background audio resolution."""
    with ctx.profiler.phase(CanonicalStage.MOOD_THEME):
        assets = get_asset_manager()
        ctx.target_category = (
            ctx.loop_category
            or getattr(ctx.lane, "loop_category", None)
            or getattr(ctx.lane, "story_type", None)
            or ("cosmic_horror" if ctx.channel_name == "moku" else "dark_ambient")
        )

        bg_audio_cfg = getattr(ctx.lane, "background_audio", None)
        bg_enabled = getattr(bg_audio_cfg, "enabled", True) if bg_audio_cfg else True
        ctx.bg_volume = float(getattr(bg_audio_cfg, "volume", 0.04)) if bg_audio_cfg else 0.04
        bg_mode = str(getattr(bg_audio_cfg, "mode", "auto")) if bg_audio_cfg else "auto"
        bg_theme = getattr(bg_audio_cfg, "theme", None) or ctx.target_category

        if hasattr(assets, "resolve_or_create_background_audio"):
            ctx.music_track_path = assets.resolve_or_create_background_audio(
                category=bg_theme,
                style=ctx.lane.template,
                duration_sec=float(ctx.audio.get("duration_sec", 60.0)),
                work_dir=ctx.work_dir,
                mode=bg_mode if bg_enabled else "off",
            )
        elif hasattr(assets, "get_music"):
            ctx.music_track_path = assets.get_music(style=ctx.lane.template)
        else:
            ctx.music_track_path = ""

        if ctx.is_multiscene_mode:
            from src.media.compositor import MultiSceneCompositor

            curator = CinematicScriptCuratorAgent()
            art = ArtDirectorMoodAgent()
            ctx.planner_agent = ScenePlannerCompositorAgent()
            ctx.multi_compositor = MultiSceneCompositor()

            target_fmt = "short" if ctx.lane.orientation == "vertical" else "longform"
            ctx.script_payload = curator.curate(
                raw_text=ctx.clean_script,
                title=ctx.title,
                channel_lane=ctx.lane.id,
                target_format=target_fmt,
            )
            (ctx.work_dir / "cinematic_script.json").write_text(
                json.dumps(ctx.script_payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            ctx.visual_plan_payload = art.plan_visuals(
                cinematic_script=ctx.script_payload, theme_lane=ctx.target_category
            )
            ctx.visual_plan_path.write_text(
                json.dumps(ctx.visual_plan_payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return

        from src.media.loop_engine import LoopVideoEngine

        ctx.loop_engine = LoopVideoEngine()
        total_audio_sec = (
            float(ctx.audio.get("duration_sec", 15.0) or 15.0) if isinstance(ctx.audio, dict) else 15.0
        )
        ctx.resolved_loop_path = ctx.loop_engine.resolve_continuous_loop(
            orientation=ctx.lane.orientation,
            allow_test_mock=is_test_environment(),
        )
        ctx.scene_bg_list = [str(ctx.resolved_loop_path)]
        ctx.shot_durations = [total_audio_sec]
        ctx.target_category = getattr(ctx.lane, "loop_category", None) or "neutral_loop"
        scenes_plan = [
            {
                "duration": total_audio_sec,
                "source": str(ctx.resolved_loop_path),
                "category": str(ctx.target_category),
                "shot_index": 0,
            }
        ]
        ctx.visual_plan_payload = {
            "video_engine": "loop",
            "loop": True,
            "mode": "loop",
            "category": str(ctx.target_category),
            "scenes": scenes_plan,
            "covered_seconds": total_audio_sec,
            "black_fallbacks": 0,
            "shot_durations": ctx.shot_durations,
        }
        ctx.visual_plan_path.write_text(
            json.dumps(ctx.visual_plan_payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info(
            "Continuous single-loop composition: %s (duration: %.1fs)", ctx.resolved_loop_path, total_audio_sec
        )
