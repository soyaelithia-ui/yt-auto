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


@pytest.mark.parametrize("folder", SCENERY_DIRS, ids=("moku", "aelithia"))
def test_visual_bank_scenery_has_at_least_three_jpgs(folder: Path) -> None:
    jpgs = _jpg_files(folder)
    assert len(jpgs) >= 3, f"{folder} has {len(jpgs)} jpgs"
    for p in jpgs:
        assert p.suffix.lower() != ".gif"
        assert "_quarantine_title_cards" not in p.as_posix()
        assert p.name not in QUARANTINE_NAMES
        assert p.stat().st_size > 20_000


def test_index_json_lists_scenery_without_quarantine() -> None:
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    assert index.get("updated_at")
    for channel in ("moku", "aelithia"):
        entries = index["channels"][channel]["categories"]["scenery"]
        assert len(entries) >= 3, channel
        disk_stems = {p.stem for p in _jpg_files(BANK / channel / "scenery")}
        ids = set()
        for entry in entries:
            for key in REQUIRED_META:
                assert key in entry, f"{channel} scenery missing {key}"
            path = str(entry["path"])
            assert "_quarantine_title_cards" not in path
            assert not path.lower().endswith(".gif")
            assert str(entry["format"]).lower() in {"jpg", "jpeg"}
            assert str(entry["file"]).lower().endswith((".jpg", ".jpeg"))
            assert entry["file"] not in QUARANTINE_NAMES
            abs_path = REPO / path
            assert abs_path.is_file(), path
            with Image.open(abs_path) as im:
                assert list(entry["resolution"]) == list(im.size), path
            ids.add(entry["id"])
        assert ids <= disk_stems
        assert len(ids & disk_stems) >= 3


def test_scenery_dirs_contain_no_gifs_or_quarantine_cards() -> None:
    for folder in SCENERY_DIRS:
        for p in folder.iterdir():
            if p.name.startswith("."):
                continue
            assert p.suffix.lower() != ".gif", p
            assert "_quarantine_title_cards" not in p.as_posix()
            assert p.name not in QUARANTINE_NAMES
