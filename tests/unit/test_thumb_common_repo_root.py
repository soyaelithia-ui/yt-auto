"""Critical: thumb_common REPO_ROOT + ImageFilter for draw_text_with_effects."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from scripts.lib import thumb_common
from scripts.lib.thumb_common import REPO_ROOT, draw_text_with_effects


def test_thumb_common_repo_root_is_repo_root():
    assert (REPO_ROOT / "scripts" / "lib" / "thumb_common.py").is_file()
    assert (REPO_ROOT / "src").is_dir()
    assert (REPO_ROOT / "assets").is_dir()
    assert REPO_ROOT.name != "scripts"
    assert Path(__file__).resolve().parents[2] == REPO_ROOT


def test_draw_text_with_effects_no_nameerror():
    """Smoke: ImageFilter must be imported; call must not raise NameError."""
    assert hasattr(thumb_common, "ImageFilter")
    img = Image.new("RGBA", (64, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    bbox = draw_text_with_effects(
        draw,
        img.size,
        "T",
        (2, 2),
        font,
        glow_color=(255, 0, 0, 80),
        glow_radius=2,
    )
    assert isinstance(bbox, tuple) and len(bbox) == 4
