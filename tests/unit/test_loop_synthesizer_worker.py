"""
Unit tests for LoopSynthesizerWorker (src/media/loop_synthesizer_worker.py).

Covers:
1. Counting loops per category/orientation.
2. Synthesizing on demand.
3. Maintaining loop buffer up to target stock.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.core.catalog import LoopCatalogRepository, LoopRecord
from src.media.loop_worker import LoopSynthesizerWorker
from src.media.web_renderer import RenderSpec


class TestLoopSynthesizerWorker(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_loops.db")
        self.catalog = LoopCatalogRepository(db_path=self.db_path)
        self.mock_renderer = MagicMock()
        self.worker = LoopSynthesizerWorker(
            db_path=self.db_path,
            renderer=self.mock_renderer,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_dummy_loop(self, loop_id: str, category: str, orientation: str) -> LoopRecord:
        f = Path(self.temp_dir.name) / f"{loop_id}.mp4"
        f.write_bytes(b"dummy_video_bytes")
        rec = LoopRecord(
            loop_id=loop_id,
            category=category,
            technology="webgl_shader",
            orientation=orientation,
            width=1080,
            height=1920,
            duration_sec=6.0,
            fps=30,
            file_path=str(f),
            file_size_bytes=len(b"dummy_video_bytes"),
            sha256="abc",
        )
        self.catalog.register_loop(rec)
        return rec

    def test_count_loops_for_category(self):
        self.assertEqual(self.worker.count_loops_for_category("cosmic_horror", "vertical"), 0)
        self._create_dummy_loop("c1", "cosmic_horror", "vertical")
        self.assertEqual(self.worker.count_loops_for_category("cosmic_horror", "vertical"), 1)
        self.assertEqual(self.worker.count_loops_for_category("cosmic_horror", "horizontal"), 0)

    def test_synthesize_on_demand_invokes_renderer(self):
        dummy_rec = LoopRecord(
            loop_id="web_scp_v_123",
            category="scp",
            technology="css_motion",
            orientation="vertical",
            width=1080,
            height=1920,
            duration_sec=6.0,
            fps=30,
            file_path="/tmp/fake.mp4",
            file_size_bytes=1000,
            sha256="123",
        )
        self.mock_renderer.render_loop.return_value = dummy_rec

        rec = self.worker.synthesize_on_demand("scp", orientation="vertical", seed=42)
        self.assertEqual(rec.loop_id, "web_scp_v_123")
        self.mock_renderer.render_loop.assert_called_once()
        spec_arg = self.mock_renderer.render_loop.call_args[0][0]
        self.assertEqual(spec_arg.category, "scp")
        self.assertEqual(spec_arg.orientation, "vertical")
        self.assertEqual(spec_arg.seed, 42)

    def test_maintain_buffer_fills_stock_to_target(self):
        self._create_dummy_loop("c1", "cosmic_horror", "vertical")

        def fake_render(spec, register_in_db=True):
            f = Path(self.temp_dir.name) / f"{spec.category}_{spec.orientation}_{spec.seed}.mp4"
            f.write_bytes(b"data")
            rec = LoopRecord(
                loop_id=f"loop_{spec.category}_{spec.orientation}_{spec.seed}",
                category=spec.category,
                technology="canvas2d",
                orientation=spec.orientation,
                width=spec.width,
                height=spec.height,
                duration_sec=spec.duration_sec,
                fps=spec.fps,
                file_path=str(f),
                file_size_bytes=4,
                sha256="fake_sha",
            )
            if register_in_db:
                self.catalog.register_loop(rec)
            return rec

        self.mock_renderer.render_loop.side_effect = fake_render

        # Target: 2 per category, testing 2 categories: cosmic_horror and monsters, 1 orientation: vertical
        res = self.worker.maintain_buffer(
            target_per_category=2,
            categories=["cosmic_horror", "monsters"],
            orientations=["vertical"],
        )

        # cosmic_horror already had 1 -> needed 1
        # monsters had 0 -> needed 2
        # Total generated = 3
        self.assertEqual(res["generated_count"], 3)
        self.assertEqual(self.worker.count_loops_for_category("cosmic_horror", "vertical"), 2)
        self.assertEqual(self.worker.count_loops_for_category("monsters", "vertical"), 2)
