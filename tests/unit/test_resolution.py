"""
Unit tests for the single source of truth for render resolutions (src/core/resolution.py).

Every resolution-dependent artifact (SCP renderer, daemon shorts ASS canvas, prepublication
gate, template presets, contact-sheet scoring, 5-cycle audit) consumes these constants so
the short-mode target can never drift from 768x1360 again.
"""
import pytest

from src.core.resolution import (
    LONGFORM_RESOLUTION,
    SHORT_RESOLUTION,
    SHORT_RESOLUTION_TEST,
    is_short_resolution,
)


class TestResolutionConstants:

    def test_short_resolution_is_720x1280(self):
        assert SHORT_RESOLUTION == (1080, 1920)

    def test_short_resolution_test_scale_is_360x640(self):
        assert SHORT_RESOLUTION_TEST == (540, 960)

    def test_longform_resolution_is_1920x1080(self):
        assert LONGFORM_RESOLUTION == (1920, 1080)


class TestIsShortResolution:

    def test_full_short_render_detected(self):
        assert is_short_resolution(1080, 1920) is True

    def test_test_scale_short_render_detected(self):
        assert is_short_resolution(540, 960) is True

    def test_longform_render_rejected(self):
        assert is_short_resolution(1280, 720) is False

    def test_legacy_768x1360_rejected(self):
        assert is_short_resolution(768, 1360) is False

    def test_swapped_dimensions_rejected(self):
        # 1280x720 is not a short-mode canvas
        assert is_short_resolution(1280, 720) is False
