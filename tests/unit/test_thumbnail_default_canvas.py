"""Default thumbnail canvas is 720p (16:9 1280×720 / 9:16 720×1280)."""

from src.media.thumbnails.engine import (
    THUMB_LONGFORM_SIZE,
    THUMB_SHORT_SIZE,
    ThumbnailConfig,
    default_thumbnail_canvas,
)


def test_default_thumbnail_canvas_720p():
    assert default_thumbnail_canvas() == (1280, 720)
    assert default_thumbnail_canvas(vertical=False) == THUMB_LONGFORM_SIZE
    assert default_thumbnail_canvas(vertical=True) == THUMB_SHORT_SIZE
    assert default_thumbnail_canvas(vertical=True) == (720, 1280)


def test_full_hd_opt_in_only():
    assert default_thumbnail_canvas(full_hd=True) == (1920, 1080)
    assert default_thumbnail_canvas(vertical=True, full_hd=True) == (1080, 1920)


def test_thumbnail_config_defaults_are_720p():
    cfg = ThumbnailConfig(title="X")
    assert (cfg.width, cfg.height) == (1280, 720)
