"""CTR anti-cases: no NONE badges, 2-line wrap, no neon glow, OSD off by default."""
from __future__ import annotations

import inspect
import re
from typing import List
from unittest.mock import patch

import pytest
from PIL import Image, ImageDraw

from src.media.thumbnails.engine import ThumbnailConfig, ThumbnailEngine
from src.media.thumbnails.grading import ChiaroscuroColorGrader
from src.media.thumbnails.layout import AspectLayoutManager
from src.media.thumbnails.layouts.analog_horror import AnalogHorrorVhsLayout
from src.media.thumbnails.layouts.cinematic import (
    GeneralCinematicLayout,
    badge_label,
    detect_thumbnail_niche,
)
from src.media.thumbnails.typography import DynamicTypographyEngine

AITA_FIXTURE = "AITA POR REVELAR EL SECRETO DE LA FAMILIA"
_NONE_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])NONE(?![A-Za-z0-9])", re.IGNORECASE)


def _contains_none_token(text: str) -> bool:
    return bool(_NONE_TOKEN_RE.search(text or ""))


def _assert_word_bounded(original: str, lines: List[str]) -> None:
    orig_words = original.replace("…", " ").split()
    orig_set = set(orig_words)
    assert len(lines) <= 2
    rendered: List[str] = []
    for line in lines:
        for word in line.replace("…", " ").split():
            if not word:
                continue
            assert word in orig_set, f"broken word {word!r} in {line!r}"
            rendered.append(word)
    assert rendered, "expected at least one rendered word"


@pytest.fixture
def spy_draw_text(monkeypatch: pytest.MonkeyPatch):
    drawn: List[str] = []
    real = ImageDraw.ImageDraw.text

    def wrapped(self, xy, text, *args, **kwargs):
        drawn.append(str(text))
        return real(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", wrapped)
    return drawn


def test_badge_label_omits_none_and_placeholders():
    for raw in (None, "", "NONE", "none", "None", "NULL", "null", "N/A", "n/a", "HISTORIA EXCLUSIVA"):
        assert badge_label(raw) is None
        assert badge_label(raw, niche="aita") is None
        assert badge_label(raw, niche="scp") is None
        assert badge_label(raw, niche="other") is None


def test_aita_verdict_badge_only():
    assert detect_thumbnail_niche(channel_id="aelithia-aita-long", archetype="aita") == "aita"
    assert badge_label("YTA", niche="aita") == "YTA"
    assert badge_label("nta", niche="aita") == "NTA"
    assert badge_label("ESH", channel_id="aelithia") == "ESH"
    assert badge_label("INFO", lane_id="reddit") == "INFO"
    assert badge_label("NONE", niche="aita") is None
    assert badge_label("CONFESIÓN ANÓNIMA", niche="aita") is None


def test_scp_class_badge_only():
    assert detect_thumbnail_niche(channel_id="moku-scp-shorts", archetype="scp") == "scp"
    assert badge_label("KETER", niche="scp") == "KETER"
    assert badge_label("euclid", channel_id="moku-scp-shorts") == "EUCLID"
    assert badge_label("SAFE", lane_id="scp") == "SAFE"
    assert badge_label("NONE", niche="scp") is None
    assert badge_label("THAUMIEL", niche="scp") is None


def test_horror_tape_badge_requires_explicit_tape_id():
    assert badge_label(None, niche="horror") is None
    assert badge_label("NONE", niche="horror") is None
    assert badge_label(None, niche="horror", tape_id="TAPE-04") == "ADVERTENCIA · TAPE-04"
    # Placeholder is valid only when explicitly provided.
    assert (
        badge_label(None, niche="horror", tape_id="TAPE-04 // ARCHIVE")
        == "ADVERTENCIA · TAPE-04 // ARCHIVE"
    )


def test_category_none_never_paints_badge(spy_draw_text):
    layout = GeneralCinematicLayout()
    canvas = Image.new("RGB", (1920, 1080), (18, 18, 22))
    safe = AspectLayoutManager.get_safe_zone(1920, 1080)
    for category in ("NONE", "none", "null", "", None):
        spy_draw_text.clear()
        assert badge_label(category, niche="aita") is None
        layout.apply_layout(
            canvas=canvas,
            title="TITULO REAL DE PRUEBA",
            channel_id="aelithia",
            safe_zone=safe,
            metadata={"category": category, "text_box_style": "badge"},
        )
        assert not any(_contains_none_token(t) for t in spy_draw_text), spy_draw_text


def test_engine_category_none_omits_badge(tmp_path, spy_draw_text):
    engine = ThumbnailEngine()
    out = tmp_path / "none_badge.jpg"
    assert badge_label("NONE", channel_id="aelithia") is None
    engine.generate(
        ThumbnailConfig(
            title="CONFESION SIN VEREDICTO",
            channel_id="aelithia",
            output_path=out,
            width=1280,
            height=720,
            metadata={"category": "NONE"},
        )
    )
    assert not any(_contains_none_token(t) for t in spy_draw_text), spy_draw_text


def test_aita_yta_renders_and_none_omitted(spy_draw_text):
    layout = GeneralCinematicLayout()
    canvas = Image.new("RGB", (1920, 1080), (20, 20, 24))
    safe = AspectLayoutManager.get_safe_zone(1920, 1080)

    spy_draw_text.clear()
    layout.apply_layout(
        canvas=canvas,
        title="¿SOY LA MALA?",
        channel_id="aelithia",
        safe_zone=safe,
        metadata={"category": "YTA", "text_box_style": "badge"},
    )
    assert any("YTA" in t.upper() for t in spy_draw_text)

    spy_draw_text.clear()
    layout.apply_layout(
        canvas=canvas,
        title="¿SOY LA MALA?",
        channel_id="aelithia",
        safe_zone=safe,
        metadata={"category": "NONE", "text_box_style": "badge"},
    )
    assert not any(_contains_none_token(t) for t in spy_draw_text)
    assert not any("YTA" in t.upper().split() for t in spy_draw_text)


def test_scp_keter_renders_and_none_omitted(spy_draw_text):
    layout = GeneralCinematicLayout()
    canvas = Image.new("RGB", (1080, 1920), (12, 16, 20))
    safe = AspectLayoutManager.get_safe_zone(1080, 1920)

    spy_draw_text.clear()
    layout.apply_layout(
        canvas=canvas,
        title="SCP-173 BRECHA",
        channel_id="moku-scp-shorts",
        safe_zone=safe,
        metadata={"category": "KETER", "archetype": "scp", "text_box_style": "badge"},
        lane_id="moku-scp-shorts",
    )
    assert any("KETER" in t.upper() for t in spy_draw_text)

    spy_draw_text.clear()
    layout.apply_layout(
        canvas=canvas,
        title="SCP-173 BRECHA",
        channel_id="moku-scp-shorts",
        safe_zone=safe,
        metadata={"category": "NONE", "archetype": "scp", "text_box_style": "badge"},
        lane_id="moku-scp-shorts",
    )
    assert not any(_contains_none_token(t) for t in spy_draw_text)
    assert not any("KETER" in t.upper().split() for t in spy_draw_text)


def test_wrap_two_lines_word_bounded_aita_fixture(spy_draw_text):
    lines = DynamicTypographyEngine.split_title_to_safe_lines(AITA_FIXTURE)
    assert len(lines) <= 2
    _assert_word_bounded(AITA_FIXTURE, lines)
    assert " ".join(lines) != "AITA POR REVELAR EL"
    assert "SECRETO" in " ".join(lines)
    assert "FAMILIA" in " ".join(lines)
    assert " ".join(lines).split() == AITA_FIXTURE.split()

    canvas = Image.new("RGB", (1920, 1080), (8, 8, 10))
    safe = AspectLayoutManager.get_safe_zone(1920, 1080)
    spy_draw_text.clear()
    DynamicTypographyEngine.draw_text_with_effects(
        canvas=canvas,
        text=AITA_FIXTURE,
        pos_x=safe.left,
        pos_y=safe.top + 80,
        max_width=int(safe.width * 0.92),
        font_size=90,
        glow_color=None,
        glow_radius=0,
        tilt_angle=0.0,
    )
    title_lines: List[str] = []
    for text in spy_draw_text:
        if any(word in text.split() for word in AITA_FIXTURE.split()):
            if text not in title_lines:
                title_lines.append(text)
    assert 1 <= len(title_lines) <= 2
    _assert_word_bounded(AITA_FIXTURE, title_lines)
    joined = " ".join(title_lines)
    assert joined != "AITA POR REVELAR EL"
    assert "SECRETO" in joined
    assert "FAMILIA" in joined

    hook = ThumbnailEngine._extract_hook_text(AITA_FIXTURE)
    assert hook != "AITA POR REVELAR EL"
    assert "SECRETO" in hook and "FAMILIA" in hook


def test_extract_hook_text_drama_motifs_and_length_bounds():
    # 1. Boda motif
    h_boda = ThumbnailEngine._extract_hook_text(
        "¿Soy la mala por negarme a ir a la boda de mi hermana porque invitó a mi agresor?"
    )
    assert h_boda == "¿ARRUINÉ SU BODA?"

    # 2. Apartamento / herencia motif
    h_apt = ThumbnailEngine._extract_hook_text(
        "¿Soy la mala por negarme a vender mi apartamento heredado para pagar las deudas de mi hermano?"
    )
    assert h_apt == "¿VENDER MI CASA?"

    # 3. Deudas motif
    h_deudas = ThumbnailEngine._extract_hook_text(
        "AITA por negarme a pagar la fianza y las deudas de mi primo irresponsable"
    )
    assert h_deudas == "¿PAGAR SUS DEUDAS?"

    # 4. Long arbitrary title bounded to <= 38 chars strictly at word boundary
    long_title = "ESTA ES UNA HISTORIA TOTALMENTE VERÍDICA QUE NUNCA ANTES HABÍA SIDO CONTADA EN NINGUNA PARTE"
    h_long = ThumbnailEngine._extract_hook_text(long_title)
    assert len(h_long) <= 38
    # No word slicing
    for w in h_long.split():
        assert w in long_title.split()


def test_ctr_layout_disables_glow_and_tilt(monkeypatch: pytest.MonkeyPatch):
    captured = []
    orig = DynamicTypographyEngine.draw_text_with_effects

    def spy(*args, **kwargs):
        captured.append(kwargs)
        return orig(*args, **kwargs)

    monkeypatch.setattr(DynamicTypographyEngine, "draw_text_with_effects", spy)

    sig = inspect.signature(orig)
    assert sig.parameters["glow_color"].default is None
    assert sig.parameters["glow_radius"].default == 0

    safe = AspectLayoutManager.get_safe_zone(1920, 1080)
    cinematic = GeneralCinematicLayout()
    cinematic.apply_layout(
        canvas=Image.new("RGB", (1920, 1080), (16, 16, 18)),
        title="TITULO CTR",
        channel_id="aelithia",
        safe_zone=safe,
        metadata={"category": "YTA", "accent_color": "#00FF66", "primary_color": "#FF003B"},
    )
    analog = AnalogHorrorVhsLayout()
    analog.apply_layout(
        canvas=Image.new("RGB", (1920, 1080), (10, 12, 16)),
        title="TRANSMISION",
        channel_id="moku",
        safe_zone=safe,
        metadata={"tape_id": "TAPE-04", "accent_color": "#00FF66"},
    )
    assert captured
    for kwargs in captured:
        assert kwargs.get("glow_color") is None
        assert kwargs.get("glow_radius") == 0
        assert kwargs.get("tilt_angle") == 0.0
        assert str(kwargs.get("fill_color", "")).upper() in {"#F5F0E6", "F5F0E6"}
        assert str(kwargs.get("stroke_color", "")).upper() in {"#000000", "000000"}


def test_process_analog_horror_osd_defaults_false():
    sig = inspect.signature(ChiaroscuroColorGrader.process_analog_horror)
    assert sig.parameters["with_osd"].default is False

    base = Image.new("RGB", (64, 36), (30, 40, 35))
    with patch("src.media.thumbnails.analog_horror.draw_camcorder_osd") as osd:
        out = ChiaroscuroColorGrader.process_analog_horror(base, 64, 36)
        osd.assert_not_called()
    assert out.size == (64, 36)


def test_analog_layout_osd_off_without_explicit_flag(spy_draw_text):
    layout = AnalogHorrorVhsLayout()
    canvas = Image.new("RGB", (1920, 1080), (10, 12, 16))
    safe = AspectLayoutManager.get_safe_zone(1920, 1080)
    layout.apply_layout(
        canvas=canvas,
        title="SEÑAL PERDIDA",
        channel_id="moku",
        safe_zone=safe,
        metadata={},
    )
    joined = " ".join(spy_draw_text).upper()
    assert "REC" not in joined
    assert "STEREO" not in joined
    assert "ADVERTENCIA" not in joined
    assert not any(_contains_none_token(t) for t in spy_draw_text)


def test_safe_zone_minimum_six_percent_inset():
    for width, height in ((1920, 1080), (1280, 720), (1080, 1920)):
        zone = AspectLayoutManager.get_safe_zone(width, height)
        assert zone.left >= int(width * 0.06) - 1
        assert zone.top >= int(height * 0.06) - 1
        assert (width - zone.right) >= int(width * 0.06) - 1
        assert (height - zone.bottom) >= int(height * 0.06) - 1


def test_empty_badge_style_does_not_draw_pill(spy_draw_text):
    layout = GeneralCinematicLayout()
    canvas = Image.new("RGB", (1280, 720), (22, 22, 26))
    safe = AspectLayoutManager.get_safe_zone(1280, 720)
    layout.apply_layout(
        canvas=canvas,
        title="HOOK SIN BADGE",
        channel_id="scifi",
        safe_zone=safe,
        metadata={"category": None, "text_box_style": "badge"},
    )
    assert badge_label(None, channel_id="scifi") is None
    assert not any("•" in t for t in spy_draw_text)
    assert not any(_contains_none_token(t) for t in spy_draw_text)
