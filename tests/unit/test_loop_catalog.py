"""
Unit tests for LoopCatalogRepository (src/core/loop_catalog.py).

Covers:
1. SQLite schema creation and table initialization.
2. Registering loop records with SHA-256 and JSON parameters.
3. Querying best loop with least-recently used / lowest usage count smart rotation.
4. Thematic tag matching and scoring.
5. Recording usage count increment and timestamp update.
6. Audit and cleanup of missing or corrupted files.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from src.core.catalog import LoopCatalogRepository, LoopRecord, compute_file_sha256


class TestLoopCatalogRepository(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_loops.db")
        self.repo = LoopCatalogRepository(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_dummy_video(self, name: str, size: int = 30_000) -> str:
        p = Path(self.temp_dir.name) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"0" * size)
        return str(p)

    def test_register_and_get_loop(self):
        file_path = self._create_dummy_video("loops/cosmic_01.mp4")
        sha = compute_file_sha256(file_path)

        rec = LoopRecord(
            loop_id="web_cosmic_v_1",
            category="cosmic_horror",
            technology="webgl_shader",
            orientation="vertical",
            width=1080,
            height=1920,
            duration_sec=8.0,
            fps=30,
            file_path=file_path,
            file_size_bytes=1024,
            sha256=sha,
            theme_tags=["void", "nebula", "black_hole"],
            generator_params={"seed": 42},
        )
        self.assertTrue(self.repo.register_loop(rec))

        fetched = self.repo.get_loop_by_id("web_cosmic_v_1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.category, "cosmic_horror")
        self.assertEqual(fetched.technology, "webgl_shader")
        self.assertEqual(fetched.orientation, "vertical")
        self.assertEqual(fetched.theme_tags, ["void", "nebula", "black_hole"])
        self.assertEqual(fetched.generator_params, {"seed": 42})
        self.assertEqual(fetched.usage_count, 0)

    def test_smart_rotation_least_recently_used(self):
        f1 = self._create_dummy_video("loops/m1.mp4")
        f2 = self._create_dummy_video("loops/m2.mp4")

        rec1 = LoopRecord(
            loop_id="loop_m1",
            category="monsters",
            technology="canvas2d",
            orientation="vertical",
            width=1080,
            height=1920,
            duration_sec=6.0,
            fps=30,
            file_path=f1,
            file_size_bytes=1024,
            sha256=compute_file_sha256(f1),
            usage_count=2,
        )
        rec2 = LoopRecord(
            loop_id="loop_m2",
            category="monsters",
            technology="canvas2d",
            orientation="vertical",
            width=1080,
            height=1920,
            duration_sec=6.0,
            fps=30,
            file_path=f2,
            file_size_bytes=1024,
            sha256=compute_file_sha256(f2),
            usage_count=0,
        )
        self.repo.register_loop(rec1)
        self.repo.register_loop(rec2)

        # Loop 2 has usage_count=0, should be picked first
        best = self.repo.get_best_loop("monsters", orientation="vertical")
        self.assertIsNotNone(best)
        self.assertEqual(best.loop_id, "loop_m2")

        # Record usage on loop 2
        self.repo.record_loop_usage("loop_m2")
        best_after = self.repo.get_loop_by_id("loop_m2")
        self.assertEqual(best_after.usage_count, 1)
        self.assertIsNotNone(best_after.last_used_at)

    def test_tag_based_matching(self):
        f1 = self._create_dummy_video("loops/tree.mp4")
        f2 = self._create_dummy_video("loops/spore.mp4")

        self.repo.register_loop(LoopRecord(
            loop_id="forest_trees",
            category="dark_forest",
            technology="canvas2d",
            orientation="horizontal",
            width=1920,
            height=1080,
            duration_sec=8.0,
            fps=30,
            file_path=f1,
            file_size_bytes=1024,
            sha256=compute_file_sha256(f1),
            theme_tags=["trees", "branches"],
        ))
        self.repo.register_loop(LoopRecord(
            loop_id="forest_spores",
            category="dark_forest",
            technology="canvas2d",
            orientation="horizontal",
            width=1920,
            height=1080,
            duration_sec=8.0,
            fps=30,
            file_path=f2,
            file_size_bytes=1024,
            sha256=compute_file_sha256(f2),
            theme_tags=["spores", "bioluminescence", "green"],
        ))

        # Search specifically for spores tag
        best = self.repo.get_best_loop("dark_forest", orientation="horizontal", requested_tags=["spores", "bioluminescence"])
        self.assertIsNotNone(best)
        self.assertEqual(best.loop_id, "forest_spores")

    def test_audit_and_cleanup_removes_missing_files(self):
        f1 = self._create_dummy_video("loops/real.mp4")
        missing_path = os.path.join(self.temp_dir.name, "loops/ghost.mp4")

        self.repo.register_loop(LoopRecord(
            loop_id="real_loop",
            category="space_abyss",
            technology="webgl_shader",
            orientation="vertical",
            width=1080,
            height=1920,
            duration_sec=8.0,
            fps=30,
            file_path=f1,
            file_size_bytes=1024,
            sha256=compute_file_sha256(f1),
        ))
        self.repo.register_loop(LoopRecord(
            loop_id="ghost_loop",
            category="space_abyss",
            technology="webgl_shader",
            orientation="vertical",
            width=1080,
            height=1920,
            duration_sec=8.0,
            fps=30,
            file_path=missing_path,
            file_size_bytes=1024,
            sha256="fake_sha",
        ))

        audit = self.repo.audit_and_cleanup(auto_remove_missing=True)
        self.assertEqual(audit["total_checked"], 2)
        self.assertEqual(audit["valid"], 1)
        self.assertEqual(audit["missing"], 1)
        self.assertIn("ghost_loop", audit["removed_ids"])

        # Verify ghost loop is deleted from DB
        self.assertIsNone(self.repo.get_loop_by_id("ghost_loop"))
        self.assertIsNotNone(self.repo.get_loop_by_id("real_loop"))

    def test_get_best_loop_rewrites_legacy_absolute_paths_to_repo_root(self):
        from unittest.mock import patch

        repo = Path(self.temp_dir.name) / "repo"
        dest = repo / "assets" / "loops" / "ok.mp4"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"0" * 30_000)
        stale = "/home/moku/projects/yt-auto/assets/loops/ok.mp4"
        self.repo.register_loop(LoopRecord(
            loop_id="stale_abs_loop",
            category="cosmic_horror",
            technology="ffmpeg_lavfi",
            orientation="vertical",
            width=1080,
            height=1920,
            duration_sec=8.0,
            fps=30,
            file_path=stale,
            file_size_bytes=30_000,
            sha256="abc",
        ))
        with patch("src.core.catalog.BASE_DIR", repo):
            best = self.repo.get_best_loop("cosmic_horror", "vertical")
        self.assertIsNotNone(best)
        self.assertEqual(Path(best.file_path), dest)
        self.assertNotIn("/srv/projects", best.file_path)
        self.assertNotIn("/home/moku/projects/yt-auto", best.file_path)

    def test_count_loops_sql_without_list(self):
        """count_loops uses cheap SQL COUNT and matches list length without loading rows."""
        self.assertEqual(self.repo.count_loops(category="monsters", orientation="vertical"), 0)
        f1 = self._create_dummy_video("loops/c1.mp4")
        f2 = self._create_dummy_video("loops/c2.mp4")
        for i, fp in enumerate((f1, f2), start=1):
            self.repo.register_loop(LoopRecord(
                loop_id=f"cnt_{i}",
                category="monsters",
                technology="canvas2d",
                orientation="vertical",
                width=1080,
                height=1920,
                duration_sec=6.0,
                fps=30,
                file_path=fp,
                file_size_bytes=30_000,
                sha256=compute_file_sha256(fp),
            ))
        self.repo.register_loop(LoopRecord(
            loop_id="cnt_h",
            category="monsters",
            technology="canvas2d",
            orientation="horizontal",
            width=1920,
            height=1080,
            duration_sec=6.0,
            fps=30,
            file_path=self._create_dummy_video("loops/c_h.mp4"),
            file_size_bytes=30_000,
            sha256="x",
        ))
        self.assertEqual(self.repo.count_loops(category="monsters", orientation="vertical"), 2)
        self.assertEqual(self.repo.count_loops(category="monsters", orientation="horizontal"), 1)
        listed = self.repo.list_loops(category="monsters", orientation="vertical", limit=1000)
        self.assertEqual(self.repo.count_loops(category="monsters", orientation="vertical"), len(listed))

    # === Milestone 1 New Tests ===

    def test_sync_catalog_from_assets_indexes_all_loops(self):
        """sync_catalog_from_assets scans assets/loops/ and indexes >= 50 pre-rendered loops."""
        from src.config import BASE_DIR
        loops_root = BASE_DIR / "assets" / "loops"
        self.assertTrue(loops_root.is_dir(), "assets/loops must exist in repository")

        self.assertEqual(self.repo.count_loops(), 0)
        indexed_count = self.repo.sync_catalog_from_assets(assets_dir=loops_root)
        self.assertGreaterEqual(indexed_count, 50, f"Expected >= 50 indexed loops, got {indexed_count}")
        self.assertEqual(self.repo.count_loops(), indexed_count)

        h_count = self.repo.count_loops(orientation="horizontal")
        v_count = self.repo.count_loops(orientation="vertical")
        self.assertGreaterEqual(h_count, 20, f"Expected >= 20 horizontal loops, got {h_count}")
        self.assertGreaterEqual(v_count, 5, f"Expected >= 5 vertical loops, got {v_count}")

        records = self.repo.list_loops(limit=200)
        for rec in records:
            p = Path(rec.file_path)
            self.assertTrue(p.is_file(), f"Indexed file does not exist on disk: {rec.file_path}")
            self.assertGreater(rec.file_size_bytes, 25_000, f"File too small (<25KB): {rec.file_path}")
            self.assertEqual(len(rec.sha256), 64, f"Invalid SHA-256 hex digest: {rec.sha256}")
            self.assertNotEqual(rec.sha256, "procedural", "Pre-rendered loop must have real SHA-256 hash")
            self.assertGreater(rec.duration_sec, 0.0)
            self.assertIn(rec.orientation, ("horizontal", "vertical"))
            self.assertIn(rec.technology, ("cinematic_master", "cinematic_atomic", "pre-rendered"))

    def test_sync_catalog_idempotency_and_preservation(self):
        """Repeated sync_catalog_from_assets calls do not duplicate rows or wipe usage counters."""
        from src.config import BASE_DIR
        loops_root = BASE_DIR / "assets" / "loops"

        c1 = self.repo.sync_catalog_from_assets(assets_dir=loops_root)
        self.assertGreaterEqual(c1, 50)

        sample = self.repo.list_loops(limit=1)[0]
        self.repo.record_loop_usage(sample.loop_id)
        rec_after_usage = self.repo.get_loop_by_id(sample.loop_id)
        self.assertEqual(rec_after_usage.usage_count, 1)
        last_used = rec_after_usage.last_used_at
        self.assertIsNotNone(last_used)

        c2 = self.repo.sync_catalog_from_assets(assets_dir=loops_root)
        self.assertEqual(self.repo.count_loops(), c1, "Count must remain identical after second sync")

        rec_after_resync = self.repo.get_loop_by_id(sample.loop_id)
        self.assertEqual(rec_after_resync.usage_count, 1, "Re-sync must not reset usage_count")
        self.assertEqual(rec_after_resync.last_used_at, last_used, "Re-sync must not reset last_used_at")

    def test_auto_seeding_on_empty_database(self):
        """When auto_seed is enabled, initializing on an empty database populates >= 50 loops."""
        db_path = os.path.join(self.temp_dir.name, "autoseed_fresh.db")
        repo = LoopCatalogRepository(db_path=db_path, auto_seed=True)
        self.assertGreaterEqual(repo.count_loops(), 50)
        self.assertGreaterEqual(repo.count_loops(orientation="horizontal"), 20)
        self.assertGreaterEqual(repo.count_loops(orientation="vertical"), 5)

        repo2 = LoopCatalogRepository(db_path=db_path, auto_seed=True)
        self.assertEqual(repo2.count_loops(), repo.count_loops())

    def test_seeded_rotation_different_seeds(self):
        """When usage_counts are equal, different seeds yield different loops deterministically."""
        for i in range(10):
            fp = self._create_dummy_video(f"loops/seed_horror_{i}.mp4")
            self.repo.register_loop(LoopRecord(
                loop_id=f"seed_horror_{i}",
                category="horror",
                technology="pre-rendered",
                orientation="horizontal",
                width=1920,
                height=1080,
                duration_sec=6.0,
                fps=30,
                file_path=fp,
                file_size_bytes=30_000,
                sha256=compute_file_sha256(fp),
                usage_count=0,
            ))

        l1 = self.repo.get_best_loop("horror", orientation="horizontal", seed=101)
        l2 = self.repo.get_best_loop("horror", orientation="horizontal", seed=202)
        l3 = self.repo.get_best_loop("horror", orientation="horizontal", seed=303)

        self.assertIsNotNone(l1)
        self.assertIsNotNone(l2)
        self.assertIsNotNone(l3)

        self.assertEqual(self.repo.get_best_loop("horror", orientation="horizontal", seed=101).loop_id, l1.loop_id)
        self.assertEqual(self.repo.get_best_loop("horror", orientation="horizontal", seed=202).loop_id, l2.loop_id)

        unique_ids = {l1.loop_id, l2.loop_id, l3.loop_id}
        self.assertGreater(len(unique_ids), 1, "Different seeds must produce different loop selections")

    def test_seeded_rotation_usage_count_precedence(self):
        """Lowest usage_count strictly takes precedence over seed randomization."""
        fp1 = self._create_dummy_video("loops/p_h1.mp4")
        fp2 = self._create_dummy_video("loops/p_h2.mp4")
        self.repo.register_loop(LoopRecord(
            loop_id="loop_used",
            category="horror",
            technology="pre-rendered",
            orientation="horizontal",
            width=1920,
            height=1080,
            duration_sec=6.0,
            fps=30,
            file_path=fp1,
            file_size_bytes=30_000,
            sha256=compute_file_sha256(fp1),
            usage_count=3,
        ))
        self.repo.register_loop(LoopRecord(
            loop_id="loop_fresh",
            category="horror",
            technology="pre-rendered",
            orientation="horizontal",
            width=1920,
            height=1080,
            duration_sec=6.0,
            fps=30,
            file_path=fp2,
            file_size_bytes=30_000,
            sha256=compute_file_sha256(fp2),
            usage_count=0,
        ))

        for test_seed in range(20):
            picked = self.repo.get_best_loop("horror", orientation="horizontal", seed=test_seed)
            self.assertEqual(picked.loop_id, "loop_fresh", f"Seed {test_seed} failed: fresh loop must be picked")

    def test_exclude_loop_ids_never_returned(self):
        """Loops listed in exclude_loop_ids are never returned by get_best_loop."""
        ids = ["ex_1", "ex_2", "ex_3"]
        for lid in ids:
            fp = self._create_dummy_video(f"loops/{lid}.mp4")
            self.repo.register_loop(LoopRecord(
                loop_id=lid,
                category="drama",
                technology="pre-rendered",
                orientation="horizontal",
                width=1920,
                height=1080,
                duration_sec=6.0,
                fps=30,
                file_path=fp,
                file_size_bytes=30_000,
                sha256=compute_file_sha256(fp),
                usage_count=0,
            ))

        b1 = self.repo.get_best_loop("drama", orientation="horizontal", exclude_loop_ids=["ex_1"])
        self.assertIn(b1.loop_id, ["ex_2", "ex_3"])

        b2 = self.repo.get_best_loop("drama", orientation="horizontal", exclude_loop_ids=["ex_1", "ex_2"])
        self.assertEqual(b2.loop_id, "ex_3")

        b3 = self.repo.get_best_loop("drama", orientation="horizontal", exclude_loop_ids=["ex_1", "ex_2", "ex_3"])
        self.assertIsNone(b3)

    def test_multi_scene_sequence_exclusion(self):
        """Simulating a 5-scene longform video: cumulative exclusions ensure 5 distinct loops."""
        for i in range(5):
            fp = self._create_dummy_video(f"loops/scene_loop_{i}.mp4")
            self.repo.register_loop(LoopRecord(
                loop_id=f"scene_loop_{i}",
                category="scifi",
                technology="pre-rendered",
                orientation="horizontal",
                width=1920,
                height=1080,
                duration_sec=6.0,
                fps=30,
                file_path=fp,
                file_size_bytes=30_000,
                sha256=compute_file_sha256(fp),
                usage_count=0,
            ))

        used = []
        for shot_idx in range(5):
            chosen = self.repo.get_best_loop(
                category="scifi",
                orientation="horizontal",
                seed=shot_idx * 97,
                exclude_loop_ids=used,
            )
            self.assertIsNotNone(chosen)
            self.assertNotIn(chosen.loop_id, used)
            used.append(chosen.loop_id)

        self.assertEqual(len(set(used)), 5, "Must select 5 unique loops across 5 scenes")

    def test_channel_isolation_moku_and_aelithia(self):
        """Queries for Moku return horror/dark loops; queries for Aelithia return drama/cozy loops."""
        f_moku1 = self._create_dummy_video("loops/moku_bunker.mp4")
        f_moku2 = self._create_dummy_video("loops/moku_forest.mp4")
        self.repo.register_loop(LoopRecord(
            loop_id="moku_horror_bunker",
            category="horror",
            technology="pre-rendered",
            orientation="horizontal",
            width=1920,
            height=1080,
            duration_sec=6.0,
            fps=30,
            file_path=f_moku1,
            file_size_bytes=30_000,
            sha256="sha_m1",
            theme_tags=["moku", "horror", "bunker"],
        ))
        self.repo.register_loop(LoopRecord(
            loop_id="moku_dark_forest_trees",
            category="dark_forest",
            technology="pre-rendered",
            orientation="horizontal",
            width=1920,
            height=1080,
            duration_sec=6.0,
            fps=30,
            file_path=f_moku2,
            file_size_bytes=30_000,
            sha256="sha_m2",
            theme_tags=["moku", "forest", "dark"],
        ))

        f_ael1 = self._create_dummy_video("loops/aelithia_cafe.mp4")
        f_ael2 = self._create_dummy_video("loops/aelithia_rain.mp4")
        self.repo.register_loop(LoopRecord(
            loop_id="aelithia_drama_cafe",
            category="drama",
            technology="pre-rendered",
            orientation="horizontal",
            width=1920,
            height=1080,
            duration_sec=6.0,
            fps=30,
            file_path=f_ael1,
            file_size_bytes=30_000,
            sha256="sha_a1",
            theme_tags=["aelithia", "drama", "cafe"],
        ))
        self.repo.register_loop(LoopRecord(
            loop_id="aelithia_cozy_rain",
            category="cozy_ambient",
            technology="pre-rendered",
            orientation="horizontal",
            width=1920,
            height=1080,
            duration_sec=6.0,
            fps=30,
            file_path=f_ael2,
            file_size_bytes=30_000,
            sha256="sha_a2",
            theme_tags=["aelithia", "cozy", "rain"],
        ))

        moku_loop = self.repo.get_best_loop("horror", orientation="horizontal", channel="moku")
        self.assertIsNotNone(moku_loop)
        self.assertEqual(moku_loop.loop_id, "moku_horror_bunker")
        self.assertNotIn("aelithia", moku_loop.loop_id)

        ael_loop = self.repo.get_best_loop("drama", orientation="horizontal", channel="aelithia")
        self.assertIsNotNone(ael_loop)
        self.assertEqual(ael_loop.loop_id, "aelithia_drama_cafe")
        self.assertNotIn("moku", ael_loop.loop_id)

    def test_channel_isolation_fallback_confinement(self):
        """When an exact category has no matches, channel fallback never crosses channel boundaries."""
        f_moku = self._create_dummy_video("loops/moku_ambient.mp4")
        f_ael = self._create_dummy_video("loops/ael_cozy.mp4")
        self.repo.register_loop(LoopRecord(
            loop_id="moku_fallback_ambient",
            category="dark_ambient",
            technology="pre-rendered",
            orientation="horizontal",
            width=1920,
            height=1080,
            duration_sec=6.0,
            fps=30,
            file_path=f_moku,
            file_size_bytes=30_000,
            sha256="sha_m_fb",
            theme_tags=["moku"],
        ))
        self.repo.register_loop(LoopRecord(
            loop_id="aelithia_fallback_cozy",
            category="cozy_ambient",
            technology="pre-rendered",
            orientation="horizontal",
            width=1920,
            height=1080,
            duration_sec=6.0,
            fps=30,
            file_path=f_ael,
            file_size_bytes=30_000,
            sha256="sha_a_fb",
            theme_tags=["aelithia"],
        ))

        fb_moku = self.repo.get_best_loop("unknown_horror_category", orientation="horizontal", channel="moku")
        self.assertIsNotNone(fb_moku)
        self.assertEqual(fb_moku.loop_id, "moku_fallback_ambient")

        fb_ael = self.repo.get_best_loop("unknown_drama_category", orientation="horizontal", channel="aelithia")
        self.assertIsNotNone(fb_ael)
        self.assertEqual(fb_ael.loop_id, "aelithia_fallback_cozy")

    def test_no_monochrome_loops_in_best_loop_selection(self):
        """Synthetic monochrome loops (lighthouse / arctic desolation) are never returned over cinematic loops."""
        f_cine = self._create_dummy_video("loops/cinematic_forest.mp4")
        f_mono = self._create_dummy_video("loops/loop_maritime_lighthouse_horizontal_544374.mp4")

        self.repo.register_loop(LoopRecord(
            loop_id="loop_maritime_lighthouse_h_544374",
            category="maritime_lighthouse",
            technology="ffmpeg_lavfi",
            orientation="horizontal",
            width=1920,
            height=1080,
            duration_sec=6.0,
            fps=30,
            file_path=f_mono,
            file_size_bytes=30_000,
            sha256="procedural",
            usage_count=0,
        ))
        self.repo.register_loop(LoopRecord(
            loop_id="cinematic_horror_forest",
            category="dark_forest",
            technology="pre-rendered",
            orientation="horizontal",
            width=1920,
            height=1080,
            duration_sec=6.0,
            fps=30,
            file_path=f_cine,
            file_size_bytes=30_000,
            sha256="sha_cine",
            usage_count=5,
        ))

        picked = self.repo.get_best_loop("unknown_hypothetical_theme", orientation="horizontal")
        self.assertIsNotNone(picked)
        self.assertEqual(picked.loop_id, "cinematic_horror_forest")
        self.assertNotEqual(picked.technology, "ffmpeg_lavfi")

    def test_purge_synthetic_monochrome_loops(self):
        """Synthetic monochrome loops are purged from database."""
        f_mono = self._create_dummy_video("loops/loop_maritime_lighthouse_horizontal_544374.mp4")
        self.repo.register_loop(LoopRecord(
            loop_id="loop_maritime_lighthouse_h_544374",
            category="maritime_lighthouse",
            technology="ffmpeg_lavfi",
            orientation="horizontal",
            width=1920,
            height=1080,
            duration_sec=6.0,
            fps=30,
            file_path=f_mono,
            file_size_bytes=30_000,
            sha256="procedural",
            usage_count=0,
        ))
        self.assertIsNotNone(self.repo.get_loop_by_id("loop_maritime_lighthouse_h_544374"))
        deleted = self.repo.purge_synthetic_monochrome_loops()
        self.assertGreaterEqual(deleted, 1)
        self.assertIsNone(self.repo.get_loop_by_id("loop_maritime_lighthouse_h_544374"))

