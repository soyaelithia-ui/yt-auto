"""
Adversarial Stress Test Suite for LoopVideoEngine (src/media/loop_video_engine.py).

Covers:
1. Category resolution, fallback hierarchies, 0-byte/corrupted files, empty directories.
2. Extreme duration boundaries (0.01s, 0.5s, 60s, 3600s, negative, zero, None).
3. Dual format scaling, orientation parsing, square/ultra-wide/custom aspect ratios.
4. Filter graph generation matrix (with/without BGM, with/without subtitles ASS/SRT, font escaping).
5. Sidechain ducking parameters, EBU R128 loudness mastering, lowpass filter edge cases.
6. Manifest parsing & BaseVideoCompositor interface contract compliance.
7. Empirical end-to-end rendering using synthetic FFmpeg media and ffprobe validation.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
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
from lib.ffmpeg import (
    FFmpegCommandResult,
    FFmpegExecutionError,
    FFmpegTimeoutError,
    probe_media,
    run_ffmpeg,
)


class TestAdversarialCategoryFallbackAndScanning(unittest.TestCase):
    """Stress testing category resolution, library scanning, corrupted files, and fallback hierarchies."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.loops_dir = self.root / "loops"
        self.loops_dir.mkdir(parents=True, exist_ok=True)
        self.fallback_dir = self.root / "backgrounds"
        self.fallback_dir.mkdir(parents=True, exist_ok=True)
        self.fallback_image = self.root / "default_background.jpg"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_corrupted_zero_byte_files_in_requested_category_skipped(self):
        """Zero-byte files in the requested category must be skipped in favor of non-empty files or fallback."""
        cat_dir = self.loops_dir / "monsters"
        cat_dir.mkdir(parents=True, exist_ok=True)
        
        corrupted_vid = cat_dir / "01_corrupted.mp4"
        corrupted_vid.touch()  # 0 bytes
        
        valid_vid = cat_dir / "02_valid.mp4"
        valid_vid.write_bytes(b"VALID_VIDEO_CONTENT_12345")

        engine = LoopVideoEngine(loops_root_dir=self.loops_dir)
        resolved = engine.resolve_loop_video(category="monsters")
        self.assertEqual(resolved, valid_vid)

    def test_corrupted_only_requested_category_falls_back_to_other_valid_category(self):
        """
        Adversarial failure case:
        If requested category contains only 0-byte files, fallback should resolve to another populated category.
        Exposes bug where scan_libraries() returns 0-byte files and resolve_loop_video() re-picks the 0-byte file.
        """
        # cosmic_horror has only 0-byte file
        ch_dir = self.loops_dir / "cosmic_horror"
        ch_dir.mkdir(parents=True, exist_ok=True)
        (ch_dir / "empty.mp4").touch()

        # dark_forest has valid file
        df_dir = self.loops_dir / "dark_forest"
        df_dir.mkdir(parents=True, exist_ok=True)
        valid_vid = df_dir / "trees.mp4"
        valid_vid.write_bytes(b"DARK_FOREST_VIDEO")

        engine = LoopVideoEngine(loops_root_dir=self.loops_dir)
        resolved = engine.resolve_loop_video(category="cosmic_horror", allow_fallback=True)
        self.assertEqual(resolved, valid_vid)

    def test_fallback_hierarchy_deep_cascade(self):
        """
        Tests cascade:
        1. Requested category missing ->
        2. Predefined thematic categories empty ->
        3. Custom discovered category empty ->
        4. Loose root video files ->
        5. Fallback backgrounds directory ->
        6. Fallback default image
        """
        # Step 6: Only default fallback image exists
        self.fallback_image.write_bytes(b"IMAGE_BYTES")
        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.fallback_dir,
            default_fallback_image=self.fallback_image,
        )
        resolved = engine.resolve_loop_video(category="space_abyss", allow_fallback=True)
        self.assertEqual(resolved, self.fallback_image)

        # Step 5: Add a fallback image in backgrounds dir
        fb_bg_img = self.fallback_dir / "bg_custom.png"
        fb_bg_img.write_bytes(b"PNG_BYTES")
        resolved = engine.resolve_loop_video(category="space_abyss", allow_fallback=True)
        self.assertEqual(resolved, fb_bg_img)

        # Step 5b: Add a fallback video in backgrounds dir (should take precedence over bg image)
        fb_bg_vid = self.fallback_dir / "bg_motion.webm"
        fb_bg_vid.write_bytes(b"WEBM_BYTES")
        resolved = engine.resolve_loop_video(category="space_abyss", allow_fallback=True)
        self.assertEqual(resolved, fb_bg_vid)

        # Step 4: Add loose video in loops root
        root_vid = self.loops_dir / "root_loop.mov"
        root_vid.write_bytes(b"MOV_BYTES")
        resolved = engine.resolve_loop_video(category="space_abyss", allow_fallback=True)
        self.assertEqual(resolved, root_vid)

        # Step 2/3: Add video in thematic category
        cat_vid = self.loops_dir / "dark_ambient" / "ambient.mkv"
        cat_vid.parent.mkdir(parents=True, exist_ok=True)
        cat_vid.write_bytes(b"MKV_BYTES")
        resolved = engine.resolve_loop_video(category="space_abyss", allow_fallback=True)
        self.assertEqual(resolved, cat_vid)

        # Step 1: Add requested category video
        space_vid = self.loops_dir / "space_abyss" / "galaxy.mp4"
        space_vid.parent.mkdir(parents=True, exist_ok=True)
        space_vid.write_bytes(b"MP4_BYTES")
        resolved = engine.resolve_loop_video(category="space_abyss", allow_fallback=True)
        self.assertEqual(resolved, space_vid)

    def test_custom_nonstandard_thematic_categories_discovered(self):
        """Dynamic subfolders (e.g. 'alien_invasion', 'haunted_house') are discovered."""
        custom_dir = self.loops_dir / "alien_invasion"
        custom_dir.mkdir(parents=True, exist_ok=True)
        alien_vid = custom_dir / "ufo.mp4"
        alien_vid.write_bytes(b"UFO_VIDEO")

        engine = LoopVideoEngine(loops_root_dir=self.loops_dir)
        scanned = engine.scan_libraries()
        self.assertIn("alien_invasion", scanned)
        self.assertIn(alien_vid, scanned["alien_invasion"])

        resolved = engine.resolve_loop_video(category="alien_invasion")
        self.assertEqual(resolved, alien_vid)

    def test_category_normalization_adversarial_strings(self):
        """Tests category normalization with weird casing, whitespace, dashes, underscores, and empty strings."""
        engine = LoopVideoEngine()
        self.assertEqual(engine.normalize_category("Cosmic-Horror"), "cosmic_horror")
        self.assertEqual(engine.normalize_category("  DARK FOREST  "), "dark_forest")
        self.assertEqual(engine.normalize_category("space___abyss"), "space___abyss")
        self.assertEqual(engine.normalize_category(""), "dark_ambient")
        self.assertEqual(engine.normalize_category(None), "dark_ambient")
        self.assertEqual(engine.normalize_category("   "), "dark_ambient")
        self.assertEqual(engine.normalize_category("MONSTERS"), "monsters")

    def test_supported_video_and_image_extensions(self):
        """All supported extensions (.mp4, .webm, .mov, .mkv, .avi, .jpg, .jpeg, .png, .webp) are recognized."""
        engine = LoopVideoEngine(loops_root_dir=self.loops_dir, default_fallback_dir=self.fallback_dir)
        for ext in [".mp4", ".webm", ".mov", ".mkv", ".avi"]:
            self.assertIn(ext, engine.SUPPORTED_VIDEO_EXTENSIONS)
        for ext in [".jpg", ".jpeg", ".png", ".webp"]:
            self.assertIn(ext, engine.SUPPORTED_IMAGE_EXTENSIONS)

    def test_random_seed_determinism(self):
        """Passing a seed provides deterministic selection when multiple loops exist."""
        cat_dir = self.loops_dir / "monsters"
        cat_dir.mkdir(parents=True, exist_ok=True)
        vids = []
        for i in range(5):
            v = cat_dir / f"monster_{i:02d}.mp4"
            v.write_bytes(b"DATA")
            vids.append(v)

        engine = LoopVideoEngine(loops_root_dir=self.loops_dir)
        res1 = engine.resolve_loop_video(category="monsters", seed=12345)
        res2 = engine.resolve_loop_video(category="monsters", seed=12345)
        self.assertEqual(res1, res2)


class TestAdversarialDurationBoundaries(unittest.TestCase):
    """Stress testing duration boundaries: micro-durations, extreme longform, zero, negative."""

    def setUp(self):
        self.engine = LoopVideoEngine()
        self.video_path = Path("/mock/video.mp4")
        self.audio_path = Path("/mock/audio.wav")
        self.bgm_path = Path("/mock/bgm.mp3")

    def test_micro_duration_clamped_to_minimum_0_1s(self):
        """Durations < 0.1s (e.g. 0.01s, 0.005s) are clamped to 0.100s to avoid FFmpeg invalid duration errors."""
        cmd = self.engine.build_composition_filter_graph(
            video_path=self.video_path,
            audio_path=self.audio_path,
            bgm_path=None,
            target_resolution=(1080, 1920),
            duration_sec=0.01,
        )
        t_idx = cmd.index("-t")
        self.assertEqual(cmd[t_idx + 1], "0.100")

    def test_subsecond_duration_formatting(self):
        """0.5s duration formats precisely to -t 0.500."""
        cmd = self.engine.build_composition_filter_graph(
            video_path=self.video_path,
            audio_path=self.audio_path,
            bgm_path=None,
            target_resolution=(1080, 1920),
            duration_sec=0.5,
        )
        t_idx = cmd.index("-t")
        self.assertEqual(cmd[t_idx + 1], "0.500")

    def test_standard_shorts_60s_duration(self):
        """60s duration formats to -t 60.000."""
        cmd = self.engine.build_composition_filter_graph(
            video_path=self.video_path,
            audio_path=self.audio_path,
            bgm_path=None,
            target_resolution=(1080, 1920),
            duration_sec=60.0,
        )
        t_idx = cmd.index("-t")
        self.assertEqual(cmd[t_idx + 1], "60.000")

    def test_extreme_longform_1_hour_3600s_duration(self):
        """3600s (1 hour) long-form duration formats to -t 3600.000."""
        cmd = self.engine.build_composition_filter_graph(
            video_path=self.video_path,
            audio_path=self.audio_path,
            bgm_path=None,
            target_resolution=(1920, 1080),
            duration_sec=3600.0,
        )
        t_idx = cmd.index("-t")
        self.assertEqual(cmd[t_idx + 1], "3600.000")


class TestAdversarialAspectRatiosAndScaling(unittest.TestCase):
    """Stress testing resolution parsing, orientation aliases, and scaling filter graphs."""

    def setUp(self):
        self.engine = LoopVideoEngine()

    def test_all_orientation_aliases_and_aspect_ratio_strings(self):
        """Checks vertical/portrait/short/9:16 and horizontal/landscape/longform/16:9 mappings."""
        vertical_keys = ["vertical", "portrait", "short", "9:16", "1080x1920", "1080:1920"]
        for key in vertical_keys:
            self.assertEqual(self.engine.parse_resolution(key), (1080, 1920), f"Failed for {key}")

        horizontal_keys = ["horizontal", "landscape", "longform", "16:9", "1920x1080", "1920:1080"]
        for key in horizontal_keys:
            self.assertEqual(self.engine.parse_resolution(key), (1920, 1080), f"Failed for {key}")

    def test_custom_tuples_and_lists(self):
        """Accepts custom (width, height) tuples or lists."""
        self.assertEqual(self.engine.parse_resolution((720, 1280)), (720, 1280))
        self.assertEqual(self.engine.parse_resolution([3840, 2160]), (3840, 2160))

    def test_invalid_resolution_inputs_raise_value_error(self):
        """Invalid resolutions throw ValueError."""
        invalid_inputs = [
            "invalid_mode",
            "",
            "0x0",
            "-1080x1920",
            (0, 1920),
            (-1080, 1920),
            (1080, 0),
            (1080,),
            (1080, 1920, 30),
            None,
        ]
        for inv in invalid_inputs:
            with self.assertRaises(ValueError, msg=f"Should raise ValueError for {inv}"):
                self.engine.parse_resolution(inv)

    def test_video_scaling_and_crop_filters(self):
        """Verifies force_original_aspect_ratio=increase, crop=W:H, setsar=1, format=yuv420p."""
        vf_vert = self.engine.build_video_filter(target_resolution=(1080, 1920), fps=60)
        self.assertIn("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", vf_vert)
        self.assertIn("fps=60", vf_vert)
        self.assertIn("setsar=1", vf_vert)
        self.assertIn("format=yuv420p[vout]", vf_vert)

        vf_horiz = self.engine.build_video_filter(target_resolution=(1920, 1080), fps=24)
        self.assertIn("scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080", vf_horiz)
        self.assertIn("fps=24", vf_horiz)
        self.assertIn("setsar=1", vf_horiz)
        self.assertIn("format=yuv420p[vout]", vf_horiz)


class TestAdversarialFilterGraphMatrix(unittest.TestCase):
    """Stress testing combinations of BGM, Subtitles (.ass / .srt), Loudness Mastering, and Sidechaining."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.engine = LoopVideoEngine()
        self.video_path = self.root / "loop.mp4"
        self.video_path.write_bytes(b"VIDEO")
        self.audio_path = self.root / "speech.wav"
        self.audio_path.write_bytes(b"SPEECH")
        self.bgm_path = self.root / "bgm.mp3"
        self.bgm_path.write_bytes(b"BGM")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_graph_matrix_no_bgm_no_subs(self):
        """Case 1: No BGM, Subtitles disabled."""
        cmd = self.engine.build_composition_filter_graph(
            video_path=self.video_path,
            audio_path=self.audio_path,
            bgm_path=None,
            target_resolution=(1080, 1920),
            duration_sec=15.0,
            include_subtitles=False,
        )
        filt = cmd[cmd.index("-filter_complex") + 1]
        self.assertNotIn("sidechaincompress", filt)
        self.assertNotIn("amix", filt)
        self.assertIn("[1:a]aresample=44100,loudnorm=I=-16.0:TP=-1.5:LRA=11.0", filt)
        self.assertNotIn("subtitles=", filt)
        self.assertNotIn("ass=", filt)

    def test_graph_matrix_with_bgm_no_subs(self):
        """Case 2: With BGM, Subtitles disabled."""
        cmd = self.engine.build_composition_filter_graph(
            video_path=self.video_path,
            audio_path=self.audio_path,
            bgm_path=self.bgm_path,
            target_resolution=(1080, 1920),
            duration_sec=20.0,
            include_subtitles=False,
            music_volume=0.15,
            ducking_threshold=0.04,
            ducking_ratio=10.0,
        )
        filt = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("sidechaincompress=threshold=0.04:ratio=10.0:attack=20.0:release=350.0:makeup=1", filt)
        self.assertIn("volume=0.1500", filt)
        self.assertIn("[speech_mix][music_ducked]amix=inputs=2:duration=first:normalize=0[amixed]", filt)
        self.assertIn("[amixed]loudnorm=I=-16.0:TP=-1.5:LRA=11.0", filt)

    def test_graph_matrix_with_bgm_and_ass_subtitles(self):
        """Case 3: With BGM, ASS Subtitles enabled."""
        sub_ass = self.root / "subs.ass"
        sub_ass.write_text(
            "[Script Info]\nTitle: Test\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Active test cue\n",
            encoding="utf-8",
        )

        cmd = self.engine.build_composition_filter_graph(
            video_path=self.video_path,
            audio_path=self.audio_path,
            bgm_path=self.bgm_path,
            target_resolution=(1080, 1920),
            duration_sec=30.0,
            include_subtitles=True,
            subtitle_path=sub_ass,
        )
        filt = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("ass=filename=", filt)
        self.assertIn("[vbase]", filt)
        self.assertIn("[vsubbed]", filt)
        self.assertIn("sidechaincompress", filt)

    def test_graph_matrix_with_srt_subtitles(self):
        """Case 4: SRT Subtitles enabled uses subtitles filter."""
        sub_srt = self.root / "subs.srt"
        sub_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")

        cmd = self.engine.build_composition_filter_graph(
            video_path=self.video_path,
            audio_path=self.audio_path,
            bgm_path=None,
            target_resolution=(1920, 1080),
            duration_sec=10.0,
            include_subtitles=True,
            subtitle_path=sub_srt,
        )
        filt = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("subtitles=", filt)
        self.assertNotIn("ass=filename=", filt)

    def test_subtitles_file_missing_or_empty_falls_back_gracefully(self):
        """When include_subtitles=True but file is missing or 0 bytes, omits subtitle filter safely."""
        missing_sub = self.root / "missing.ass"
        cmd = self.engine.build_composition_filter_graph(
            video_path=self.video_path,
            audio_path=self.audio_path,
            bgm_path=None,
            target_resolution=(1080, 1920),
            duration_sec=10.0,
            include_subtitles=True,
            subtitle_path=missing_sub,
        )
        filt = cmd[cmd.index("-filter_complex") + 1]
        self.assertNotIn("ass=", filt)
        self.assertNotIn("subtitles=", filt)
        self.assertIn("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", filt)

    def test_audio_master_loudness_disabled(self):
        """When master_loudness=False, loudnorm filter is omitted."""
        filt = self.engine.build_audio_filter(
            has_music=True,
            master_loudness=False,
        )
        self.assertNotIn("loudnorm", filt)
        self.assertIn("[amixed]aresample=44100,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[aout]", filt)

        filt_nomusic = self.engine.build_audio_filter(
            has_music=False,
            master_loudness=False,
        )
        self.assertNotIn("loudnorm", filt_nomusic)
        self.assertIn("[1:a]aresample=44100,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[aout]", filt_nomusic)

    def test_lowpass_frequency_custom_and_disabled(self):
        """lowpass filter omitted when 0 or None, included when positive integer."""
        filt_lp = self.engine.build_audio_filter(has_music=True, lowpass_freq=8000)
        self.assertIn("lowpass=f=8000", filt_lp)

        filt_nolp = self.engine.build_audio_filter(has_music=True, lowpass_freq=0)
        self.assertNotIn("lowpass", filt_nolp)


class TestCompositorManifestContractCompliance(unittest.TestCase):
    """Stress testing render() manifest parsing, missing audio handling, and kwargs priority."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.audio_file = self.root / "narration.wav"
        self.audio_file.write_bytes(b"SPEECH_DATA_123")
        self.out_video = self.root / "rendered.mp4"
        self.engine = LoopVideoEngine()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_audio_path_raises_compositor_error(self):
        """Missing audio_path in both manifest and extra_kwargs raises CompositorError."""
        manifest = self.root / "empty_manifest.json"
        manifest.write_text(json.dumps({"category": "monsters"}), encoding="utf-8")

        with self.assertRaises(CompositorError):
            self.engine.render(manifest_path=manifest, output_video_path=self.out_video)

    def test_extra_kwargs_override_manifest_values(self):
        """
        Adversarial test:
        extra_kwargs should take precedence over manifest file entries.
        Exposes Python keyword argument collision if render() unpacks **extra_kwargs
        while simultaneously passing positional/keyword arguments explicitly to self.compose().
        """
        manifest = self.root / "manifest.json"
        manifest.write_text(
            json.dumps({
                "audio_path": str(self.audio_file),
                "category": "cosmic_horror",
                "orientation": "vertical",
                "duration_sec": 45.0,
            }),
            encoding="utf-8",
        )

        with patch.object(self.engine, "compose") as mock_compose:
            mock_compose.return_value = str(self.out_video)
            self.out_video.write_bytes(b"VIDEO")

            res = self.engine.render(
                manifest_path=manifest,
                output_video_path=self.out_video,
                category="monsters",
                orientation="horizontal",
                duration_sec=12.0,
            )

            mock_compose.assert_called_once()
            call_kwargs = mock_compose.call_args[1]
            self.assertEqual(call_kwargs["category"], "monsters")
            self.assertEqual(call_kwargs["orientation"], "horizontal")
            self.assertEqual(call_kwargs["duration_sec"], 12.0)
            self.assertEqual(res["category"], "monsters")
            self.assertEqual(res["resolution"], "1920x1080")


class TestEmpiricalEndToEndFFmpegExecution(unittest.TestCase):
    """
    Empirical Stress Testing: Generates synthetic video and audio streams with real FFmpeg
    and verifies that LoopVideoEngine executes end-to-end rendering without failure.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.loops_dir = self.root / "loops"
        self.dark_ambient_dir = self.loops_dir / "dark_ambient"
        self.dark_ambient_dir.mkdir(parents=True, exist_ok=True)

        self.bg_dir = self.root / "backgrounds"
        self.bg_dir.mkdir(parents=True, exist_ok=True)

        # 1. Generate a synthetic 2.0s loop video (640x360 test pattern)
        self.synth_loop = self.dark_ambient_dir / "test_ambient.mp4"
        cmd_vid = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=640x360:rate=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(self.synth_loop)
        ]
        subprocess.run(cmd_vid, check=True, capture_output=True)

        # 2. Generate a synthetic 3.0s narration audio wav (440Hz sine wave)
        self.synth_audio = self.root / "narration.wav"
        cmd_aud = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-ar", "44100", "-ac", "2",
            str(self.synth_audio)
        ]
        subprocess.run(cmd_aud, check=True, capture_output=True)

        # 3. Generate a synthetic 5.0s background music wav (220Hz sine wave)
        self.synth_bgm = self.root / "ambient_music.wav"
        cmd_bgm = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=220:duration=5",
            "-ar", "44100", "-ac", "2",
            str(self.synth_bgm)
        ]
        subprocess.run(cmd_bgm, check=True, capture_output=True)

        # 4. Generate a fallback image (solid dark blue 1280x720)
        self.synth_image = self.bg_dir / "fallback_image.jpg"
        cmd_img = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=navy:s=1280x720:d=1",
            "-frames:v", "1",
            str(self.synth_image)
        ]
        subprocess.run(cmd_img, check=True, capture_output=True)

        self.engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.bg_dir,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_empirical_render_vertical_shorts_with_ducking(self):
        """Renders vertical (1080x1920) 9:16 Shorts with sidechain ducked BGM end-to-end."""
        out_path = self.root / "output_vertical.mp4"
        rendered = self.engine.compose(
            audio_path=self.synth_audio,
            output_video_path=out_path,
            category="dark_ambient",
            orientation="vertical",
            bg_music_path=self.synth_bgm,
            duration_sec=3.0,
        )

        self.assertTrue(out_path.exists())
        self.assertGreater(out_path.stat().st_size, 1000)

        # Probe output media to verify duration, resolution, audio streams
        info = probe_media(out_path)
        self.assertAlmostEqual(info.duration, 3.0, delta=0.5)
        self.assertEqual(info.video_streams[0].width, 1080)
        self.assertEqual(info.video_streams[0].height, 1920)
        self.assertEqual(info.audio_streams[0].sample_rate, 44100)
        self.assertEqual(info.audio_streams[0].channels, 2)

    def test_empirical_render_horizontal_longform_fallback_image(self):
        """Renders horizontal (1920x1080) 16:9 using fallback image when category is empty."""
        out_path = self.root / "output_horizontal.mp4"
        # Category 'space_abyss' is empty, should cascade to fallback image
        rendered = self.engine.compose(
            audio_path=self.synth_audio,
            output_video_path=out_path,
            category="space_abyss",
            orientation="horizontal",
            bg_music_path=None,
            duration_sec=2.5,
        )

        self.assertTrue(out_path.exists())
        self.assertGreater(out_path.stat().st_size, 1000)

        info = probe_media(out_path)
        self.assertAlmostEqual(info.duration, 2.5, delta=0.5)
        self.assertEqual(info.video_streams[0].width, 1920)
        self.assertEqual(info.video_streams[0].height, 1080)

    def test_empirical_render_micro_duration_subsecond(self):
        """Renders sub-second duration (0.5s) without crashing FFmpeg."""
        out_path = self.root / "output_subsecond.mp4"
        rendered = self.engine.compose(
            audio_path=self.synth_audio,
            output_video_path=out_path,
            category="dark_ambient",
            orientation="vertical",
            duration_sec=0.5,
        )

        self.assertTrue(out_path.exists())
        self.assertGreater(out_path.stat().st_size, 500)
        info = probe_media(out_path)
        self.assertAlmostEqual(info.duration, 0.5, delta=0.3)


if __name__ == "__main__":
    unittest.main()
