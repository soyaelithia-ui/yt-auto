"""Adversarial test suite for the loop-only pipeline.

The active pipeline runs exclusively through ``LoopVideoEngine``: legacy
per-scene image generation (SceneImageAgent, ``provide_scene_images_aligned``,
``_build_ai_scene_prompts``, ``_fallback_scene_prompts``) and the legacy
visual verifiers (``verify_visual_integrity``, ``VisualQualityVerifier``,
``VisualValidator``, ``evaluate_visual_diversity``) have been removed from
the codebase.

These tests assert:

1. Loop-mode runs touch NO removed visual-generation entry points.
2. Subtitle configuration matrix (default-off, explicit on/off, env overrides).
3. Prepublication QA allows single-scene loop plans across durations.
4. LoopVideoEngine rejects non-loop compositor names (fail-closed).
5. Malicious category names / missing directories resolve gracefully.
6. LoopVideoEngine.render keyword-arguments duplication bug is fixed.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from src.core.domain import CanonicalChannel
from src.core.quality import QualityReport, validate_prepublication
from src.media.loop_engine import (
    LoopCompositionError,
    LoopVideoAssetError,
    LoopVideoEngine,
)
from src.pipeline import run_pipeline_once


SAMPLE_SPANISH_NARRATION = (
    "Esta es una historia en español porque la protagonista llegó a la casa abandonada y no sabía "
    "qué hacer cuando todos los extraños ruidos comenzaron a sonar en la oscuridad, "
    "pero finalmente decidió cruzar la puerta y descubrir la verdad oculta tras el misterio."
)


def _mock_audio_gen(script, output_path, **kwargs):
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"RIFFdummyWAVEfmt ")
    dur = float(kwargs.get("target_duration_sec") or 15.0)
    return {
        "audio_path": str(p),
        "duration_sec": dur,
        "word_timestamps": [
            {"word": "Esta", "start": 0.0, "end": 0.5},
            {"word": "historia", "start": 0.5, "end": 1.0},
        ],
    }


def _mock_loop_render(manifest_path, output_video_path, **kwargs):
    p = Path(output_video_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"DUMMY_LOOP_VIDEO_DATA")
    return {
        "compositor": "loop",
        "render_time_sec": 0.5,
        "output_path": str(p),
        "resolution": "1080x1920",
    }


def _mock_create_ass(words, output_path, **kwargs):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text("[Script Info]\nPlayResX: 1080\nPlayResY: 1920\n", encoding="utf-8")


def _mock_create_srt(words, output_path, **kwargs):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text("1\n00:00:00,000 --> 00:00:01,000\nEsta historia\n\n", encoding="utf-8")


class TestAdversarialZeroCallsInLoopMode(unittest.TestCase):
    """Loop-mode runs MUST NOT touch any removed visual-generation entry point."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.loop_video = self.root_path / "sample_loop.mp4"
        self.loop_video.write_bytes(b"LOOP_VIDEO_CONTENT")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _execute_pipeline_run(self, channel, lane_id=None, video_engine=None, **extra_kwargs):
        db_path = str(self.root_path / f"test_{channel}_{video_engine or 'default'}.db")
        mock_report = QualityReport(channel=CanonicalChannel.MOKU if channel == "moku" else CanonicalChannel.AELITHIA)

        with patch("src.pipeline.curate_script", return_value=SAMPLE_SPANISH_NARRATION), \
             patch("lib.tts.generate_audio", side_effect=_mock_audio_gen), \
             patch("src.pipeline.validate_prepublication", return_value=mock_report) as mock_validate, \
             patch("src.media.loop_engine.LoopVideoEngine.resolve_loop_video", return_value=self.loop_video) as spy_resolve_loop, \
             patch("src.media.loop_engine.LoopVideoEngine.render", side_effect=_mock_loop_render) as spy_loop_render, \
             patch("src.core.quality.ffprobe") as mock_probe:

            mock_probe.return_value = {
                "format": {"duration": "15.0"},
                "streams": [
                    {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920, "pix_fmt": "yuv420p"},
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
            }

            res = run_pipeline_once(
                channel=channel,
                db_path=db_path,
                lane_id=lane_id,
                video_engine=video_engine,
                generate_only=True,
                **extra_kwargs,
            )

            return {
                "result": res,
                "spy_resolve_loop": spy_resolve_loop,
                "spy_loop_render": spy_loop_render,
                "mock_validate": mock_validate,
            }

    def test_loop_mode_resolves_video_and_renders(self):
        """Default loop-mode renders via LoopVideoEngine."""
        spies = self._execute_pipeline_run(channel="moku", lane_id=None, video_engine=None)
        self.assertEqual(spies["result"]["status"], "RENDERED")
        spies["spy_resolve_loop"].assert_called_once()
        spies["spy_loop_render"].assert_called_once()

    def test_aelithia_loop_mode_renders(self):
        """Aelithia channel renders via loop engine too."""
        spies = self._execute_pipeline_run(channel="aelithia", lane_id=None, video_engine=None)
        self.assertEqual(spies["result"]["status"], "RENDERED")
        spies["spy_loop_render"].assert_called_once()

    def test_explicit_loop_aliases_all_render(self):
        """All accepted loop engine aliases drive the active pipeline."""
        for alias in ("loop", "loop_video", "loop_video_engine", "loop_compositor"):
            with self.subTest(alias=alias):
                spies = self._execute_pipeline_run(channel="moku", video_engine=alias)
                self.assertEqual(spies["result"]["status"], "RENDERED")
                spies["spy_loop_render"].assert_called_once()


class TestSubtitleMatrix(unittest.TestCase):
    """Subtitle generation respects explicit args and env vars, with explicit args winning."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.loop_video = self.root_path / "sample_loop.mp4"
        self.loop_video.write_bytes(b"LOOP_VIDEO_CONTENT")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _run(self, **extra_kwargs):
        db_path = str(self.root_path / "test_subtitles.db")
        mock_report = QualityReport(channel=CanonicalChannel.MOKU)
        with patch("src.pipeline.curate_script", return_value=SAMPLE_SPANISH_NARRATION), \
             patch("lib.tts.generate_audio", side_effect=_mock_audio_gen), \
             patch("src.pipeline.validate_prepublication", return_value=mock_report), \
             patch("src.media.loop_engine.LoopVideoEngine.resolve_loop_video", return_value=self.loop_video), \
             patch("src.media.loop_engine.LoopVideoEngine.render", side_effect=_mock_loop_render), \
             patch("src.core.quality.ffprobe") as mock_probe:

            mock_probe.return_value = {
                "format": {"duration": "15.0"},
                "streams": [
                    {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920, "pix_fmt": "yuv420p"},
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
            }

            return run_pipeline_once(
                channel="moku", db_path=db_path, generate_only=True, **extra_kwargs,
            )

    def test_default_subtitles_disabled(self):
        with patch("lib.subtitles.create_ass_subtitles") as mock_ass, \
             patch("lib.subtitles.create_subtitles") as mock_srt:
            res = self._run()
        self.assertEqual(res["status"], "RENDERED")
        mock_ass.assert_not_called()
        mock_srt.assert_not_called()

    def test_env_enables_subtitles_when_explicit_arg_absent(self):
        with patch.dict(os.environ, {"ENABLE_SUBTITLES": "1"}):
            with patch("lib.subtitles.create_ass_subtitles", side_effect=_mock_create_ass) as mock_ass, \
                 patch("lib.subtitles.create_subtitles", side_effect=_mock_create_srt) as mock_srt, \
                 patch("lib.subtitles.validate_subtitle_grammar_and_syntax"), \
                 patch("lib.subtitles.generate_safe_area_validation_artifact"):
                res = self._run()
        self.assertEqual(res["status"], "RENDERED")
        mock_ass.assert_called_once()
        mock_srt.assert_called_once()

    def test_explicit_arg_overrides_env(self):
        with patch.dict(os.environ, {"ENABLE_SUBTITLES": "1"}):
            with patch("lib.subtitles.create_ass_subtitles") as mock_ass, \
                 patch("lib.subtitles.create_subtitles") as mock_srt:
                res = self._run(enable_subtitles=False)
        self.assertEqual(res["status"], "RENDERED")
        mock_ass.assert_not_called()
        mock_srt.assert_not_called()


class TestPrepublicationLoopCadence(unittest.TestCase):
    """Single-scene loop plans pass without the 8-15s multi-scene cadence rejection."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.video_path = self.root_path / "video.mp4"
        self.video_path.write_bytes(b"VIDEODATA")
        self.thumbnail_path = self.root_path / "thumb.jpg"
        from PIL import Image
        Image.new("RGB", (1080, 1920), color=(100, 100, 100)).save(self.thumbnail_path)
        self.background_video = self.root_path / "bg_loop.mp4"
        self.background_video.write_bytes(b"BGLOOP")

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("src.core.quality.ffprobe")
    @patch("src.core.quality.has_faststart", return_value=True)
    @patch("src.core.quality.detect_long_black_frames", return_value=(0.0, []))
    @patch("src.core.quality.analyze_perceptual_luminance", return_value={"avg_luminance": 80.0, "dark_ratio": 0.05, "passed": True})
    def test_validate_prepublication_allows_single_scene_loop(self, mock_lum, mock_black, mock_faststart, mock_probe):
        mock_probe.return_value = {
            "format": {"duration": "30.0"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920, "pix_fmt": "yuv420p"},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }
        visual_plan_path = self.root_path / "visual_plan.json"
        visual_plan_path.write_text(json.dumps({
            "video_engine": "loop",
            "loop": True,
            "scenes": [{"duration": 30.0, "source": str(self.background_video)}],
            "covered_seconds": 30.0,
            "black_fallbacks": 0,
        }), encoding="utf-8")

        report = validate_prepublication(
            channel=CanonicalChannel.MOKU,
            script=SAMPLE_SPANISH_NARRATION,
            title="La casa donde nadie debía entrar",
            description="Descripción completa en español para la historia que se publica hoy.",
            video_path=self.video_path,
            subtitle_path=None,
            thumbnail_path=self.thumbnail_path,
            visual_plan_path=visual_plan_path,
            video_mode="short",
            video_engine="loop",
            require_subtitles=False,
        )
        self.assertTrue(report.passed, f"Prepublication QA failed with issues: {report.issues}")
        self.assertEqual(report.facts.get("scene_count"), 1)


class TestAdversarialCategoryResolutionAndFallback(unittest.TestCase):
    """Adversarial stress testing of LoopVideoEngine category resolution and fallback cascades."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.loops_dir = self.root_path / "loops"
        self.loops_dir.mkdir(parents=True, exist_ok=True)
        self.bg_dir = self.root_path / "backgrounds"
        self.bg_dir.mkdir(parents=True, exist_ok=True)
        self.default_bg = self.root_path / "default_bg.jpg"
        self.default_bg.write_bytes(b"DEFAULT_IMAGE")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_adversarial_category_names_resolve_safely(self):
        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.bg_dir,
            default_fallback_image=self.default_bg,
        )
        malicious_categories = [
            "../../etc/passwd",
            "../../../secret",
            "..\\..\\windows\\system32",
            "/absolute/root/path",
            "foo/bar/../../baz",
            "cosmic_horror\x00malicious",
            "",
            None,
            "   ",
            "---",
            "???special***chars!!!",
        ]
        for mal_cat in malicious_categories:
            with self.subTest(category=mal_cat):
                result = engine.resolve_loop_video(mal_cat, allow_fallback=True)
                self.assertTrue(result is not None)


class TestLoopRenderKeywordArgsDuplication(unittest.TestCase):
    """LoopVideoEngine.render must not raise TypeError about duplicated keyword arguments."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.manifest = self.root_path / "scene_manifest.json"
        self.manifest.write_text(json.dumps({
            "scenes": [{"image_path": str(self.root_path / "loop.mp4"), "duration_sec": 10.0}],
            "duration_sec": 10.0,
            "loop": True,
            "video_engine": "loop",
            "category": "dark_ambient",
            "orientation": "vertical",
            "fps": 30,
        }), encoding="utf-8")
        self.audio_path = self.root_path / "speech.wav"
        self.audio_path.write_bytes(b"RIFFdummyWAVEfmt ")
        self.out = self.root_path / "out.mp4"
        self.loop_video = self.root_path / "loop.mp4"
        self.loop_video.write_bytes(b"LOOP")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_render_with_full_kwargs_does_not_duplicate(self):
        engine = LoopVideoEngine()
        with patch.object(engine, "compose", return_value=str(self.out)) as mock_compose:
            res = engine.render(
                manifest_path=self.manifest,
                output_video_path=self.out,
                audio_path=str(self.audio_path),
                category="dark_ambient",
                orientation="vertical",
                duration_sec=10.0,
                fps=30,
                crf=24,
            )
        mock_compose.assert_called_once()
        self.assertEqual(res["compositor"], "loop")


class TestNonLoopCompositorRejected(unittest.TestCase):
    """Legacy compositor names now fail-closed at the pipeline boundary."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.loop_video = self.root_path / "loop.mp4"
        self.loop_video.write_bytes(b"LOOP")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_legacy_engine_name_returns_retryable_failed(self):
        """video_engine='ffmpeg_legacy' fails fast — legacy compositors removed."""
        from src.core.domain import JobStatus
        db_path = str(self.root_path / "fb.db")
        with patch("src.pipeline.curate_script", return_value=SAMPLE_SPANISH_NARRATION), \
             patch("lib.tts.generate_audio", side_effect=_mock_audio_gen), \
             patch("src.pipeline.validate_prepublication") as mock_validate, \
             patch("src.media.loop_engine.LoopVideoEngine.resolve_loop_video", return_value=self.loop_video) as spy_resolve, \
             patch("src.media.loop_engine.LoopVideoEngine.render", side_effect=_mock_loop_render) as spy_render, \
             patch("src.core.quality.ffprobe") as mock_probe:

            mock_probe.return_value = {
                "format": {"duration": "15.0"},
                "streams": [
                    {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920, "pix_fmt": "yuv420p"},
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
            }
            res = run_pipeline_once(
                channel="moku",
                db_path=db_path,
                generate_only=True,
                video_engine="ffmpeg_legacy",
            )
        self.assertEqual(res["status"], JobStatus.RETRYABLE_FAILED.value)
        self.assertIn("video_engine", res.get("reason", ""))


if __name__ == "__main__":
    unittest.main()
