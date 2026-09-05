"""Smoke tests for analog-horror thumbnail grade (Aelithia quality bar)."""
from __future__ import annotations

from PIL import Image

from src.media.thumbnails.analog_horror import apply_analog_horror_grade, draw_camcorder_osd


def test_analog_horror_grade_preserves_size_and_rgb():
    base = Image.new("RGB", (320, 568), (40, 50, 45))
    out = apply_analog_horror_grade(base, target_size=(320, 568), seed=1)
    assert out.size == (320, 568)
    assert out.mode == "RGB"


def test_camcorder_osd_composites():
    base = Image.new("RGB", (640, 360), (20, 25, 22))
    out = draw_camcorder_osd(base, cam_label="CAM 01 [TEST]", date_label="1994-10-31")
    assert out.size == (640, 360)
