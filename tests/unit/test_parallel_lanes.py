"""Unit test suite for Parallel Lanes architecture, visual pipeline contracts,
and dual paradigm configuration (image_animation vs video_loop).
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

from src.core.contracts.render import RenderSpec
from src.core.lanes import (
    ALLOWED_VISUAL_PIPELINES,
    LaneProfile,
    load_lanes,
    parse_lane,
)


def _minimal_lane_dict(lane_id: str = "test-lane", visual_pipeline: str = "beats") -> dict:
    return {
        "id": lane_id,
        "channel": "horror",
        "story_type": "scp",
        "orientation": "vertical",
        "duration": {"min_sec": 60, "target_sec": 90, "max_sec": 180},
        "words": {"min": 160, "max": 340, "recondense_max": 300},
        "template": "shorts_creepypasta",
        "voice_rate": "+0%",
        "cadence": {"min_gap_seconds": 300},
        "visual_pipeline": visual_pipeline,
        "sources": {
            "kind": "reddit",
            "subreddits": ["nosleep"],
        },
    }


class TestParallelLanesFoundationContracts:
    """Test assertions for Phase 1: Foundation Data Contracts & Declarative Lane Matrix."""

    def test_allowed_visual_pipelines_contains_dual_paradigms(self):
        """Asserts that {"image_animation", "video_loop"}.issubset(ALLOWED_VISUAL_PIPELINES)."""
        assert {"image_animation", "video_loop"}.issubset(ALLOWED_VISUAL_PIPELINES)

    def test_parse_lane_image_animation(self):
        """Asserts parse_lane() parses 'visual_pipeline': 'image_animation' cleanly."""
        raw = _minimal_lane_dict("horror-scp-shorts", visual_pipeline="image_animation")
        lane = parse_lane(raw)
        assert lane.visual_pipeline == "image_animation"
        assert isinstance(lane, LaneProfile)

    def test_parse_lane_video_loop(self):
        """Asserts parse_lane() parses 'visual_pipeline': 'video_loop' cleanly."""
        raw = _minimal_lane_dict("drama-drama-shorts", visual_pipeline="video_loop")
        lane = parse_lane(raw)
        assert lane.visual_pipeline == "video_loop"
        assert isinstance(lane, LaneProfile)

    def test_parse_lane_unsupported_visual_pipeline_raises(self):
        """Asserts parse_lane() with unsupported visual pipeline raises ValueError listing options."""
        raw = _minimal_lane_dict("invalid-lane", visual_pipeline="unsupported_webgl")
        with pytest.raises(ValueError) as exc_info:
            parse_lane(raw)
        err = str(exc_info.value)
        assert "visual_pipeline" in err
        assert "unsupported_webgl" in err
        for allowed in ALLOWED_VISUAL_PIPELINES:
            assert allowed in err

    def test_canonical_six_lanes_have_valid_visual_pipelines(self):
        """Loads config/lanes.json and verifies all six canonical production lanes define valid pipelines."""
        all_lanes = load_lanes(include_disabled=True)
        lanes_by_id = {lane.id: lane for lane in all_lanes}
        expected_lanes = {
            "horror-scp-shorts": "image_animation",
            "horror-horror-long": "director",
            "drama-drama-shorts": "video_loop",
            "drama-aita-long": "director",
            "scifi-singularity-shorts": "image_animation",
            "scifi-singularity-long": "director",
        }
        for lane_id, expected_pipeline in expected_lanes.items():
            assert lane_id in lanes_by_id, f"Missing canonical lane: {lane_id}"
            lane = lanes_by_id[lane_id]
            assert lane.visual_pipeline in ALLOWED_VISUAL_PIPELINES
            assert lane.visual_pipeline == expected_pipeline

    def test_renderspec_visual_pipeline_contract(self):
        """Asserts RenderSpec includes visual_pipeline: str = 'beats' and inherits from context."""
        spec_default = RenderSpec()
        assert hasattr(spec_default, "visual_pipeline")
        assert spec_default.visual_pipeline == "beats"
        assert spec_default.to_dict()["visual_pipeline"] == "beats"

        # Test from_dict
        spec_dict = RenderSpec.from_dict({"visual_pipeline": "image_animation"})
        assert spec_dict.visual_pipeline == "image_animation"

        # Test from_pipeline_context
        fake_lane = SimpleNamespace(
            visual_pipeline="video_loop",
            orientation="vertical",
            fps=30,
            expected_resolution=(1080, 1920),
        )
        fake_ctx = SimpleNamespace(
            lane=fake_lane,
            audio={"duration_sec": 45.0},
            video_path=Path("/tmp/fake.mp4"),
            audio_path=Path("/tmp/fake.mp3"),
            mux_subtitles=True,
            ass_path=None,
            srt_path=None,
            is_long_lane=False,
            stream_copy_mode=True,
            scene_bg_list=[],
            shot_durations=[],
            manifest_payload={"scenes": []},
            target_category="drama",
            resolved_loop_path="/tmp/loop.mp4",
            music_track_path=None,
            bg_volume=0.04,
        )
        spec_from_ctx = RenderSpec.from_pipeline_context(fake_ctx)
        assert spec_from_ctx.visual_pipeline == "video_loop"

        # Test validation on invalid pipeline
        invalid_spec = RenderSpec(visual_pipeline="invalid_format")
        with pytest.raises(ValueError) as exc:
            invalid_spec.validate()
        assert "visual_pipeline" in str(exc.value)


class DummyProfiler:
    from contextlib import contextmanager

    @contextmanager
    def phase(self, stage):
        yield


def _make_pipeline_context(tmp_path: Path, visual_pipeline: str = "video_loop", is_long_lane: bool = False):
    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    video_path = tmp_path / "out.mp4"
    video_path.write_bytes(b"\0" * 200)
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"\0" * 100)
    ass_path = tmp_path / "subs.ass"
    ass_path.write_text("[Script Info]\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")

    lane = SimpleNamespace(
        id=f"lane-{visual_pipeline}",
        visual_pipeline=visual_pipeline,
        orientation="vertical" if not is_long_lane else "horizontal",
        fps=30,
        expected_resolution=(1080, 1920) if not is_long_lane else (1920, 1080),
    )

    ctx = SimpleNamespace(
        lane=lane,
        channel_name="moku",
        target_category="horror",
        story_id="story-123",
        run_id="run-456",
        title="Test Story",
        story={"attribution": "reddit", "object_class": "Safe"},
        audio={"duration_sec": 15.0},
        audio_path=audio_path,
        video_path=video_path,
        ass_path=ass_path,
        srt_path=None,
        subtitles_active=True,
        mux_subtitles=False,
        stream_copy_mode=True,
        is_long_lane=is_long_lane,
        is_multiscene_mode=False,
        work_dir=work_dir,
        manifest_path=manifest_path,
        scene_manifest_path=manifest_path,
        manifest_payload={},
        script_payload={"acts": []},
        visual_plan_payload={"scenes": []},
        resolved_loop_path=str(tmp_path / "loop.mp4"),
        music_track_path=None,
        bg_volume=0.04,
        scene_bg_list=[],
        shot_durations=[],
        profiler=DummyProfiler(),
        heartbeat=MagicMock(return_value=True),
        require_heartbeat=MagicMock(),
        loop_engine=SimpleNamespace(render=MagicMock(return_value={"engine": "loop", "quality_metrics": {}})),
        planner_agent=SimpleNamespace(plan_manifest=MagicMock(return_value={"scenes": []})),
        multi_compositor=SimpleNamespace(render=MagicMock(return_value={"engine": "multi_scene_dual_engine"})),
        repository=SimpleNamespace(record_artifact=MagicMock()),
    )
    return ctx


class TestParallelLanesPipelineIntegration:
    """Tests for Phase 3: Pipeline Integration, Stage Segregation & Lane Fallbacks."""

    def test_stage_08_loop_scene_video_loop_lane(self, tmp_path):
        """Asserts that when ctx.lane.visual_pipeline == 'video_loop', stage_08_loop_scene
        resolves catalog loop, sets ctx.stream_copy_mode = True, and sets ctx.mux_subtitles = True
        without invoking still image planner."""
        from unittest.mock import MagicMock
        from src.pipeline.stages.stage_08_loop import stage_08_loop_scene

        ctx = _make_pipeline_context(tmp_path, visual_pipeline="video_loop")
        stage_08_loop_scene(ctx)

        assert ctx.stream_copy_mode is True
        assert ctx.mux_subtitles is True
        # Planner agent must NOT be called for video_loop
        assert ctx.planner_agent.plan_manifest.call_count == 0

    def test_stage_08_loop_scene_image_animation_lane(self, tmp_path):
        """Asserts that when ctx.lane.visual_pipeline == 'image_animation', stage_08_loop_scene
        sets ctx.stream_copy_mode = False, resolves still assets, scales scene durations via
        timing_scales_to_audio(), and plans Ken Burns camera motion."""
        from src.pipeline.stages.stage_08_loop import stage_08_loop_scene

        ctx = _make_pipeline_context(tmp_path, visual_pipeline="image_animation")
        ctx.shot_durations = [3.0, 4.0, 5.0]
        ctx.scene_bg_list = ["/path/img1.jpg", "/path/img2.jpg", "/path/img3.jpg"]

        stage_08_loop_scene(ctx)

        assert ctx.stream_copy_mode is False
        assert ctx.mux_subtitles is False  # Subtitles burned via libass
        assert ctx.shot_durations == [3.75, 5.0, 6.25]
        assert ctx.manifest_path is not None

    def test_stage_09_render_video_loop_stream_copy(self, tmp_path):
        """Asserts that when visual_pipeline == 'video_loop', stage_09_video_rendering
        delegates to ctx.loop_engine.render() with stream_copy=True."""
        from src.pipeline.stages.stage_09_render import stage_09_video_rendering

        ctx = _make_pipeline_context(tmp_path, visual_pipeline="video_loop")
        stage_09_video_rendering(ctx)

        assert ctx.loop_engine.render.call_count == 1
        call_kwargs = ctx.loop_engine.render.call_args[1]
        assert call_kwargs.get("stream_copy") is True
        assert ctx.multi_compositor.render.call_count == 0

    def test_stage_09_render_image_animation_unified_encoder(self, tmp_path):
        """Asserts that when visual_pipeline == 'image_animation', stage_09_video_rendering
        delegates to multi_compositor or unified encoder for atomic transcode."""
        from src.pipeline.stages.stage_09_render import stage_09_video_rendering

        ctx = _make_pipeline_context(tmp_path, visual_pipeline="image_animation")
        ctx.stream_copy_mode = False
        ctx.mux_subtitles = False

        stage_09_video_rendering(ctx)

        assert ctx.multi_compositor.render.call_count == 1
        assert ctx.loop_engine.render.call_count == 0
        assert ctx.visual_integrity_report["passed"] is True

    def test_stage_09_render_fallback_to_video_loop_on_failure(self, tmp_path):
        """Asserts that if image animation transcode raises an exception, stage 09 catches
        the error, logs an event, and falls back to catalog loop composition."""
        from src.pipeline.stages.stage_09_render import stage_09_video_rendering

        ctx = _make_pipeline_context(tmp_path, visual_pipeline="image_animation")
        ctx.stream_copy_mode = False
        ctx.multi_compositor.render.side_effect = RuntimeError("Transcode filtergraph crash")

        stage_09_video_rendering(ctx)

        assert ctx.loop_engine.render.call_count == 1
        call_kwargs = ctx.loop_engine.render.call_args[1]
        assert call_kwargs.get("stream_copy") is True
        assert ctx.visual_integrity_report["engine"] in ("loop", "loop_fallback")
        assert ctx.repository.record_artifact.call_count == 1

    def test_semaphore_concurrency_isolation(self, tmp_path):
        """Asserts short renders acquire _SHORT_RENDER_SEMAPHORE = 2 and long renders
        acquire _LONG_RENDER_SEMAPHORE = 1."""
        from unittest.mock import MagicMock, patch
        import src.pipeline.stages.stage_09_render as s9

        # Check semaphore values
        assert s9._SHORT_RENDER_SEMAPHORE._value <= 2
        assert s9._LONG_RENDER_SEMAPHORE._value <= 1

        # Short lane acquires _SHORT_RENDER_SEMAPHORE
        mock_short_sem = MagicMock()
        mock_short_sem.__enter__ = MagicMock(return_value=None)
        mock_short_sem.__exit__ = MagicMock(return_value=None)
        ctx_short = _make_pipeline_context(tmp_path, visual_pipeline="video_loop", is_long_lane=False)
        with patch.object(s9, "_SHORT_RENDER_SEMAPHORE", mock_short_sem):
            s9.stage_09_video_rendering(ctx_short)
            assert mock_short_sem.__enter__.call_count == 1

        # Long lane acquires _LONG_RENDER_SEMAPHORE
        mock_long_sem = MagicMock()
        mock_long_sem.__enter__ = MagicMock(return_value=None)
        mock_long_sem.__exit__ = MagicMock(return_value=None)
        ctx_long = _make_pipeline_context(tmp_path, visual_pipeline="video_loop", is_long_lane=True)
        with patch.object(s9, "_LONG_RENDER_SEMAPHORE", mock_long_sem):
            s9.stage_09_video_rendering(ctx_long)
            assert mock_long_sem.__enter__.call_count == 1

    def test_cli_visual_pipeline_override_integration(self):
        """Asserts that main.py CLI parser accepts --visual-pipeline override and validates choices."""
        from src.cli.parser import build_parser

        parser = build_parser()
        args = parser.parse_args(["run", "--lane", "horror-scp-shorts", "--visual-pipeline", "video_loop"])
        assert args.visual_pipeline == "video_loop"
        assert args.lane == "horror-scp-shorts"

        args2 = parser.parse_args(["run", "--lane", "drama-drama-shorts", "--visual-pipeline", "image_animation"])
        assert args2.visual_pipeline == "image_animation"

        with pytest.raises(SystemExit):
            parser.parse_args(["run", "--visual-pipeline", "invalid_webgl"])

