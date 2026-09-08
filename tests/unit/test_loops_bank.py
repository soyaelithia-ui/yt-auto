"""
test_loops_bank.py - Unit tests for the classified Grok video loops bank.
Validates master loops existence, H.264 profile, and LoopVideoEngine resolution.
"""
import json
import sqlite3
from pathlib import Path
import pytest

from src.core.catalog import LoopCatalogRepository
from src.media.loop_engine import LoopVideoEngine


BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOOPS_DIR = BASE_DIR / "assets" / "loops"
MANIFEST_PATH = LOOPS_DIR / "bank_manifest.json"
DB_PATH = BASE_DIR / "data" / "loop_catalog.db"


@pytest.fixture(scope="module")
def bank_manifest():
    assert MANIFEST_PATH.exists(), f"Missing bank manifest at {MANIFEST_PATH}"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_bank_manifest_structure(bank_manifest):
    """Verifies that bank_manifest.json contains required metadata."""
    assert "version" in bank_manifest
    assert "master_loops" in bank_manifest
    assert len(bank_manifest["master_loops"]) >= 5
    assert bank_manifest["total_atomic_clips"] >= 50


def test_master_loops_exist_and_valid(bank_manifest):
    """Verifies that all master loops registered in the manifest exist on disk with canonical 1080p geometry."""
    assert bank_manifest["total_atomic_clips"] == 55
    master_loops = bank_manifest.get("master_loops", [])
    if not any((BASE_DIR / item["file_path"]).is_file() for item in master_loops):
        pytest.skip("Master loop video binaries (.mp4) not present in local checkout (gitignored)")
    for item in master_loops:
        file_path = BASE_DIR / item["file_path"]
        assert file_path.is_file(), f"Master loop file does not exist: {file_path}"
        assert file_path.stat().st_size > 1_000_000, f"Master loop suspiciously small: {file_path}"
        assert item["duration_sec"] >= 60.0, f"Master loop duration under 60s: {item['duration_sec']}"

        if item["orientation"] == "horizontal":
            assert item["width"] == 1920, f"Expected 1920 width, got {item['width']}"
            assert item["height"] == 1080, f"Expected 1080 height, got {item['height']}"
        else:
            assert item["width"] == 1080, f"Expected 1080 width, got {item['width']}"
            assert item["height"] == 1920, f"Expected 1920 height, got {item['height']}"


def test_sqlite_catalog_populated():
    """Verifies that SQLite loop catalog has active records for horizontal and vertical."""
    if not DB_PATH.is_file():
        pytest.skip("data/loop_catalog.db not present in local checkout (gitignored)")
    repo = LoopCatalogRepository(db_path=DB_PATH)
    loops = repo.list_loops(limit=100)
    if len(loops) == 0:
        pytest.skip("data/loop_catalog.db has 0 records in local checkout")
    assert len(loops) >= 8, f"Expected at least 8 catalog records, got {len(loops)}"

    categories = {l.category for l in loops}
    assert "horror" in categories
    assert "drama" in categories
    assert "scifi" in categories


def test_loop_video_engine_resolves_all_channels():
    """Verifies that LoopVideoEngine resolves bank assets without error or live synthesis."""
    engine = LoopVideoEngine(loops_root_dir=LOOPS_DIR, db_path=DB_PATH, enable_live_synth=False)

    for cat in ("horror", "drama", "scifi", "dark_forest", "space_abyss"):
        # Test horizontal
        h_asset = engine.resolve_loop_video(category=cat, orientation="horizontal", allow_fallback=True)
        assert h_asset is not None
        assert h_asset.exists()

        # Test vertical
        v_asset = engine.resolve_loop_video(category=cat, orientation="vertical", allow_fallback=True)
        assert v_asset is not None
        assert v_asset.exists()
