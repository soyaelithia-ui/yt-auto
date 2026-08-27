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

    def _create_dummy_video(self, name: str, size: int = 1024) -> str:
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
