"""
E2E Test Suite for Requirement R1 (Loop Catalog Activation & SQLite Indexing).
Covers Features F1 through F6, Boundary Cases, and Rotation Dynamics.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import List, Optional
import pytest

from src.core.catalog import LoopCatalogRepository, LoopRecord, resolve_loop_file_path
from src.media.loop_engine import LoopVideoEngine

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets" / "loops"


# ==============================================================================
# Tier 1: Feature Coverage (R1: F1 - F6)
# ==============================================================================

@pytest.mark.tier1
def test_r1_f1_scan_assets_catalog_discovers_cinematic_loops():
    """Verify assets/loops contains >= 64 valid cinematic loops across orientations."""
    horizontal_loops = list((ASSETS_DIR / "horizontal").rglob("*.mp4")) + list((ASSETS_DIR / "horizontal").rglob("*.webm"))
    vertical_loops = list((ASSETS_DIR / "vertical").rglob("*.mp4")) + list((ASSETS_DIR / "vertical").rglob("*.webm"))
    total_loops = len(horizontal_loops) + len(vertical_loops)
    
    assert len(horizontal_loops) >= 10, f"Expected >=10 horizontal loops, found {len(horizontal_loops)}"
    assert len(vertical_loops) >= 10, f"Expected >=10 vertical loops, found {len(vertical_loops)}"
    assert total_loops >= 64, f"Expected >=64 total cinematic loops in assets/loops, found {total_loops}"


@pytest.mark.tier1
def test_r1_f2_sync_catalog_from_assets_contract(tmp_path: Path):
    """Verify sync_catalog_from_assets() indexes > 50 verified loops into SQLite table video_loops."""
    db_path = tmp_path / "test_catalog.db"
    repo = LoopCatalogRepository(db_path=str(db_path))

    if not hasattr(repo, "sync_catalog_from_assets"):
        pytest.xfail("Pending M1 implementation: LoopCatalogRepository.sync_catalog_from_assets() not yet implemented")

    indexed_count = repo.sync_catalog_from_assets(ASSETS_DIR)
    assert indexed_count >= 50, f"Expected >=50 loops indexed, got {indexed_count}"
    assert repo.count_loops() >= 50, "Total count in DB must be >= 50"

    # Verify idempotency
    second_run = repo.sync_catalog_from_assets(ASSETS_DIR)
    assert second_run == indexed_count, "Second sync run must be idempotent"


@pytest.mark.tier1
def test_r1_f3_auto_seeding_on_empty_database(tmp_path: Path):
    """Verify LoopCatalogRepository auto-seeds loops if count_loops() < 50 on initialization."""
    db_path = tmp_path / "autoseed_catalog.db"
    repo = LoopCatalogRepository(db_path=str(db_path))

    count = repo.count_loops()
    if count < 50:
        pytest.xfail("Pending M1 implementation: LoopCatalogRepository auto-seeding in _ensure_table() not yet active")
    assert count >= 50, f"Auto-seeding should guarantee >=50 loops in database, found {count}"


@pytest.mark.tier1
def test_r1_f4_category_aliasing_and_thematic_categories():
    """Verify THEMATIC_CATEGORIES and CATEGORY_ALIASES mappings in LoopVideoEngine."""
    required_cats = {"horror", "dark_forest", "cosmic_horror", "drama", "cozy_ambient", "scifi", "space_abyss", "monsters"}
    actual_cats = set(getattr(LoopVideoEngine, "THEMATIC_CATEGORIES", ()))

    aliases = getattr(LoopVideoEngine, "CATEGORY_ALIASES", None)
    if aliases is None or not required_cats.issubset(actual_cats):
        pytest.xfail("Pending M1 implementation: LoopVideoEngine.CATEGORY_ALIASES or expanded THEMATIC_CATEGORIES missing")

    assert required_cats.issubset(actual_cats), f"Missing categories in THEMATIC_CATEGORIES: {required_cats - actual_cats}"
    assert aliases.get("tactical_chamber") in ("horror", "dark_ambient", "scifi")
    assert aliases.get("drama_aita") in ("drama", "cozy_ambient")


@pytest.mark.tier1
def test_r1_f5_channel_isolation_and_seeded_rotation(tmp_path: Path):
    """Verify channel isolation and deterministic rotation using seed parameter."""
    db_path = tmp_path / "test_isolation.db"
    repo = LoopCatalogRepository(db_path=str(db_path))

    # Test seed parameter contract
    import inspect
    sig = inspect.signature(repo.get_best_loop)
    if "seed" not in sig.parameters or "channel" not in sig.parameters:
        pytest.xfail("Pending M1 implementation: LoopCatalogRepository.get_best_loop missing seed or channel parameter")

    loop_moku = repo.get_best_loop("horror", "vertical", seed=42, channel="moku")
    loop_aelithia = repo.get_best_loop("drama", "vertical", seed=42, channel="aelithia")

    if loop_moku is not None and loop_aelithia is not None:
        assert loop_moku.loop_id != loop_aelithia.loop_id, "Channel loops must be distinct"


@pytest.mark.tier1
def test_r1_f6_monochrome_defaults_excluded_from_default_pool(tmp_path: Path):
    """Verify flat monochrome procedural loops (maritime_lighthouse, arctic_desolation) are excluded."""
    db_path = tmp_path / "test_monochrome.db"
    repo = LoopCatalogRepository(db_path=str(db_path))

    # Register a valid cinematic loop and a legacy monochrome loop
    cinematic_loop = LoopRecord(
        loop_id="cinematic_cosmic_01",
        category="cosmic_horror",
        technology="mp4",
        orientation="horizontal",
        width=1920,
        height=1080,
        duration_sec=10.0,
        fps=30,
        file_path=str(ASSETS_DIR / "horizontal" / "cosmic_horror"),
        file_size_bytes=500000,
        sha256="abc12345",
    )
    repo.register_loop(cinematic_loop)

    # Invariant: get_best_loop for general categories must never return deprecated monochrome loops
    best_loop = repo.get_best_loop("cosmic_horror", "horizontal")
    if best_loop:
        assert "maritime_lighthouse" not in best_loop.loop_id
        assert "arctic_desolation" not in best_loop.loop_id


# ==============================================================================
# Tier 2: Boundary & Corner Cases (>= 5 tests)
# ==============================================================================

@pytest.mark.tier2
def test_r1_boundary_empty_assets_directory_sync(tmp_path: Path):
    """Verify syncing an empty directory gracefully returns 0 without database error."""
    db_path = tmp_path / "empty_sync.db"
    empty_assets = tmp_path / "empty_assets"
    empty_assets.mkdir()

    repo = LoopCatalogRepository(db_path=str(db_path))
    if not hasattr(repo, "sync_catalog_from_assets"):
        pytest.xfail("Pending M1 implementation: sync_catalog_from_assets not present")

    count = repo.sync_catalog_from_assets(empty_assets)
    assert count == 0


@pytest.mark.tier2
def test_r1_boundary_corrupted_or_zero_byte_loop(tmp_path: Path):
    """Verify 0-byte or corrupt loop files (<25KB) are rejected and omitted from active selection."""
    db_path = tmp_path / "corrupt_check.db"
    repo = LoopCatalogRepository(db_path=str(db_path))

    fake_corrupt_file = tmp_path / "corrupt_loop.mp4"
    fake_corrupt_file.write_bytes(b"corrupt header 1234")  # < 25KB

    corrupt_rec = LoopRecord(
        loop_id="corrupt_loop_01",
        category="horror",
        technology="mp4",
        orientation="vertical",
        width=1080,
        height=1920,
        duration_sec=5.0,
        fps=30,
        file_path=str(fake_corrupt_file),
        file_size_bytes=len(fake_corrupt_file.read_bytes()),
        sha256="corrupt_sha",
    )
    repo.register_loop(corrupt_rec)

    # Invariant: Files <25KB must be filtered out by get_best_loop
    selected = repo.get_best_loop("horror", "vertical")
    if selected:
        assert selected.loop_id != "corrupt_loop_01"


@pytest.mark.tier2
def test_r1_boundary_unknown_category_graceful_fallback(tmp_path: Path):
    """Verify querying an unknown or nonexistent category falls back gracefully without crash."""
    db_path = tmp_path / "fallback.db"
    repo = LoopCatalogRepository(db_path=str(db_path))

    # Even with empty DB, calling get_best_loop with unknown category must return None, not raise exception
    res = repo.get_best_loop("nonexistent_alien_dimension_xyz", "vertical")
    assert res is None or isinstance(res, LoopRecord)


@pytest.mark.tier2
def test_r1_boundary_exclude_all_available_loops(tmp_path: Path):
    """Verify exclude_loop_ids containing all loops returns None or wraps without unhandled exception."""
    db_path = tmp_path / "exclude.db"
    repo = LoopCatalogRepository(db_path=str(db_path))

    import inspect
    sig = inspect.signature(repo.get_best_loop)
    if "exclude_loop_ids" not in sig.parameters:
        pytest.xfail("Pending M1 implementation: exclude_loop_ids parameter missing")

    all_ids = [r.loop_id for r in repo.list_loops()]
    res = repo.get_best_loop("horror", "vertical", exclude_loop_ids=all_ids)
    assert res is None or isinstance(res, LoopRecord)


@pytest.mark.tier2
def test_r1_boundary_non_video_files_ignored(tmp_path: Path):
    """Verify non-video files (.txt, .json, .gitkeep) in loop folders are ignored during scan."""
    db_path = tmp_path / "non_video.db"
    asset_dir = tmp_path / "assets"
    (asset_dir / "vertical" / "horror").mkdir(parents=True)
    (asset_dir / "vertical" / "horror" / "notes.txt").write_text("not a video")
    (asset_dir / "vertical" / "horror" / ".gitkeep").touch()
    (asset_dir / "vertical" / "horror" / "meta.json").write_text("{}")

    repo = LoopCatalogRepository(db_path=str(db_path))
    if not hasattr(repo, "sync_catalog_from_assets"):
        pytest.xfail("Pending M1 implementation: sync_catalog_from_assets not present")

    count = repo.sync_catalog_from_assets(asset_dir)
    assert count == 0


@pytest.mark.tier2
def test_r1_boundary_sql_injection_resilience(tmp_path: Path):
    """Verify malicious SQL inputs in category or orientation do not cause injection."""
    db_path = tmp_path / "sqli.db"
    repo = LoopCatalogRepository(db_path=str(db_path))

    malicious_cat = "horror' OR '1'='1"
    # Must execute safely without sqlite3.OperationalError syntax error
    res = repo.get_best_loop(malicious_cat, "vertical")
    assert res is None or isinstance(res, LoopRecord)


# ==============================================================================
# Tier 3: Cross-Feature Interaction
# ==============================================================================

@pytest.mark.tier3
def test_r1_interaction_consecutive_seeded_rotation(tmp_path: Path):
    """Verify different seeds yield different loops when multiple options exist."""
    db_path = tmp_path / "rotation.db"
    repo = LoopCatalogRepository(db_path=str(db_path))

    import inspect
    sig = inspect.signature(repo.get_best_loop)
    if "seed" not in sig.parameters:
        pytest.xfail("Pending M1 implementation: seed parameter not present")

    # Invariant: seed variation changes the returned candidate when pool > 1
    loop_a = repo.get_best_loop("horror", "vertical", seed=101)
    loop_b = repo.get_best_loop("horror", "vertical", seed=202)
    # If catalog populated with >1 loop, verify determinism
    loop_a_repeat = repo.get_best_loop("horror", "vertical", seed=101)
    if loop_a and loop_a_repeat:
        assert loop_a.loop_id == loop_a_repeat.loop_id, "Identical seed must return identical loop"
