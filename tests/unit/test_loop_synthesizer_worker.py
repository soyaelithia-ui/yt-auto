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
        call_kwargs = self.mock_renderer.render_loop.call_args[1]
        self.assertEqual(call_kwargs.get("category"), "scp")
        self.assertEqual(call_kwargs.get("orientation"), "vertical")
        self.assertEqual(call_kwargs.get("seed"), 42)

    def test_maintain_buffer_fills_stock_to_target(self):
        self._create_dummy_loop("c1", "cosmic_horror", "vertical")

        def fake_render(category, orientation="vertical", duration_sec=6.0, fps=30, seed=42, register_in_db=True, **kwargs):
            f = Path(self.temp_dir.name) / f"{category}_{orientation}_{seed}.mp4"
            f.write_bytes(b"data")
            rec = LoopRecord(
                loop_id=f"loop_{category}_{orientation}_{seed}",
                category=category,
                technology="canvas2d",
                orientation=orientation,
                width=1080 if orientation == "vertical" else 1920,
                height=1920 if orientation == "vertical" else 1080,
                duration_sec=duration_sec,
                fps=fps,
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
