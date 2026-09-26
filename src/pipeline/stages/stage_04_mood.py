"""Stage 4: Visual plan planning, shot pacing, and background audio resolution."""

from __future__ import annotations

import json
import os
from src.media.manifest_compiler import ScenePlannerCompositorAgent
from src.curators.text_splitter import TextSegmentationEngine, CinematicScriptCuratorAgent
from src.asset_manager import get_asset_manager
from src.core.profiling import CanonicalStage
from src.log import get_logger
from src.media.interface import MultiActVisualSpec
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

        is_horizontal_director = (
            getattr(ctx.lane, "orientation", "") == "horizontal"
            and getattr(ctx.lane, "visual_pipeline", "") == "director"
        )
        is_killswitch = os.environ.get("FORCE_SINGLE_LOOP", "").strip().lower() in ("1", "true", "yes", "on")

        if is_horizontal_director and not is_killswitch:
            try:
                if ctx.script_payload is None:
                    curator = CinematicScriptCuratorAgent()
                    ctx.script_payload = curator.curate(
                        raw_text=ctx.clean_script or getattr(ctx, "script", "") or "",
                        title=ctx.title or "",
                        channel_lane=getattr(ctx.lane, "id", ""),
                        target_format="longform",
                    )
                    (ctx.work_dir / "cinematic_script.json").write_text(
                        json.dumps(ctx.script_payload, indent=2, ensure_ascii=False), encoding="utf-8"
                    )

                acts = ctx.script_payload.get("acts", []) if isinstance(ctx.script_payload, dict) else []
                if acts:
                    from src.media.loop_engine import LoopVideoEngine
                    ctx.loop_engine = LoopVideoEngine()

                    total_audio_sec = (
                        float(ctx.audio.get("duration_sec", 0.0) or 0.0)
                        if isinstance(ctx.audio, dict)
                        else 0.0
                    )
                    raw_durs = [
                        float(
                            a.get("target_duration_sec")
                            or a.get("estimated_duration_sec")
                            or a.get("duration_sec")
                            or 30.0
                        )
                        for a in acts
                    ]
                    if total_audio_sec > 0.0 and abs(sum(raw_durs) - total_audio_sec) > 0.1:
                        scaled = TextSegmentationEngine.scale_act_durations(raw_durs, total_audio_sec)
                        for a, s in zip(acts, scaled):
                            if isinstance(a, dict):
                                a["target_duration_sec"] = s

                    loop_paths, act_durations = ctx.loop_engine.resolve_multi_act_loops(
                        acts=acts,
                        orientation=ctx.lane.orientation,
                        channel=str(ctx.channel_name),
                        category=str(ctx.target_category),
                        allow_test_mock=is_test_environment(),
                    )
                    ctx.scene_bg_list = [str(p) for p in loop_paths]
                    ctx.shot_durations = act_durations
                    spec = MultiActVisualSpec(
                        video_engine="director",
                        stream_copy=True,
                        lane_id=str(getattr(ctx.lane, "id", "")),
                        orientation="horizontal",
                        total_duration_sec=sum(act_durations),
                        scene_bg_list=ctx.scene_bg_list,
                        shot_durations=ctx.shot_durations,
                        act_titles=[str(a.get("act_title", f"Acto {i+1}")) for i, a in enumerate(acts)],
                        act_tensions=[int(a.get("tension_level", 1)) for a in acts],
                        is_killswitch_active=False,
                    )
                    ctx.visual_plan_payload = spec.to_dict()
                    ctx.visual_plan_path.write_text(
                        json.dumps(ctx.visual_plan_payload, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                    logger.info(
                        "Hybrid Multi-Act Director visual plan resolved: %d acts, %d distinct loops",
                        len(acts),
                        len(set(ctx.scene_bg_list)),
                    )
                    return
            except Exception as exc:
                logger.warning("pipeline.mood.multi_act_fallback: %s", exc, exc_info=True)

        from src.media.loop_engine import LoopVideoEngine

        ctx.loop_engine = LoopVideoEngine()
        total_audio_sec = (
            float(ctx.audio.get("duration_sec", 15.0) or 15.0) if isinstance(ctx.audio, dict) else 15.0
        )
        ctx.resolved_loop_path = ctx.loop_engine.resolve_continuous_loop(
            orientation=ctx.lane.orientation,
            category=str(ctx.target_category),
            channel=str(ctx.channel_name),
            allow_test_mock=is_test_environment(),
        )
        ctx.scene_bg_list = [str(ctx.resolved_loop_path)]
        ctx.shot_durations = [total_audio_sec]
        ctx.target_category = ctx.target_category or getattr(ctx.lane, "loop_category", None) or "neutral_loop"
        scenes_plan = [
            {
                "duration": total_audio_sec,
                "source": str(ctx.resolved_loop_path),
                "category": str(ctx.target_category),
                "shot_index": 0,
            }
        ]
        if is_horizontal_director:
            spec = MultiActVisualSpec(
                video_engine="director",
                stream_copy=True,
                lane_id=str(getattr(ctx.lane, "id", "")),
                orientation="horizontal",
                total_duration_sec=total_audio_sec,
                scene_bg_list=ctx.scene_bg_list,
                shot_durations=ctx.shot_durations,
                act_titles=["Continuous Single Loop"],
                act_tensions=[1],
                is_killswitch_active=bool(is_killswitch),
            )
            ctx.visual_plan_payload = spec.to_dict()
        else:
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
