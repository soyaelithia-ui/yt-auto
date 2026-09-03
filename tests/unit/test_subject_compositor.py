"""
tests/unit/test_subject_compositor.py - Unit tests for AdaptiveSubjectCompositor.
"""
import pytest
from PIL import Image
from src.media.thumbnails.subject_extractor import AdaptiveSubjectCompositor, RimLightCompositor


class TestAdaptiveSubjectCompositor:
    @pytest.fixture
    def sample_canvas_vertical(self):
        return Image.new("RGB", (1080, 1920), color=(20, 25, 35))

    @pytest.fixture
    def sample_canvas_horizontal(self):
        return Image.new("RGB", (1280, 720), color=(15, 20, 30))

    def test_all_archetypes_render_cleanly(self, sample_canvas_vertical):
        archetypes = [
            "maritime_lighthouse",
            "tactical_chamber",
            "dark_forest",
            "arctic_desolation",
            "cosmic_singularity",
            "arcade_vector_flight",
            "parkour_runner",
            "cozy_hearth",
            "synaptic_network",
        ]
        for arch in archetypes:
            res = AdaptiveSubjectCompositor.composite_thematic_subject(
                base_img=sample_canvas_vertical,
                channel_id="moku",
                archetype=arch,
                accent_color_hex="#00FF66",
                intensity=0.8,
            )
            assert res is not None
            assert res.size == (1080, 1920)
            assert res.mode == "RGB"

    def test_horizontal_resolution_support(self, sample_canvas_horizontal):
        res = AdaptiveSubjectCompositor.composite_thematic_subject(
            base_img=sample_canvas_horizontal,
            channel_id="aelithia",
            archetype="cozy_hearth",
            accent_color_hex="#E0AAFF",
            intensity=0.75,
        )
        assert res.size == (1280, 720)

    def test_legacy_wrapper_delegation(self, sample_canvas_vertical):
        rgb = RimLightCompositor.hex_to_rgb("#00FF66")
        assert rgb == (0, 255, 102)

    def test_focal_area_pixel_modification(self, sample_canvas_vertical):
        # Verify that pixels in the focal center were modified (composite happened)
        res = AdaptiveSubjectCompositor.composite_thematic_subject(
            base_img=sample_canvas_vertical.copy(),
            channel_id="moku",
            archetype="tactical_chamber",
            accent_color_hex="#FF3300",
            intensity=1.0,
        )
        base_pixels = list(sample_canvas_vertical.crop((400, 800, 680, 1200)).tobytes())
        res_pixels = list(res.crop((400, 800, 680, 1200)).tobytes())
        assert base_pixels != res_pixels
