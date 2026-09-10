"""
tests/unit/test_loop_engine_fail_closed_challenger.py

Adversarial Stress Test Suite created by Challenger 2 for Milestone 1.
Exhaustively challenges and stress-tests:
1. Missing catalog assets fail-closed under all circumstances.
2. CatalogAssetNotFoundError and LoopVideoAssetError inheritance and raising contracts.
3. Zero procedural live synthesis (no LoopSynthesizerWorker, no lavfi, no _try_live_synthesize).
4. Zero synthetic fallback image generation (no synthetic black JPEGs or procedural planes).
5. Safe traversal handling in category and catalog paths.
6. Clean resolution when valid catalog assets exist.
7. Stream-copy composition cmd maintains '-c:v copy' and subtitle muxing without burning.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.media.interface import (
    BaseVideoCompositor,
    CatalogAssetNotFoundError,
    CompositorError,
)
from src.media.loop_engine import (
    LoopCompositionError,
    LoopVideoAssetError,
    LoopVideoEngine,
    LoopVideoError,
    is_grey_procedural_plane,
)


class TestLoopEngineFailClosedAdversarial(unittest.TestCase):
    """Adversarial stress-testing suite for loop_engine fail-closed behavior."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.loops_dir = self.root / "loops"
        self.loops_dir.mkdir(parents=True, exist_ok=True)
        self.fallback_dir = self.root / "backgrounds"
        self.fallback_dir.mkdir(parents=True, exist_ok=True)
        self.fallback_image = self.root / "fallback.jpg"
        # Notice: self.loops_dir is empty, self.fallback_dir is empty, self.fallback_image does not exist.

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_exception_hierarchy_and_subclass_contracts(self):
        """
        Verify that LoopVideoAssetError is a direct subclass of CatalogAssetNotFoundError
        and LoopVideoError, satisfying both exception contracts.
        """
        self.assertTrue(issubclass(LoopVideoAssetError, CatalogAssetNotFoundError))
        self.assertTrue(issubclass(LoopVideoAssetError, LoopVideoError))
        self.assertTrue(issubclass(LoopVideoAssetError, CompositorError))

        err = LoopVideoAssetError("Simulated missing loop asset")
        self.assertIsInstance(err, CatalogAssetNotFoundError)
        self.assertIsInstance(err, LoopVideoAssetError)
        self.assertIsInstance(err, LoopVideoError)
        self.assertIsInstance(err, CompositorError)

    def test_dead_live_synth_method_is_completely_eliminated(self):
        """LoopVideoEngine must NOT have _try_live_synthesize method."""
        engine = LoopVideoEngine(loops_root_dir=self.loops_dir)
        self.assertFalse(
            hasattr(engine, "_try_live_synthesize"),
            "CRITICAL BUG: _try_live_synthesize was resurrected or not pruned!",
        )

    def test_bogus_categories_allow_fallback_false_fail_closed_across_orientations(self):
        """
        Stress test: Calling resolve_loop_video with bogus/non-existent categories
        and allow_fallback=False across various orientations MUST raise CatalogAssetNotFoundError.
        """
        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.fallback_dir,
            default_fallback_image=self.fallback_image,
        )

        bogus_categories = [
            "nonexistent_category_xyz",
            "fake_theme_9999",
            "completely_bogus",
            "unknown_cosmic_void",
            "random_gibberish_string_alpha_beta",
            "void",
            "does_not_exist",
        ]

        orientations = [
            "horizontal",
            "vertical",
            "16:9",
            "9:16",
            (1920, 1080),
            (1080, 1920),
            (1280, 720),
            None,
        ]

        for cat in bogus_categories:
            for orient in orientations:
                with self.subTest(category=cat, orientation=orient):
                    with self.assertRaises(CatalogAssetNotFoundError) as ctx:
                        engine.resolve_loop_video(
                            category=cat,
                            orientation=orient,
                            allow_fallback=False,
                        )
                    # Verify dual exception type contracts
                    err = ctx.exception
                    self.assertIsInstance(err, CatalogAssetNotFoundError)
                    self.assertIsInstance(err, LoopVideoAssetError)
                    self.assertIsInstance(err, LoopVideoError)

    def test_bogus_categories_allow_fallback_true_when_fallbacks_empty_fails_closed(self):
        """
        Stress test: Calling resolve_loop_video with allow_fallback=True when loop dir
        and fallback dir/image are all empty/missing MUST fail-closed with CatalogAssetNotFoundError.
        """
        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.fallback_dir,
            default_fallback_image=self.fallback_image,
        )

        bogus_categories = [
            "nonexistent_category_xyz",
            "drama_aita",
            "horror",
            "dark_ambient",
            "",
            None,
            "   ",
        ]

        orientations = ["horizontal", "vertical", "16:9", "9:16"]

        for cat in bogus_categories:
            for orient in orientations:
                with self.subTest(category=cat, orientation=orient):
                    with self.assertRaises(CatalogAssetNotFoundError) as ctx:
                        engine.resolve_loop_video(
                            category=cat,
                            orientation=orient,
                            allow_fallback=True,
                        )
                    err = ctx.exception
                    self.assertIsInstance(err, CatalogAssetNotFoundError)
                    self.assertIsInstance(err, LoopVideoAssetError)

    @patch("src.media.loop_worker.LoopSynthesizerWorker")
    def test_zero_procedural_live_synthesis_attempted_on_asset_miss(self, mock_worker_cls):
        """
        Adversarial test: Verify that under NO circumstances does resolve_loop_video
        attempt procedural live synthesis, invoke LoopSynthesizerWorker, or call lavfi.
        """
        mock_worker_instance = MagicMock()
        mock_worker_cls.return_value = mock_worker_instance

        # Even with enable_live_synth=True and environment variable set!
        with patch.dict(os.environ, {"ENABLE_LIVE_LOOP_SYNTH": "1"}):
            engine = LoopVideoEngine(
                loops_root_dir=self.loops_dir,
                default_fallback_dir=self.fallback_dir,
                default_fallback_image=self.fallback_image,
                enable_live_synth=True,
            )

            # Record directory state before
            files_before = list(self.root.rglob("*"))

            with self.assertRaises(CatalogAssetNotFoundError):
                engine.resolve_loop_video(
                    category="completely_absent_loop_theme",
                    allow_fallback=True,
                )

            # Assert LoopSynthesizerWorker was NEVER called
            mock_worker_cls.assert_not_called()
            mock_worker_instance.synthesize_on_demand.assert_not_called()

            # Record directory state after - NO synthetic media should be written!
            files_after = list(self.root.rglob("*"))
            self.assertEqual(
                files_before,
                files_after,
                "Fail-closed violation: synthetic files were created in filesystem!",
            )

    def test_zero_synthetic_black_image_generation(self):
        """
        Stress test: Verify that the engine NEVER generates a synthetic black JPEG
        or fallback image on asset miss, instead failing closed immediately.
        """
        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.fallback_dir,
            default_fallback_image=self.fallback_image,
        )

        with self.assertRaises(CatalogAssetNotFoundError):
            engine.resolve_loop_video(category="space_abyss", allow_fallback=True)

        # Ensure fallback image was NOT created
        self.assertFalse(self.fallback_image.exists())

        # Ensure no JPEG/PNG files created anywhere in the tree
        generated_images = list(self.root.rglob("*.jpg")) + list(self.root.rglob("*.jpeg")) + list(self.root.rglob("*.png"))
        self.assertEqual(generated_images, [])

    def test_path_traversal_in_category_raises_immediately(self):
        """
        Adversarial test: Category strings with path traversal markers (../, /, \\)
        MUST immediately raise LoopVideoAssetError (which is CatalogAssetNotFoundError).
        """
        engine = LoopVideoEngine(loops_root_dir=self.loops_dir)

        malicious_inputs = [
            "../../etc/passwd",
            "../secret",
            "/absolute/root/path",
            "foo/bar",
            "foo\\bar",
            "..\\..\\windows\\system32",
        ]

        for bad_cat in malicious_inputs:
            with self.subTest(category=bad_cat):
                with self.assertRaises(CatalogAssetNotFoundError) as ctx:
                    engine.resolve_loop_video(category=bad_cat)
                self.assertIsInstance(ctx.exception, LoopVideoAssetError)
                self.assertIn("Path traversal detected", str(ctx.exception))

    def test_catalog_returning_path_traversal_fails_closed(self):
        """
        Adversarial test: If SQLite catalog returns an asset record with path traversal
        or outside allowed roots, resolve_loop_video MUST fail-closed with LoopVideoAssetError.
        """
        mock_catalog = MagicMock()
        mock_loop_record = MagicMock()
        mock_loop_record.file_path = "../../etc/shadow"
        mock_loop_record.category = "horror"
        mock_catalog.get_best_loop.return_value = mock_loop_record

        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            catalog=mock_catalog,
        )
        engine._custom_catalog = True

        with self.assertRaises(CatalogAssetNotFoundError) as ctx:
            engine.resolve_loop_video(category="horror", allow_fallback=False)
        self.assertIsInstance(ctx.exception, LoopVideoAssetError)
        self.assertIn("Path traversal detected", str(ctx.exception))

    def test_catalog_returning_outside_root_fails_closed(self):
        """
        Adversarial test: Catalog returning a path outside allowed roots
        MUST fail-closed with LoopVideoAssetError.
        """
        outside_file = self.root / "outside_asset.mp4"
        outside_file.write_bytes(b"VIDEO")

        mock_catalog = MagicMock()
        mock_loop_record = MagicMock()
        mock_loop_record.file_path = str(outside_file)
        mock_loop_record.category = "horror"
        mock_catalog.get_best_loop.return_value = mock_loop_record

        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            catalog=mock_catalog,
        )
        engine._custom_catalog = True

        with self.assertRaises(CatalogAssetNotFoundError) as ctx:
            engine.resolve_loop_video(category="horror", allow_fallback=False)
        self.assertIsInstance(ctx.exception, LoopVideoAssetError)
        self.assertIn("outside assets directory", str(ctx.exception))

    def test_catalog_returning_grey_procedural_is_rejected_and_fails_closed(self):
        """
        Adversarial test: If catalog returns a synthetic monochrome or grey procedural
        plane candidate, it MUST be rejected by is_grey_procedural_plane, and fail-closed
        when no other asset is available.
        """
        mock_catalog = MagicMock()
        mock_loop_record = MagicMock()
        # Point to a fake file within allowed root
        allowed_fake = self.loops_dir / "grey_loop.mp4"
        allowed_fake.write_bytes(b"DATA")
        mock_loop_record.file_path = str(allowed_fake)
        mock_loop_record.category = "horror"
        mock_loop_record.technology = "ffmpeg_lavfi"
        mock_loop_record.sha256 = "procedural"
        mock_loop_record.loop_id = "loop_maritime_lighthouse_h"
        mock_catalog.get_best_loop.return_value = mock_loop_record

        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.fallback_dir,
            default_fallback_image=self.fallback_image,
            catalog=mock_catalog,
        )
        engine._custom_catalog = True

        with self.assertRaises(CatalogAssetNotFoundError) as ctx:
            engine.resolve_loop_video(category="horror", allow_fallback=False)
        self.assertIsInstance(ctx.exception, LoopVideoAssetError)

    def test_catalog_stale_record_missing_on_disk_fails_closed(self):
        """
        Adversarial test: Catalog returns a record pointing to a non-existent file.
        Engine must fall through and fail closed with CatalogAssetNotFoundError.
        """
        mock_catalog = MagicMock()
        mock_loop_record = MagicMock()
        mock_loop_record.file_path = str(self.loops_dir / "non_existent_file.mp4")
        mock_loop_record.category = "horror"
        mock_catalog.get_best_loop.return_value = mock_loop_record

        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.fallback_dir,
            default_fallback_image=self.fallback_image,
            catalog=mock_catalog,
        )
        engine._custom_catalog = True

        with self.assertRaises(CatalogAssetNotFoundError) as ctx:
            engine.resolve_loop_video(category="horror", allow_fallback=False)
        self.assertIsInstance(ctx.exception, LoopVideoAssetError)

    def test_catalog_sqlite_error_handled_gracefully_and_fails_closed(self):
        """
        Adversarial test: When SQLite catalog raises an OperationalError
        (e.g., 'database is locked' or disk corruption), engine catches the exception,
        logs a warning, and cleanly fails closed when filesystem has no assets.
        """
        mock_catalog = MagicMock()
        mock_catalog.get_best_loop.side_effect = sqlite3.OperationalError("database is locked")

        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.fallback_dir,
            default_fallback_image=self.fallback_image,
            catalog=mock_catalog,
        )
        engine._custom_catalog = True

        with self.assertRaises(CatalogAssetNotFoundError) as ctx:
            engine.resolve_loop_video(category="horror", allow_fallback=False)
        self.assertIsInstance(ctx.exception, LoopVideoAssetError)

    def test_valid_catalog_asset_resolves_cleanly(self):
        """
        Positive control: Legitimate video files in the category directory
        resolve cleanly and match the expected Path.
        """
        cat_dir = self.loops_dir / "dark_ambient"
        cat_dir.mkdir(parents=True, exist_ok=True)
        valid_vid = cat_dir / "ambient_loop.mp4"
        valid_vid.write_bytes(b"VALID_LOOP_VIDEO_DATA")

        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.fallback_dir,
            default_fallback_image=self.fallback_image,
        )
        resolved = engine.resolve_loop_video(category="dark_ambient", allow_fallback=False)
        self.assertEqual(resolved, valid_vid)

    def test_build_stream_copy_composition_cmd_preserves_copy_and_mux_subtitles(self):
        """
        Invariant verification: build_stream_copy_composition_cmd MUST contain '-c:v copy'
        and mux subtitles cleanly with '-c:s mov_text' (never burn with libass/libx264).
        """
        engine = LoopVideoEngine(loops_root_dir=self.loops_dir)

        concat_list = self.root / "concat.txt"
        audio = self.root / "speech.wav"
        bgm = self.root / "music.mp3"
        bgm.write_bytes(b"BGM_DATA")
        out_video = self.root / "output.mp4"
        subtitles = self.root / "subs.ass"
        subtitles.write_text(
            "[Script Info]\nTitle: Test Subtitle\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,Test subtitle narration line\n"
        )

        cmd = engine.build_stream_copy_composition_cmd(
            concat_list_path=concat_list,
            audio_path=audio,
            bgm_path=bgm,
            duration_sec=30.0,
            output_video_path=out_video,
            subtitle_path=subtitles,
        )

        # 1. Verify -c:v copy is present
        self.assertIn("-c:v", cmd)
        c_v_idx = cmd.index("-c:v")
        self.assertEqual(cmd[c_v_idx + 1], "copy")

        # 2. Verify zero subtitle burning (no libass, no -vf, no subtitle burn filter)
        cmd_str = " ".join(cmd)
        self.assertNotIn("-vf", cmd)
        self.assertNotIn("libass", cmd_str)
        self.assertNotIn("subtitles=", cmd_str)
        self.assertNotIn("libx264", cmd_str)
        # Ensure 'ass=' as a filter clause (not part of lowpass) is not present
        import re
        self.assertIsNone(re.search(r"\bass=", cmd_str))

        # 3. Verify active captions are muxed
        self.assertIn("-c:s", cmd)
        c_s_idx = cmd.index("-c:s")
        self.assertEqual(cmd[c_s_idx + 1], "mov_text")

        # 4. Verify -movflags +faststart is present
        self.assertIn("-movflags", cmd)
        mf_idx = cmd.index("-movflags")
        self.assertEqual(cmd[mf_idx + 1], "+faststart")

    def test_compose_missing_assets_fails_closed(self):
        """
        End-to-end compose() call without existing loop assets MUST fail-closed
        with CatalogAssetNotFoundError / LoopVideoAssetError without attempting live synthesis.
        """
        audio = self.root / "speech.wav"
        audio.write_bytes(b"RIFF" + b"\x00" * 40)
        out_video = self.root / "out.mp4"

        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.fallback_dir,
            default_fallback_image=self.fallback_image,
        )

        with self.assertRaises(CatalogAssetNotFoundError) as ctx:
            engine.compose(
                audio_path=audio,
                output_video_path=out_video,
                category="totally_nonexistent_category",
            )
        self.assertIsInstance(ctx.exception, LoopVideoAssetError)

    def test_symlink_pointing_outside_allowed_roots_fails_closed(self):
        """
        Adversarial test: A symlink inside the assets folder pointing outside
        the allowed asset hierarchy MUST be rejected by path safety checks.
        """
        outside_target = self.root / "outside_target.mp4"
        outside_target.write_bytes(b"OUTSIDE_SECRET_VIDEO")

        symlink_file = self.loops_dir / "symlink_evil.mp4"
        try:
            symlink_file.symlink_to(outside_target)
        except OSError:
            self.skipTest("Symlink creation not supported in this environment")

        mock_catalog = MagicMock()
        mock_loop_record = MagicMock()
        mock_loop_record.file_path = str(symlink_file)
        mock_loop_record.category = "horror"
        mock_catalog.get_best_loop.return_value = mock_loop_record

        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            catalog=mock_catalog,
        )
        engine._custom_catalog = True

        with self.assertRaises(CatalogAssetNotFoundError) as ctx:
            engine.resolve_loop_video(category="horror", allow_fallback=False)
        self.assertIsInstance(ctx.exception, LoopVideoAssetError)
        self.assertIn("outside assets directory", str(ctx.exception))

    def test_zero_byte_assets_in_category_and_fallbacks_fail_closed(self):
        """
        Adversarial test: When files exist on disk but are 0 bytes (corrupted/truncated),
        resolve_loop_video MUST refuse to return them and must fail closed.
        """
        cat_dir = self.loops_dir / "space_abyss"
        cat_dir.mkdir(parents=True, exist_ok=True)
        zero_video = cat_dir / "zero_loop.mp4"
        zero_video.touch()  # 0 bytes

        zero_fallback_img = self.fallback_dir / "zero_bg.jpg"
        zero_fallback_img.touch()  # 0 bytes

        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.fallback_dir,
            default_fallback_image=self.fallback_image,
        )

        with self.assertRaises(CatalogAssetNotFoundError) as ctx:
            engine.resolve_loop_video(category="space_abyss", allow_fallback=True)
        self.assertIsInstance(ctx.exception, LoopVideoAssetError)

    def test_grey_monochrome_files_rejected_and_fails_closed(self):
        """
        Adversarial test: If files named 'monochrome.mp4', 'grey_background.mp4',
        or 'tv_static.mp4' exist in loops, they MUST be rejected as unusable plane-0,
        failing closed with CatalogAssetNotFoundError.
        """
        cat_dir = self.loops_dir / "monsters"
        cat_dir.mkdir(parents=True, exist_ok=True)
        (cat_dir / "grey_monochrome.mp4").write_bytes(b"GREY_PLANE_DATA")
        (cat_dir / "tv_static.mp4").write_bytes(b"STATIC_OVERLAY_DATA")

        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.fallback_dir,
            default_fallback_image=self.fallback_image,
        )

        with self.assertRaises(CatalogAssetNotFoundError) as ctx:
            engine.resolve_loop_video(category="monsters", allow_fallback=False)
        self.assertIsInstance(ctx.exception, LoopVideoAssetError)

    def test_concurrent_multithreaded_missing_asset_requests_fail_closed(self):
        """
        Concurrency stress test: 20 concurrent threads requesting missing assets
        must all fail-closed with CatalogAssetNotFoundError without thread contention
        or state corruption.
        """
        import concurrent.futures

        engine = LoopVideoEngine(
            loops_root_dir=self.loops_dir,
            default_fallback_dir=self.fallback_dir,
            default_fallback_image=self.fallback_image,
        )

        def worker_task(thread_id: int):
            cat = f"bogus_thread_cat_{thread_id}"
            try:
                engine.resolve_loop_video(category=cat, allow_fallback=True)
                return "FAIL_DID_NOT_RAISE"
            except CatalogAssetNotFoundError as e:
                if isinstance(e, LoopVideoAssetError):
                    return "PASS"
                return "FAIL_WRONG_TYPE"
            except Exception as e:
                return f"FAIL_UNEXPECTED_{type(e).__name__}"

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker_task, i) for i in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        self.assertEqual(results, ["PASS"] * 20)

