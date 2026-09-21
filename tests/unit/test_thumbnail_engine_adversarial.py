"""
tests/unit/test_thumbnail_engine_adversarial.py - Adversarial Stress Harness for ResilientThumbnailEngine.

Empirical verification suite challenging boundaries, unusual inputs, aspect ratios,
color formats, font fallbacks, background image corruptions, and QA auditor gating.
"""
from __future__ import annotations

import os
from pathlib import Path
import pytest
from PIL import Image

from src.media.thumbnail_engine import ResilientThumbnailEngine
from src.verification.technical_qa import TechnicalQAAuditor as VisualAudioQAAuditorAgent


@pytest.fixture
def engine() -> ResilientThumbnailEngine:
    return ResilientThumbnailEngine()


@pytest.fixture
def qa_auditor() -> VisualAudioQAAuditorAgent:
    return VisualAudioQAAuditorAgent()


class TestThumbnailTitlesAndTextAdversarial:
    """Stress-tests title strings, special characters, unicode, and extreme lengths."""

    def test_empty_and_none_titles_produce_valid_image(self, engine: ResilientThumbnailEngine, tmp_path: Path):
        out = tmp_path / "empty_titles.jpg"
        res = engine.generate(
            out,
            title_main="",
            title_sub="",
            highlight_box="",
            badge_text="",
        )
        assert res.is_file()
        assert res.stat().st_size > 40 * 1024
        with Image.open(res) as img:
            assert img.size == (1280, 720)
            assert img.mode == "RGB"
            assert img.format == "JPEG"

    def test_none_value_titles_produce_valid_image(self, engine: ResilientThumbnailEngine, tmp_path: Path):
        out = tmp_path / "none_titles.jpg"
        res = engine.generate(
            out,
            title_main=None,
            title_sub=None,
            highlight_box=None,
            badge_text=None,
        )
        assert res.is_file()
        assert res.stat().st_size > 40 * 1024

    def test_unicode_emojis_and_multilingual_scripts(self, engine: ResilientThumbnailEngine, tmp_path: Path):
        scripts = [
            ("spanish", "¡¿EL MONSTRUO DEL BOSQUE OSCURO?!", "NÚMERO 1 // CLASIFICADO"),
            ("emojis", "🔥🚨 SCP-999: EL AMIGO DEFINITIVO 💀👽", "SUPERVIVENCIA 100%"),
            ("cyrillic", "ОБЪЕКТ SCP-2000: ДЕУС ЭКС МАХИНА", "СЕКРЕТНО // УРОВЕНЬ 5"),
            ("japanese", "東京タワー地下の秘密研究施設", "最高機密 // レベル5"),
            ("arabic", "تقرير سرّي للغاية: التجربة رقم ٩", "سري للغاية"),
            ("zalgo", "S̷C̶P̸-̶0̵9̵6̷ ̸I̵S̷ ̴L̶O̶O̸K̵I̷N̸G̵", "R̷E̴D̶A̸C̸T̷E̶D̵"),
            ("null_and_control", "SCP-173\0\r\n\tDEUS", "SAFE\0LEVEL"),
        ]
        for tag, title_m, title_s in scripts:
            out = tmp_path / f"script_{tag}.jpg"
            res = engine.generate(out, title_main=title_m, title_sub=title_s)
            assert res.is_file()
            assert res.stat().st_size > 40 * 1024
            with Image.open(res) as img:
                assert img.size == (1280, 720)

    def test_extreme_length_titles(self, engine: ResilientThumbnailEngine, tmp_path: Path):
        out = tmp_path / "extreme_title.jpg"
        long_title = "SCP " + "VERY LONG PHRASE " * 100
        res = engine.generate(out, title_main=long_title, title_sub=long_title)
        assert res.is_file()
        assert res.stat().st_size > 40 * 1024
        with Image.open(res) as img:
            assert img.size == (1280, 720)


class TestThumbnailDimensionsAndAspectRatios:
    """Stress-tests dimension boundaries, aspect ratios, and orientations."""

    @pytest.mark.parametrize(
        "width,height,desc",
        [
            (1280, 720, "16:9 Standard Longform"),
            (1920, 1080, "16:9 Full HD"),
            (720, 1280, "9:16 Standard Shorts"),
            (1080, 1920, "9:16 Full HD Shorts"),
            (1080, 1080, "1:1 Square"),
            (2560, 1080, "21:9 Ultrawide"),
            (320, 180, "Low resolution 16:9"),
            (100, 100, "Tiny square"),
            (10, 10, "Extreme miniature"),
            (10, 1000, "Extreme needle vertical"),
            (1000, 10, "Extreme needle horizontal"),
        ],
    )
    def test_valid_and_nonstandard_canvas_sizes(
        self, engine: ResilientThumbnailEngine, tmp_path: Path, width: int, height: int, desc: str
    ):
        out = tmp_path / f"dim_{width}_{height}.jpg"
        res = engine.generate(out, width=width, height=height)
        assert res.is_file()
        assert res.stat().st_size > 0
        with Image.open(res) as img:
            assert img.size == (width, height)
            assert img.mode == "RGB"

    @pytest.mark.parametrize(
        "width,height",
        [
            (0, 720),
            (1280, 0),
            (-100, 720),
            (1280, -50),
        ],
    )
    def test_non_positive_dimensions_fail_cleanly(
        self, engine: ResilientThumbnailEngine, tmp_path: Path, width: int, height: int
    ):
        out = tmp_path / f"invalid_{width}_{height}.jpg"
        with pytest.raises(ValueError):
            engine.generate(out, width=width, height=height)


class TestThumbnailColorsAndFormatting:
    """Stress-tests accent color parsing, fallbacks, and boundary conditions."""

    def test_standard_and_boundary_color_representations(
        self, engine: ResilientThumbnailEngine, tmp_path: Path
    ):
        colors = [
            ("rgb_standard", (0, 255, 180)),
            ("rgb_black", (0, 0, 0)),
            ("rgb_white", (255, 255, 255)),
            ("rgba_tuple", (0, 255, 180, 255)),
            ("hex_standard", "#00ffb4"),
            ("hex_short", "#0fb"),
            ("hex_uppercase", "#00FFB4"),
            ("named_color", "cyan"),
            ("none_color", None),
            ("invalid_hex", "#GGGGGG"),
            ("invalid_string", "not-a-color"),
            ("empty_string", ""),
            ("integer_representation", 123456),
            ("out_of_bounds_tuple", (300, -10, 500)),
        ]
        for tag, col in colors:
            out = tmp_path / f"color_{tag}.jpg"
            res = engine.generate(out, accent_color=col)
            assert res.is_file()
            assert res.stat().st_size > 40 * 1024

    def test_incomplete_tuple_raises_index_error(
        self, engine: ResilientThumbnailEngine, tmp_path: Path
    ):
        """Documented failure mode: tuple with < 3 elements raises IndexError."""
        out = tmp_path / "incomplete_tuple.jpg"
        with pytest.raises(IndexError):
            engine.generate(out, accent_color=(255, 0))

    def test_float_tuple_raises_value_error(
        self, engine: ResilientThumbnailEngine, tmp_path: Path
    ):
        """Documented failure mode: tuple of floats raises ValueError on hex formatting."""
        out = tmp_path / "float_tuple.jpg"
        with pytest.raises(ValueError):
            engine.generate(out, accent_color=(0.5, 1.0, 0.2))


class TestThumbnailBackgroundFallbacksAndCorruptions:
    """Stress-tests background image ingestion, format conversions, and corruption resilience."""

    def test_missing_background_falls_back_to_atmospheric_gradient(
        self, engine: ResilientThumbnailEngine, tmp_path: Path
    ):
        out = tmp_path / "missing_bg.jpg"
        res = engine.generate(out, background_image=tmp_path / "does_not_exist.jpg")
        assert res.is_file()
        assert res.stat().st_size > 40 * 1024

    def test_corrupted_zero_byte_background(
        self, engine: ResilientThumbnailEngine, tmp_path: Path
    ):
        zero_p = tmp_path / "zero.jpg"
        zero_p.write_bytes(b"")
        out = tmp_path / "out_zero.jpg"
        res = engine.generate(out, background_image=zero_p)
        assert res.is_file()
        assert res.stat().st_size > 40 * 1024

    def test_corrupted_garbage_bytes_background(
        self, engine: ResilientThumbnailEngine, tmp_path: Path
    ):
        garbage_p = tmp_path / "garbage.jpg"
        garbage_p.write_bytes(b"NOT A VALID JPEG OR PNG AT ALL HELLO WORLD")
        out = tmp_path / "out_garbage.jpg"
        res = engine.generate(out, background_image=garbage_p)
        assert res.is_file()
        assert res.stat().st_size > 40 * 1024

    def test_various_image_modes_and_dimensions(
        self, engine: ResilientThumbnailEngine, tmp_path: Path
    ):
        modes = [
            ("rgba", Image.new("RGBA", (800, 600), (255, 50, 50, 128)), "PNG"),
            ("gray", Image.new("L", (800, 600), 128), "PNG"),
            ("cmyk", Image.new("CMYK", (800, 600), (0, 255, 255, 0)), "JPEG"),
            ("tiny", Image.new("RGB", (2, 2), (200, 200, 200)), "PNG"),
            ("giant", Image.new("RGB", (3000, 3000), (30, 40, 50)), "PNG"),
        ]
        for tag, img, fmt in modes:
            src_p = tmp_path / f"src_{tag}.{fmt.lower()}"
            img.save(src_p, fmt)
            out_p = tmp_path / f"out_{tag}.jpg"
            res = engine.generate(out_p, background_image=src_p)
            assert res.is_file()
            assert res.stat().st_size > 30 * 1024
            with Image.open(res) as out_img:
                assert out_img.size == (1280, 720)
                assert out_img.mode == "RGB"


class TestThumbnailFontResolutionAndCandidates:
    """Stress-tests font candidates list and dynamic font resolution."""

    def test_nonexistent_custom_font_candidates_fallback_gracefully(self):
        engine = ResilientThumbnailEngine(custom_font_paths=["/path/to/fake_font_12345.ttf"])
        assert "/path/to/fake_font_12345.ttf" in engine.font_candidates
        fnt = engine.resolve_font(size=48)
        assert fnt is not None

    @pytest.mark.parametrize("size", [1, 0, -10, 48, 120, 1000])
    def test_resolve_font_size_boundaries(self, size: int):
        engine = ResilientThumbnailEngine()
        fnt = engine.resolve_font(size=size)
        assert fnt is not None


class TestThumbnailOutputAndQualityAuditor:
    """Tests compliance with VisualAudioQAAuditorAgent and file system output handling."""

    def test_qa_auditor_compliance_16_9_horizontal(
        self, engine: ResilientThumbnailEngine, qa_auditor: VisualAudioQAAuditorAgent, tmp_path: Path
    ):
        out = tmp_path / "qa_16_9.jpg"
        res = engine.generate(
            out,
            title_main="SCP-2000",
            title_sub="DEUS EX MACHINA",
            highlight_box="REINICIO DE LA HUMANIDAD",
            badge_text="NIVEL 5 // TOP SECRET",
            width=1280,
            height=720,
        )
        passed, errors = qa_auditor.audit_thumbnail(res)
        assert passed is True, f"QA audit failed on 16:9 thumbnail: {errors}"
        assert len(errors) == 0

    def test_qa_auditor_compliance_1080p_9_16_vertical(
        self, engine: ResilientThumbnailEngine, qa_auditor: VisualAudioQAAuditorAgent, tmp_path: Path
    ):
        out = tmp_path / "qa_9_16_fhd.jpg"
        res = engine.generate(
            out,
            title_main="SCP-999",
            title_sub="MONSTRUO AMIGABLE",
            highlight_box="CRIATURA VIVIENTE",
            badge_text="SEGURO",
            width=1080,
            height=1920,
        )
        passed, errors = qa_auditor.audit_thumbnail(res)
        assert passed is True, f"QA audit failed on 1080x1920 Shorts thumbnail: {errors}"
        assert len(errors) == 0

    def test_nested_directories_auto_created(
        self, engine: ResilientThumbnailEngine, tmp_path: Path
    ):
        deep_out = tmp_path / "dir1" / "dir2" / "nested" / "thumb.jpg"
        res = engine.generate(deep_out)
        assert res.is_file()
