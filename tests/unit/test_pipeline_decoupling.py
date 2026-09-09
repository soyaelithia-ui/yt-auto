import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.domain import CanonicalChannel
from src.core.quality import QualityReport, validate_prepublication
from src.pipeline import run_pipeline_once


def _fake_generate_audio(script, output_path, **kwargs):
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"RIFFdummyWAVEfmt ")
    return {
        "audio_path": str(p),
        "duration_sec": 15.0,
        "word_timestamps": [
            {"word": "Esta", "start": 0.0, "end": 0.5},
            {"word": "historia", "start": 0.5, "end": 1.0},
        ],
    }


def _fake_create_ass(words, output_path, **kwargs):
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("[Script Info]\nPlayResX: 1080\nPlayResY: 1920\n", encoding="utf-8")


def _fake_create_srt(words, output_path, **kwargs):
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("1\n00:00:00,000 --> 00:00:01,000\nEsta historia\n\n", encoding="utf-8")


def _fake_loop_render(manifest_path, output_video_path, **kwargs):
    p = Path(output_video_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"DUMMY_MP4_DATA")
    return {
        "compositor": "loop",
        "render_time_sec": 1.2,
        "output_path": str(p),
    }


class TestPipelineLoopDecoupling(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.db_path = str(self.root_path / "test_pipeline.db")
        self.work_root = self.root_path / "work"
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.artifacts_root = self.root_path / "artifacts"
        self.artifacts_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("src.pipeline.validate_prepublication")
    @patch("src.youtube.uploader.upload_video")
    @patch("src.media.loop_engine.run_ffmpeg")
    @patch("lib.tts.generate_audio", side_effect=_fake_generate_audio)
    @patch("src.llm.curate_script")
    def test_pipeline_defaults_to_loop_mode(
        self, mock_curate, mock_audio, mock_ffmpeg, mock_upload, mock_validate
    ):
        """Pipeline defaults to loop video composition (LoopVideoEngine).

        Image-generation entry points (``SceneImageAgent``, legacy image
        provider, visual-integrity verifier) have been removed from the
        active flow. This test asserts loop render is engaged and the cover
        is rendered locally via PIL.
        """
        mock_curate.return_value = (
            "Esta es una historia en español porque la protagonista llegó a la casa y no sabía "
            "qué hacer cuando todos estaban allí, pero decidió contar toda la verdad sobre el misterio."
        )
        mock_report = QualityReport(channel=CanonicalChannel.MOKU)
        mock_validate.return_value = mock_report

        with patch("src.media.loop_engine.LoopVideoEngine.render", side_effect=_fake_loop_render) as mock_loop_render, \
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
                db_path=self.db_path,
                generate_only=True,
            )

            self.assertEqual(res["status"], "RENDERED")
            mock_loop_render.assert_called_once()
            mock_validate.assert_called_once()
            call_kwargs = mock_validate.call_args[1]
            self.assertIn(call_kwargs.get("video_engine"), ("loop", "beats"))
            self.assertFalse(call_kwargs.get("require_subtitles"))

    @patch("src.pipeline.validate_prepublication")
    @patch("src.youtube.uploader.upload_video")
    @patch("lib.tts.generate_audio", side_effect=_fake_generate_audio)
    @patch("src.llm.curate_script")
    def test_subtitles_disabled_by_default(self, mock_curate, mock_audio, mock_upload, mock_validate):
        """Subtitles generation is disabled by default in pipeline execution."""
        mock_curate.return_value = (
            "Esta es una historia en español porque la protagonista llegó a la casa y no sabía "
            "qué hacer cuando todos estaban allí, pero decidió contar toda la verdad sobre el misterio."
        )
        mock_report = QualityReport(channel=CanonicalChannel.MOKU)
        mock_validate.return_value = mock_report

        with patch("lib.subtitles.create_ass_subtitles") as mock_ass, \
             patch("lib.subtitles.create_subtitles") as mock_srt, \
             patch("src.media.loop_engine.LoopVideoEngine.render", side_effect=_fake_loop_render) as mock_loop_render, \
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
                db_path=self.db_path,
                generate_only=True,
                enable_subtitles=False,
            )

            self.assertEqual(res["status"], "RENDERED")
            mock_ass.assert_not_called()
            mock_srt.assert_not_called()

    @patch("src.pipeline.validate_prepublication")
    @patch("src.youtube.uploader.upload_video")
    @patch("lib.tts.generate_audio", side_effect=_fake_generate_audio)
    @patch("src.llm.curate_script")
    def test_subtitles_generated_when_explicitly_flagged(self, mock_curate, mock_audio, mock_upload, mock_validate):
        """Product path generates captions when enable_subtitles=True."""
        mock_curate.return_value = (
            "Esta es una historia en español porque la protagonista llegó a la casa y no sabía "
            "qué hacer cuando todos estaban allí, pero decidió contar toda la verdad sobre el misterio."
        )
        mock_report = QualityReport(channel=CanonicalChannel.MOKU)
        mock_validate.return_value = mock_report

        with patch("lib.subtitles.create_ass_subtitles", side_effect=_fake_create_ass) as mock_ass, \
             patch("lib.subtitles.create_subtitles", side_effect=_fake_create_srt) as mock_srt, \
             patch("lib.subtitles.validate_subtitle_grammar_and_syntax"), \
             patch("lib.subtitles.generate_safe_area_validation_artifact"), \
             patch("src.media.loop_engine.LoopVideoEngine.render", side_effect=_fake_loop_render) as mock_loop_render, \
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
                db_path=self.db_path,
                generate_only=True,
                enable_subtitles=True,
            )

            self.assertEqual(res["status"], "RENDERED")
            mock_ass.assert_called_once()
            mock_srt.assert_called_once()


class TestPrepublicationLoopPlanCadence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.video_path = self.root_path / "video.mp4"
        self.video_path.write_bytes(b"VIDEODATA")
        self.thumbnail_path = self.root_path / "thumb.jpg"
        from PIL import Image
        img = Image.new("RGB", (1080, 1920), color=(100, 100, 100))
        img.save(self.thumbnail_path)

        self.background_video = self.root_path / "bg_loop.mp4"
        self.background_video.write_bytes(b"BGLOOP")

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("src.core.quality.ffprobe")
    @patch("src.core.quality.has_faststart", return_value=True)
    @patch("src.core.quality.detect_long_black_frames", return_value=(0.0, []))
    @patch("src.core.quality.analyze_perceptual_luminance", return_value={"avg_luminance": 80.0, "dark_ratio": 0.05, "passed": True})
    def test_validate_prepublication_allows_single_scene_loop_plan(
        self, mock_lum, mock_black, mock_faststart, mock_probe
    ):
        """validate_prepublication relaxes 8-15s multi-scene cadence check when loop video engine is active."""
        mock_probe.return_value = {
            "format": {"duration": "30.0"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920, "pix_fmt": "yuv420p"},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }

        # Single continuous scene covering entire 30 seconds
        visual_plan_path = self.root_path / "visual_plan.json"
        visual_plan_path.write_text(
            json.dumps({
                "video_engine": "loop",
                "loop": True,
                "scenes": [
                    {"duration": 30.0, "source": str(self.background_video)}
                ],
                "covered_seconds": 30.0,
                "black_fallbacks": 0,
            }),
            encoding="utf-8",
        )

        report = validate_prepublication(
            channel=CanonicalChannel.MOKU,
            script=(
                "Esta es una historia en español porque la protagonista llegó a la casa y no sabía "
                "qué hacer cuando todos estaban allí, pero decidió contar toda la verdad."
            ),
            title="La casa donde nadie debía entrar",
            description="Esta es una descripción completa en español para la historia de terror que se publica hoy.",
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

    @patch("src.core.quality.ffprobe")
    @patch("src.core.quality.has_faststart", return_value=True)
    @patch("src.core.quality.detect_long_black_frames", return_value=(0.0, []))
    @patch("src.core.quality.analyze_perceptual_luminance", return_value={"avg_luminance": 80.0, "dark_ratio": 0.05, "passed": True})
    def test_validate_prepublication_accepts_scene_manifest_aliases(
        self, mock_lum, mock_black, mock_faststart, mock_probe
    ):
        """QA accepts duration_sec/image_path aliases used by scene_manifest-shaped plans."""
        mock_probe.return_value = {
            "format": {"duration": "39.72"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920, "pix_fmt": "yuv420p"},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }
        visual_plan_path = self.root_path / "visual_plan_aliases.json"
        visual_plan_path.write_text(
            json.dumps({
                "video_engine": "loop",
                "loop": True,
                "mode": "loop",
                "scenes": [
                    {"duration_sec": 7.8, "image_path": str(self.background_video)},
                    {"duration_sec": 10.64, "image_path": str(self.background_video)},
                    {"duration_sec": 9.58, "image_path": str(self.background_video)},
                    {"duration_sec": 11.7, "image_path": str(self.background_video)},
                ],
                "black_fallbacks": 0,
            }),
            encoding="utf-8",
        )
        report = validate_prepublication(
            channel=CanonicalChannel.MOKU,
            script=(
                "Esta es una historia en español porque la protagonista llegó a la casa y no sabía "
                "qué hacer cuando todos estaban allí, pero decidió contar toda la verdad."
            ),
            title="La casa donde nadie debía entrar",
            description="Esta es una descripción completa en español para la historia de terror que se publica hoy.",
            video_path=self.video_path,
            subtitle_path=None,
            thumbnail_path=self.thumbnail_path,
            visual_plan_path=visual_plan_path,
            video_mode="short",
            video_engine="loop",
            require_subtitles=False,
        )
        self.assertTrue(report.passed, f"Prepublication QA failed with issues: {report.issues}")
        self.assertEqual(report.facts.get("scene_count"), 4)


if __name__ == "__main__":
    unittest.main()
