"""Guards: CTR master backdrops and visual_bank scenery are clean scene plates."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "assets" / "thumbnails" / "templates"
BANK = REPO / "assets" / "visual_bank"
INDEX_PATH = BANK / "index.json"

MASTER_BACKDROPS = (
    TEMPLATES / "horror" / "master_backdrop.jpg",
    TEMPLATES / "scp" / "master_backdrop.jpg",
    TEMPLATES / "aita" / "master_backdrop.jpg",
)
SCENERY_DIRS = (
    BANK / "moku" / "scenery",
    BANK / "aelithia" / "scenery",
)
REQUIRED_META = ("id", "file", "path", "resolution", "format", "tags", "description")
OSD_TOKENS = ("REC", "ADVERTENCIA", "BITÁCORA", "NONE", "CH 0")
QUARANTINE_NAMES = {
    "abyssal_creature.jpg",
    "scp_3008_infinite.jpg",
    "scp_containment.jpg",
    "dna_secret.jpg",
}


def _jpg_files(folder: Path) -> list[Path]:
    return sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"} and not p.name.startswith(".")
    )


def _assert_not_flat_color(im: Image.Image) -> None:
    gray = im.convert("L")
    lo, hi = gray.getextrema()
    occupied = sum(1 for n in gray.histogram() if n > 0)
    assert (hi - lo) > 25, f"luminance range too small: {lo}-{hi}"
    assert occupied > 32, f"too few distinct gray levels: {occupied}"


@pytest.mark.parametrize("path", MASTER_BACKDROPS, ids=("horror", "scp", "aita"))
def test_master_backdrops_are_1920x1080_scene_plates(path: Path) -> None:
    assert path.is_file(), path
    assert path.stat().st_size > 20_000, f"{path} is tiny ({path.stat().st_size} bytes)"
    with Image.open(path) as im:
        assert im.size == (1920, 1080), f"{path} size {im.size}"
        assert im.format == "JPEG"
        _assert_not_flat_color(im)


def test_master_backdrops_ocr_has_no_baked_osd() -> None:
    pytesseract = pytest.importorskip("pytesseract")
    needle = re.compile(
        r"(?<![A-Za-z])(?:REC|ADVERTENCIA|BIT[ÁA]CORA|NONE|CH 0)(?![A-Za-z])",
        re.IGNORECASE,
    )
    for path in MASTER_BACKDROPS:
        with Image.open(path) as im:
            text = pytesseract.image_to_string(im) or ""
        assert not needle.search(text), f"{path.name} OCR has OSD: {text!r}"
        lowered = text.lower()
        for token in OSD_TOKENS:
            assert token.lower() not in lowered, f"{path.name} OCR contains {token!r}: {text!r}"


def test_visual_bank_is_purged_and_templates_preserved() -> None:
    """Obsolete visual_bank assets are purged; templates/ backdrops remain."""
    assert not BANK.exists(), "visual_bank directory must be purged"
    for path in MASTER_BACKDROPS:
        assert path.is_file(), f"Master backdrop missing: {path}"

