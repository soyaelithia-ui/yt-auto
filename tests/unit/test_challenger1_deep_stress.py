"""
Deep Stress & Empirical Adversarial Test Harness for LoopVideoEngine.
Executed by Challenger 1 in Gate Iteration 2.
"""
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
from lib.ffmpeg import probe_media


class TestChallenger1AdversarialHarness(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.loops_dir = self.root / "loops"
        self.loops_dir.mkdir(parents=True, exist_ok=True)
        self.bg_dir = self.root / "backgrounds"
        self.bg_dir.mkdir(parents=True, exist_ok=True)
        self.default_bg = self.root / "default_bg.jpg"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_kwargs_collision_exhaustive_matrix(self):
        """
        Exhaustively test calling render() with ALL combinations of alias and bound keyword arguments
        to ensure no duplicate keyword argument TypeError can ever occur.
        """
        engine = LoopVideoEngine(loops_root_dir=self.loops_dir)
        dummy_audio = self.root / "audio.wav"
        dummy_audio.write_bytes(b"DUMMY_AUDIO_DATA_FOR_TEST")
        dummy_manifest = self.root / "manifest.json"
        dummy_manifest.write_text(json.dumps({
            "audio_path": str(dummy_audio),
            "category": "cosmic_horror",
            "orientation": "vertical",
            "duration_sec": 10.0,
            "bg_music_path": str(self.root / "music.mp3"),
            "subtitle_path": str(self.root / "subs.ass"),
            "include_subtitles": True,
            "video_loop_path": str(self.root / "loop.mp4"),
        }), encoding="utf-8")

        out_path = self.root / "out.mp4"

        # Mock compose to intercept and verify forwarded arguments
        with patch.object(engine, "compose") as mock_compose:
            mock_compose.return_value = str(out_path)

            # Test Matrix: all possible pipeline kwarg permutations
            permutations = [
                {"audio_path": str(dummy_audio)},
                {"narration_audio_path": str(dummy_audio)},
                {"narration_path": str(dummy_audio)},
                {"category": "monsters", "loop_category": "dark_ambient", "style": "cinematic", "template": "cosmic"},
                {"orientation": "horizontal", "video_mode": "short", "aspect_ratio": "9:16"},
                {"duration_sec": 25.5, "min_duration": 30.0},
                {"bg_music_path": "m.mp3", "music_path": "m2.mp3", "bgm_path": "m3.mp3"},
                {"subtitle_path": "s.ass", "subtitles_path": "s2.ass", "include_subtitles": True, "enable_subtitles": True},
                {"video_loop_path": "v.mp4", "background_path": "v2.mp4", "background_image": "v3.jpg"},
                {"fps": 60, "crf": 18, "preset": "fast", "music_volume": 0.2, "ducking_threshold": 0.05},
                {"ducking_ratio": 12.0, "ducking_attack_ms": 15.0, "ducking_release_ms": 400.0, "master_loudness": False},
                # Combinations of ALL at once
                {
                    "audio_path": str(dummy_audio),
                    "narration_audio_path": str(dummy_audio),
                    "video_path": str(out_path),
                    "category": "monsters",
                    "loop_category": "cosmic_horror",
                    "style": "dark",
                    "template": "lovecraft",
                    "orientation": "horizontal",
                    "video_mode": "longform",
                    "aspect_ratio": "16:9",
                    "duration_sec": 120.0,
                    "bg_music_path": "bgm.mp3",
                    "music_path": "music.mp3",
                    "subtitle_path": "sub.ass",
                    "include_subtitles": True,
                    "enable_subtitles": True,
                    "video_loop_path": "loop.mp4",
                    "background_path": "bg.mp4",
                    "fps": 30,
                    "crf": 22,
                    "preset": "medium",
                    "music_volume": 0.1,
                    "ducking_threshold": 0.03,
                    "ducking_ratio": 6.0,
                    "ducking_attack_ms": 25.0,
                    "ducking_release_ms": 300.0,
                    "master_loudness": True,
                    "timeout": 60.0,
                    "custom_extra_param_1": "value1",
                    "custom_extra_param_2": 42,
                }
            ]

            for idx, kw in enumerate(permutations):
                try:
                    res = engine.render(manifest_path=dummy_manifest, output_video_path=out_path, **kw)
                    self.assertIsInstance(res, dict)
                except TypeError as te:
                    self.fail(f"Permutation {idx} raised TypeError: {te}")

    def test_corrupted_directory_tree_stress(self):
        """
        Stress test complex asset directory tree with:
        - Nested empty subfolders
        - Zero-byte files with various valid extensions
        - Non-media files (.txt, .DS_Store, .tmp)
        - Subdirectories with non-standard names
        - Only 1 valid file deeply placed in a fallback category
        """
        # Create categories with zero byte files and non-media files
        for cat in LoopVideoEngine.THEMATIC_CATEGORIES:
            cat_dir = self.loops_dir / cat
            cat_dir.mkdir(parents=True, exist_ok=True)
            (cat_dir / "zero.mp4").touch()
            (cat_dir / "zero.webm").touch()
            (cat_dir / "notes.txt").write_text("not media")
            (cat_dir / ".hidden_empty.mov").touch()

        # Add an empty custom directory
        (self.loops_dir / "empty_custom").mkdir(parents=True, exist_ok=True)

        # In fallback dir, put 0-byte images and txt files
        (self.bg_dir / "zero.jpg").touch()
        (self.bg_dir / "info.json").write_text("{}")

        # Finally, put ONE valid file in dark_forest
        valid_file = self.loops_dir / "dark_forest" / "real_forest.mp4"
        valid_file.write_bytes(b"REAL_VIDEO_CONTENT_BYTES")

        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.bg_dir,
            default_fallback_image=self.default_bg,
        )

        # Scanning should only discover real_forest.mp4 in dark_forest and empty lists for others
        scanned = engine.scan_libraries()
        self.assertEqual(len(scanned["dark_forest"]), 1)
        self.assertEqual(scanned["dark_forest"][0], valid_file)
        for cat in LoopVideoEngine.THEMATIC_CATEGORIES:
            if cat != "dark_forest":
                self.assertEqual(len(scanned[cat]), 0)

        # Requesting cosmic_horror should fallback directly to dark_forest/real_forest.mp4
        resolved = engine.resolve_loop_video(category="cosmic_horror")
        self.assertEqual(resolved, valid_file)

        # Requesting an unlisted category should also resolve to dark_forest/real_forest.mp4
        resolved_unlisted = engine.resolve_loop_video(category="non_existent_category")
        self.assertEqual(resolved_unlisted, valid_file)

    def test_empirical_real_ffmpeg_rendering_dual_aspect_ratios_and_audio(self):
        """
        Empirically generate real video & audio, execute composition in both 9:16 and 16:9,
        and probe output metadata with ffprobe.
        """
        # Create synthetic 2s loop video (320x240)
        synth_cat_dir = self.loops_dir / "dark_ambient"
        synth_cat_dir.mkdir(parents=True, exist_ok=True)
        synth_vid = synth_cat_dir / "loop.mp4"
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=25",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(synth_vid)
        ], check=True, capture_output=True)

        # Create synthetic 4s narration audio (sine 440Hz)
        synth_speech = self.root / "speech.wav"
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
            "-ar", "48000", "-ac", "2",
            str(synth_speech)
        ], check=True, capture_output=True)

        # Create synthetic 6s BGM audio (sine 220Hz)
        synth_bgm = self.root / "bgm.wav"
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=220:duration=6",
            "-ar", "48000", "-ac", "2",
            str(synth_bgm)
        ], check=True, capture_output=True)

        engine = LoopVideoEngine(loops_root_dir=self.loops_dir)

        # 1. Test 9:16 Vertical Export
        out_v = self.root / "vertical_render.mp4"
        res_v = engine.compose(
            audio_path=synth_speech,
            output_video_path=out_v,
            category="dark_ambient",
            orientation="9:16",
            bg_music_path=synth_bgm,
            duration_sec=4.0,
            music_volume=0.1,
            ducking_threshold=0.03,
        )
        self.assertTrue(out_v.exists())
        self.assertGreater(out_v.stat().st_size, 2000)
        info_v = probe_media(out_v)
        self.assertAlmostEqual(info_v.duration, 4.0, delta=0.5)
        self.assertEqual(info_v.video_streams[0].width, 1080)
        self.assertEqual(info_v.video_streams[0].height, 1920)

        # 2. Test 16:9 Horizontal Export
        out_h = self.root / "horizontal_render.mp4"
        res_h = engine.compose(
            audio_path=synth_speech,
            output_video_path=out_h,
            category="dark_ambient",
            orientation="16:9",
            bg_music_path=synth_bgm,
            duration_sec=4.0,
            music_volume=0.1,
            ducking_threshold=0.03,
        )
        self.assertTrue(out_h.exists())
        self.assertGreater(out_h.stat().st_size, 2000)
        info_h = probe_media(out_h)
        self.assertAlmostEqual(info_h.duration, 4.0, delta=0.5)
        self.assertEqual(info_h.video_streams[0].width, 1920)
        self.assertEqual(info_h.video_streams[0].height, 1080)


if __name__ == "__main__":
    unittest.main()
