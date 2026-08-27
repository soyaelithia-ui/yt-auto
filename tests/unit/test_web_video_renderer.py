"""
Unit tests for WebVideoRenderer (src/media/web_video_renderer.py).

Covers:
1. RenderSpec resolution and parameter assignment.
2. Template path resolution for thematic categories.
3. Preview thumbnail generation.
4. Deterministic short loop rendering and SQLite catalog registration.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from src.core.catalog import LoopCatalogRepository
from src.media.web_renderer import (
    CATEGORY_TAGS_MAP,
    CATEGORY_TECH_MAP,
    RenderSpec,
    THEMATIC_TEMPLATES,
    WebVideoRenderer,
)


class TestWebVideoRenderer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_loops.db")
        self.output_dir = os.path.join(self.temp_dir.name, "output_loops")
        self.renderer = WebVideoRenderer(
            output_loops_dir=self.output_dir,
            db_path=self.db_path,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_render_spec_orientations(self):
        spec_v = RenderSpec(category="cosmic_horror", orientation="vertical")
        self.assertEqual(spec_v.width, 1080)
        self.assertEqual(spec_v.height, 1920)
        self.assertEqual(spec_v.orientation, "vertical")

        spec_h = RenderSpec(category="cosmic_horror", orientation="horizontal")
        self.assertEqual(spec_h.width, 1920)
        self.assertEqual(spec_h.height, 1080)
        self.assertEqual(spec_h.orientation, "horizontal")

        spec_169 = RenderSpec(category="monsters", orientation="16:9")
        self.assertEqual(spec_169.orientation, "horizontal")
        self.assertEqual(spec_169.width, 1920)

    def test_resolve_template_path(self):
        for cat, tmpl in THEMATIC_TEMPLATES.items():
            p = self.renderer.resolve_template_path(cat)
            self.assertTrue(p.is_file(), f"Template for {cat} must exist on disk: {p}")

        # Unknown category falls back to cosmic_horror_three.html
        fb = self.renderer.resolve_template_path("unknown_space_dimension")
        self.assertTrue(fb.is_file())
        self.assertEqual(fb.name, "cosmic_horror_three.html")

    def test_render_preview_image(self):
        preview_path = os.path.join(self.temp_dir.name, "preview_test.png")
        out = self.renderer.render_preview_image(
            category="scp",
            output_image_path=preview_path,
            orientation="vertical",
            seed=42,
        )
        self.assertTrue(out.is_file())
        self.assertGreater(out.stat().st_size, 1000)

    def test_render_short_loop_and_verify(self):
        spec = RenderSpec(
            category="drama_aita",
            orientation="horizontal",
            duration_sec=1.0,
            fps=15,
            seed=99,
        )
        rec = self.renderer.render_loop(spec, register_in_db=True)
        self.assertTrue(Path(rec.file_path).is_file())
        self.assertGreater(rec.file_size_bytes, 1000)
        self.assertEqual(rec.category, "drama_aita")
        self.assertEqual(rec.orientation, "horizontal")
        self.assertEqual(rec.width, 1920)
        self.assertEqual(rec.height, 1080)
        self.assertEqual(rec.fps, 15)

        # Check DB entry
        catalog = LoopCatalogRepository(db_path=self.db_path)
        in_db = catalog.get_loop_by_id(rec.loop_id)
        self.assertIsNotNone(in_db)
        self.assertEqual(in_db.file_path, rec.file_path)
