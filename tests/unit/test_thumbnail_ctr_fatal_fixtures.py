"""Fatal CTR samples against real master_backdrop.jpg plates (not synthetic canvases)."""
from __future__ import annotations

from pathlib import Path
from typing import List

import pytest
from PIL import Image, ImageDraw

import src.media.thumbnails.layouts  # noqa: F401  # register analog + cinematic before generate()
from src.media.thumbnails.engine import ThumbnailConfig, ThumbnailEngine
from src.media.thumbnails.typography import DynamicTypographyEngine
from tests.unit.test_thumbnail_ctr_anti_cases import (
    AITA_FIXTURE,
    _assert_word_bounded,
    _contains_none_token,
)

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "assets" / "thumbnails" / "templates"
AITA_PLATE = TEMPLATES / "aita" / "master_backdrop.jpg"
HORROR_PLATE = TEMPLATES / "horror" / "master_backdrop.jpg"
SCP_PLATE = TEMPLATES / "scp" / "master_backdrop.jpg"
OSD_CHROME_TOKENS = ("REC", "CH 03", "STEREO", "HI-FI", "OCT 24", "11:42")


@pytest.fixture
def spy_draw_text(monkeypatch: pytest.MonkeyPatch):
    drawn: List[str] = []
    real = ImageDraw.ImageDraw.text

    def wrapped(self, xy, text, *args, **kwargs):
        drawn.append(str(text))
        return real(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", wrapped)
    return drawn


def _assert_jpeg_1920x1080(path: Path) -> None:
    assert path.is_file(), path
    with Image.open(path) as im:
        assert im.format == "JPEG"
        assert im.size == (1920, 1080), im.size


def _title_lines_from_spy(drawn: List[str], original: str) -> List[str]:
    words = original.split()
    lines: List[str] = []
    for text in drawn:
        if any(word in text.split() for word in words) and text not in lines:
            lines.append(text)
    return lines


def test_real_aita_none_badge_never_paints_none_token(tmp_path, spy_draw_text):
    # Synthetic canvases cannot catch a baked NONE on the master plate plus layout paint.
    assert AITA_PLATE.is_file(), AITA_PLATE
    engine = ThumbnailEngine()
    for category in ("NONE", "none"):
        spy_draw_text.clear()
        out = tmp_path / f"aita_none_{category}.jpg"
        engine.generate(
            ThumbnailConfig(
                title="CONFESION SIN VEREDICTO",
                channel_id="aelithia",
                archetype="aita",
                output_path=out,
                width=1920,
                height=1080,
                metadata={"category": category},
            ),
            base_image_path=AITA_PLATE,
        )
        _assert_jpeg_1920x1080(out)
        assert not any(_contains_none_token(t) for t in spy_draw_text), spy_draw_text


def test_real_aita_title_wraps_two_word_bounded_lines(tmp_path, spy_draw_text):
    # Engine hook used to mid-cut "AITA POR REVELAR EL"; the live wrap must keep whole words.
    assert AITA_PLATE.is_file(), AITA_PLATE
    out = tmp_path / "aita_truncate.jpg"
    ThumbnailEngine().generate(
        ThumbnailConfig(
            title=AITA_FIXTURE,
            channel_id="aelithia",
            archetype="aita",
            output_path=out,
            width=1920,
            height=1080,
            metadata={"category": "YTA"},
        ),
        base_image_path=AITA_PLATE,
    )
    _assert_jpeg_1920x1080(out)
    title_lines = _title_lines_from_spy(spy_draw_text, AITA_FIXTURE)
    assert 1 <= len(title_lines) <= 2, title_lines
    _assert_word_bounded(AITA_FIXTURE, title_lines)
    joined = " ".join(title_lines)
    assert joined != "AITA POR REVELAR EL"
    assert "SECRETO" in joined
    assert "FAMILIA" in joined
    assert any("YTA" in t.upper() for t in spy_draw_text)


def test_real_horror_osd_off_does_not_double_chrome(tmp_path, spy_draw_text):
    # Clean horror plate + default layout must not stamp a second camcorder chrome layer.
    assert HORROR_PLATE.is_file(), HORROR_PLATE
    out = tmp_path / "horror_osd_off.jpg"
    ThumbnailEngine().generate(
        ThumbnailConfig(
            title="SENAL PERDIDA",
            channel_id="moku",
            archetype="horror",
            output_path=out,
            width=1920,
            height=1080,
            metadata={},
        ),
        base_image_path=HORROR_PLATE,
    )
    _assert_jpeg_1920x1080(out)
    joined = " ".join(spy_draw_text).upper()
    for token in OSD_CHROME_TOKENS:
        assert token not in joined, (token, spy_draw_text)
    assert "ADVERTENCIA" not in joined
    assert not any(_contains_none_token(t) for t in spy_draw_text)


def test_real_scp_ctr_path_disables_neon_glow(tmp_path, spy_draw_text, monkeypatch):
    # Assert glow kwargs (not a flaky #00FF66 pixel sample; accent rims are unrelated).
    assert SCP_PLATE.is_file(), SCP_PLATE
    captured: List[dict] = []
    orig = DynamicTypographyEngine.draw_text_with_effects

    def spy(*args, **kwargs):
        captured.append(kwargs)
        return orig(*args, **kwargs)

    monkeypatch.setattr(DynamicTypographyEngine, "draw_text_with_effects", spy)
    out = tmp_path / "scp_keter.jpg"
    ThumbnailEngine().generate(
        ThumbnailConfig(
            title="SCP-173 BRECHA",
            channel_id="moku-scp-shorts",
            archetype="scp",
            output_path=out,
            width=1920,
            height=1080,
            metadata={"category": "KETER", "accent_color": "#00FF66"},
        ),
        base_image_path=SCP_PLATE,
    )
    _assert_jpeg_1920x1080(out)
    assert captured
    for kwargs in captured:
        assert kwargs.get("glow_color") is None
        assert kwargs.get("glow_radius") == 0
    assert any("KETER" in t.upper() for t in spy_draw_text)
    assert not any(_contains_none_token(t) for t in spy_draw_text)
    # NONE omitted on the same plate (SCP class badge is the only allowed chrome).
    spy_draw_text.clear()
    captured.clear()
    out_none = tmp_path / "scp_none.jpg"
    ThumbnailEngine().generate(
        ThumbnailConfig(
            title="SCP-173 BRECHA",
            channel_id="moku-scp-shorts",
            archetype="scp",
            output_path=out_none,
            width=1920,
            height=1080,
            metadata={"category": "NONE", "accent_color": "#00FF66"},
        ),
        base_image_path=SCP_PLATE,
    )
    _assert_jpeg_1920x1080(out_none)
    assert not any(_contains_none_token(t) for t in spy_draw_text), spy_draw_text
    assert not any("KETER" in t.upper().split() for t in spy_draw_text)
    for kwargs in captured:
        assert kwargs.get("glow_color") is None
        assert kwargs.get("glow_radius") == 0
