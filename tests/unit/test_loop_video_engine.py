"""
Unit test suite for LoopVideoEngine (src/media/loop_video_engine.py).
Tests category resolution, fallback logic, FFmpeg filter graph generation,
stream looping, sidechain ducking, dual format export (9:16 and 16:9),
optional subtitles, and compositor factory registration.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.media.interface import (
    BaseVideoCompositor,
    CompositorError,
    get_compositor,
)
from src.media.loop_engine import (
    LoopCompositionError,
    LoopVideoAssetError,
    LoopVideoCompositor,
    LoopVideoEngine,
    LoopVideoError,
)
from lib.ffmpeg import FFmpegCommandResult, FFmpegExecutionError, FFmpegTimeoutError


class TestLoopCategoryResolution(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.loops_dir = self.root_path / "loops"
        self.loops_dir.mkdir(parents=True, exist_ok=True)
        self.fb_dir = self.root_path / "backgrounds"
        self.fb_dir.mkdir(parents=True, exist_ok=True)
        self.fb_image = self.root_path / "background.jpg"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_scan_libraries_discovers_thematic_categories(self):
        """scan_libraries finds video files in thematic subdirectories."""
        cat_dir = self.loops_dir / "cosmic_horror"
        cat_dir.mkdir(parents=True, exist_ok=True)
        sample_vid = cat_dir / "nebula_loop.mp4"
        sample_vid.write_bytes(b"VIDEO_DATA")

        engine = LoopVideoEngine(loops_root_dir=self.loops_dir)
        library = engine.scan_libraries()

        self.assertIn("cosmic_horror", library)
        self.assertEqual(len(library["cosmic_horror"]), 1)
        self.assertEqual(library["cosmic_horror"][0].name, "nebula_loop.mp4")

    def test_normalize_category_name(self):
        """normalize_category handles case-insensitivity, hyphens, spaces, and empty inputs."""
        engine = LoopVideoEngine(loops_root_dir=self.loops_dir)
        self.assertEqual(engine.normalize_category("Cosmic-Horror"), "cosmic_horror")
        self.assertEqual(engine.normalize_category("DARK FOREST"), "dark_forest")
        self.assertEqual(engine.normalize_category("space_abyss"), "space_abyss")
        self.assertEqual(engine.normalize_category(""), "dark_ambient")
        self.assertEqual(engine.normalize_category(None), "dark_ambient")

    def test_resolve_exact_category_match(self):
        """resolve_loop_video returns video from requested category when present."""
        cat_dir = self.loops_dir / "dark_ambient"
        cat_dir.mkdir(parents=True, exist_ok=True)
        vid = cat_dir / "ambient_1.mp4"
        vid.write_bytes(b"VIDEO_DATA")

        engine = LoopVideoEngine(loops_root_dir=self.loops_dir)
        resolved = engine.resolve_loop_video(category="dark_ambient")
        self.assertEqual(resolved, vid)

    def test_fallback_to_other_category_when_requested_is_empty(self):
        """When requested category is missing/empty, fallbacks to another populated category."""
        (self.loops_dir / "cosmic_horror").mkdir(parents=True, exist_ok=True)  # empty
        monsters_dir = self.loops_dir / "monsters"
        monsters_dir.mkdir(parents=True, exist_ok=True)
        m_vid = monsters_dir / "monster_loop.mp4"
        m_vid.write_bytes(b"MONSTER_VIDEO")

        engine = LoopVideoEngine(loops_root_dir=self.loops_dir)
        resolved = engine.resolve_loop_video(category="cosmic_horror", allow_fallback=True)
        self.assertEqual(resolved, m_vid)

    def test_fallback_to_backgrounds_and_image(self):
        """When all loop categories are empty, fallback to backgrounds directory or fallback image."""
        fb_img = self.fb_dir / "horror_forest.jpg"
        fb_img.write_bytes(b"FALLBACK_IMAGE")

        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.fb_dir,
            default_fallback_image=self.fb_image,
        )
        resolved = engine.resolve_loop_video(category="space_abyss", allow_fallback=True)
        self.assertEqual(resolved, fb_img)

    def test_empty_asset_library_raises_asset_error(self):
        """When no video loops or fallback assets exist, LoopVideoAssetError is raised."""
        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.fb_dir,
            default_fallback_image=self.fb_image,
        )
        with self.assertRaises(LoopVideoAssetError):
            engine.resolve_loop_video(category="dark_forest", allow_fallback=True)

    def test_allow_fallback_false_raises_when_category_empty(self):
        """When allow_fallback=False and category is missing, raises LoopVideoAssetError immediately."""
        monsters_dir = self.loops_dir / "monsters"
        monsters_dir.mkdir(parents=True, exist_ok=True)
        (monsters_dir / "monster.mp4").write_bytes(b"DATA")

        engine = LoopVideoEngine(loops_root_dir=self.loops_dir)
        with self.assertRaises(LoopVideoAssetError):
            engine.resolve_loop_video(category="space_abyss", allow_fallback=False)



    def test_live_synth_attempted_before_background_fallback(self):
        """Empty catalog/category: live synth is attempted before background fallback."""
        fb_img = self.fb_dir / "horror_forest.jpg"
        fb_img.write_bytes(b"FALLBACK_IMAGE")
        synth_vid = self.root_path / "live_synth.mp4"
        synth_vid.write_bytes(b"SYNTH_VIDEO")

        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.fb_dir,
            default_fallback_image=self.fb_image,
        )
        with patch.object(engine, "_try_live_synthesize", return_value=synth_vid) as mock_synth:
            resolved = engine.resolve_loop_video(category="space_abyss", allow_fallback=True)
        mock_synth.assert_called_once()
        self.assertEqual(resolved, synth_vid)
        self.assertNotEqual(resolved, fb_img)

    def test_allow_fallback_false_skips_synth_and_background(self):
        """allow_fallback=False fails closed: no live synth inventing assets, no backgrounds."""
        fb_img = self.fb_dir / "should_not_use.jpg"
        fb_img.write_bytes(b"FALLBACK_IMAGE")
        synth_vid = self.root_path / "would_synth.mp4"
        synth_vid.write_bytes(b"SYNTH_VIDEO")

        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.fb_dir,
            default_fallback_image=self.fb_image,
        )
        with patch.object(engine, "_try_live_synthesize", return_value=synth_vid) as mock_synth:
            with self.assertRaises(LoopVideoAssetError):
                engine.resolve_loop_video(category="space_abyss", allow_fallback=False)
        mock_synth.assert_not_called()

class TestLoopStreamComposition(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.audio_path = self.root_path / "speech.wav"
        self.audio_path.write_bytes(b"RIFF" + b"\x00" * 40)
        self.video_path = self.root_path / "loop.mp4"
        self.video_path.write_bytes(b"MP4_DATA")
        self.output_path = self.root_path / "out.mp4"

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("src.media.loop_engine.run_ffmpeg")
    def test_stream_loop_flag_and_duration_sync(self, mock_run_ffmpeg):
        """FFmpeg command uses -stream_loop -1 for video input and syncs duration with -t."""
        mock_run_ffmpeg.return_value = FFmpegCommandResult(
            command=[], returncode=0, stdout="", stderr="", duration_sec=1.0
        )
        self.output_path.write_bytes(b"RENDERED_VIDEO")

        engine = LoopVideoEngine()
        out = engine.compose(
            audio_path=self.audio_path,
            output_video_path=self.output_path,
            video_loop_path=self.video_path,
            duration_sec=42.5,
        )

        self.assertEqual(out, str(self.output_path))
        cmd = mock_run_ffmpeg.call_args[0][0]

        # Verify -stream_loop -1 precedes video input
        vid_idx = cmd.index(str(self.video_path))
        self.assertEqual(cmd[vid_idx - 3], "-stream_loop")
        self.assertEqual(cmd[vid_idx - 2], "-1")
        self.assertEqual(cmd[vid_idx - 1], "-i")

        # Verify exact duration trim -t 42.500
        self.assertIn("-t", cmd)
        t_idx = cmd.index("-t")
        self.assertEqual(cmd[t_idx + 1], "42.500")

        # Verify video & audio encoding flags
        self.assertIn("-c:v", cmd)
        self.assertIn("libx264", cmd)
        self.assertIn("-pix_fmt", cmd)
        self.assertIn("yuv420p", cmd)
        self.assertIn("-c:a", cmd)
        self.assertIn("aac", cmd)
        self.assertIn("-movflags", cmd)
        self.assertIn("+faststart", cmd)

    @patch("src.media.loop_engine.run_ffmpeg")
    def test_image_fallback_uses_loop_flag(self, mock_run_ffmpeg):
        """Fallback static image background uses -loop 1 instead of -stream_loop -1."""
        mock_run_ffmpeg.return_value = FFmpegCommandResult(
            command=[], returncode=0, stdout="", stderr="", duration_sec=1.0
        )
        img_path = self.root_path / "bg.jpg"
        img_path.write_bytes(b"JPG_DATA")

        engine = LoopVideoEngine()
        engine.compose(
            audio_path=self.audio_path,
            output_video_path=self.output_path,
            video_loop_path=img_path,
            duration_sec=15.0,
        )

        cmd = mock_run_ffmpeg.call_args[0][0]
        img_idx = cmd.index(str(img_path))
        self.assertEqual(cmd[img_idx - 3], "-loop")
        self.assertEqual(cmd[img_idx - 2], "1")
        self.assertEqual(cmd[img_idx - 1], "-i")


    @patch("src.media.loop_engine.run_ffmpeg", side_effect=FFmpegExecutionError("FFmpeg error", returncode=1))
    def test_ffmpeg_execution_failure_raises_loop_composition_error(self, mock_run):
        """FFmpeg execution failure translates to LoopCompositionError."""
        engine = LoopVideoEngine()
        with self.assertRaises(LoopCompositionError):
            engine.compose(
                audio_path=self.audio_path,
                output_video_path=self.output_path,
                video_loop_path=self.video_path,
                duration_sec=10.0,
            )


class TestLoopAudioSidechainDucking(unittest.TestCase):
    def setUp(self):
        self.engine = LoopVideoEngine()

    def test_sidechain_ducking_filter_graph_structure(self):
        """Audio filter graph includes sidechaincompress with specified threshold, ratio, attack, release."""
        af = self.engine.build_audio_filter(
            has_music=True,
            music_volume=0.12,
            ducking_threshold=0.035,
            ducking_ratio=8.0,
            ducking_attack_ms=20.0,
            ducking_release_ms=350.0,
            master_loudness=True,
            target_lufs=-14.0,
        )

        self.assertIn("asplit=2[speech_sc][speech_mix]", af)
        self.assertIn("sidechaincompress=threshold=0.035:ratio=8.0:attack=20.0:release=350.0:makeup=1[music_ducked]", af)
        self.assertIn("[speech_mix][music_ducked]amix=inputs=2:duration=first:normalize=0[amixed]", af)
        self.assertIn("loudnorm=I=-14.0:TP=-1.5:LRA=11.0", af)
        self.assertIn("aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[aout]", af)

    def test_audio_filter_without_music(self):
        """When no background music is provided, passes narration directly through loudnorm."""
        af = self.engine.build_audio_filter(
            has_music=False,
            master_loudness=True,
            target_lufs=-14.0,
        )

        self.assertNotIn("sidechaincompress", af)
        self.assertNotIn("amix", af)
        self.assertIn("[1:a]aresample=48000,loudnorm=I=-14.0:TP=-1.5:LRA=11.0", af)
        self.assertIn("[aout]", af)


class TestLoopAspectRatioFormats(unittest.TestCase):
    def setUp(self):
        self.engine = LoopVideoEngine()

    def test_vertical_9_16_resolution_filter(self):
        """Vertical format generates scale and crop to 1080x1920."""
        vf = self.engine.build_video_filter(target_resolution=(1080, 1920), fps=30)
        self.assertIn("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", vf)
        self.assertIn("fps=30", vf)
        self.assertIn("setsar=1", vf)
        self.assertIn("format=yuv420p[vout]", vf)

    def test_horizontal_16_9_resolution_filter(self):
        """Horizontal format generates scale and crop to 1920x1080."""
        vf = self.engine.build_video_filter(target_resolution=(1920, 1080), fps=30)
        self.assertIn("scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080", vf)
        self.assertIn("fps=30", vf)
        self.assertIn("setsar=1", vf)
        self.assertIn("format=yuv420p[vout]", vf)

    def test_parse_resolution_variations(self):
        """parse_resolution supports orientation names, aspect ratio strings, and dimensions."""
        self.assertEqual(self.engine.parse_resolution("vertical"), (1080, 1920))
        self.assertEqual(self.engine.parse_resolution("horizontal"), (1920, 1080))
        self.assertEqual(self.engine.parse_resolution("9:16"), (1080, 1920))
        self.assertEqual(self.engine.parse_resolution("16:9"), (1920, 1080))
        self.assertEqual(self.engine.parse_resolution("short"), (1080, 1920))
        self.assertEqual(self.engine.parse_resolution("longform"), (1920, 1080))
        self.assertEqual(self.engine.parse_resolution((1080, 1920)), (1080, 1920))

    def test_invalid_resolution_raises_value_error(self):
        """Unsupported resolution string raises ValueError."""
        with self.assertRaises(ValueError):
            self.engine.parse_resolution("invalid_format")


class TestLoopSubtitlesConfiguration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.sub_path = self.root_path / "subtitles.ass"
        self.sub_path.write_text(
            "[Script Info]\nTitle: Test\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Active test cue\n",
            encoding="utf-8",
        )
        self.engine = LoopVideoEngine()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_subtitles_disabled_by_default(self):
        """Video filter does not contain subtitle filters when disabled."""
        vf = self.engine.build_video_filter(
            target_resolution=(1080, 1920),
            subtitle_path=self.sub_path,
            include_subtitles=False,
        )
        self.assertNotIn("ass=", vf)
        self.assertNotIn("subtitles=", vf)
        self.assertIn("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1,format=yuv420p[vout]", vf)

    def test_subtitles_enabled_adds_ass_filter(self):
        """When include_subtitles=True and subtitle file exists, burns subtitles."""
        vf = self.engine.build_video_filter(
            target_resolution=(1080, 1920),
            subtitle_path=self.sub_path,
            include_subtitles=True,
        )
        self.assertIn("ass=filename=", vf)
        self.assertIn("[vsubbed]", vf)
        self.assertIn("[vout]", vf)


class TestCompositorFactoryRegistrationAndRender(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.manifest_path = self.root_path / "scene_manifest.json"
        self.audio_path = self.root_path / "narration.wav"
        self.audio_path.write_bytes(b"AUDIO_DATA")
        self.out_video = self.root_path / "output.mp4"

        manifest_data = {
            "version": "1.0",
            "audio_path": str(self.audio_path),
            "duration_sec": 30.0,
            "category": "cosmic_horror",
            "orientation": "vertical",
        }
        self.manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_compositor_loop_factory(self):
        """get_compositor('loop') returns LoopVideoEngine instance."""
        comp = get_compositor("loop")
        self.assertIsInstance(comp, LoopVideoEngine)
        self.assertIsInstance(comp, BaseVideoCompositor)

    def test_get_compositor_loop_factory_falls_back_for_legacy_engine(self):
        """Legacy compositor names fall back to LoopVideoEngine (legacy paths removed)."""
        comp = get_compositor("ffmpeg_legacy")
        self.assertIsInstance(comp, LoopVideoEngine)
        comp_mc = get_compositor("motion_canvas")
        self.assertIsInstance(comp_mc, LoopVideoEngine)

    @patch("src.media.loop_engine.LoopVideoEngine.compose")
    def test_render_manifest_interface(self, mock_compose):
        """render() conforms to BaseVideoCompositor interface and returns metrics dictionary."""
        mock_compose.return_value = str(self.out_video)
        self.out_video.write_bytes(b"VIDEO_OUTPUT_DATA")

        engine = LoopVideoEngine()
        res = engine.render(
            manifest_path=self.manifest_path,
            output_video_path=self.out_video,
        )

        self.assertEqual(res["compositor"], "loop")
        self.assertIn("render_time_sec", res)
        self.assertEqual(res["output_path"], str(self.out_video))
        self.assertEqual(res["category"], "cosmic_horror")
        self.assertEqual(res["resolution"], "1080x1920")


if __name__ == "__main__":
    unittest.main()
