"""
tests/unit/test_challenger_m1_2.py - Pytest suite for Challenger M1.2 empirical verification.
"""
import shutil
import sqlite3
import tempfile
from pathlib import Path
import pytest

from src.config import DEFAULT_DB_PATH
from src.core.catalog import (
    LoopCatalogRepository,
    compute_file_sha256,
    resolve_loop_file_path,
)
from src.media.loop_engine import LoopVideoEngine


def test_challenger_idempotent_sync():
    """Test 1: Idempotent Sync over 3 consecutive executions."""
    real_db = Path(DEFAULT_DB_PATH)
    assert real_db.is_file(), f"Real DB not found: {real_db}"

    with tempfile.TemporaryDirectory() as tmpdir:
        clone_db = Path(tmpdir) / "test_shorts_queue.db"
        shutil.copyfile(real_db, clone_db)
        repo = LoopCatalogRepository(db_path=str(clone_db), auto_seed=False)

        # Simulate usage
        sample = repo.list_loops(limit=5)
        for s in sample:
            repo.record_loop_usage(s.loop_id)

        conn = sqlite3.connect(str(clone_db))
        conn.row_factory = sqlite3.Row
        baseline = {
            r["loop_id"]: (r["usage_count"], r["last_used_at"], r["sha256"])
            for r in conn.execute("SELECT loop_id, usage_count, last_used_at, sha256 FROM video_loops").fetchall()
        }

        for _ in range(3):
            synced = repo.sync_catalog_from_assets()
            assert synced == len(baseline)
            current = {
                r["loop_id"]: (r["usage_count"], r["last_used_at"], r["sha256"])
                for r in conn.execute("SELECT loop_id, usage_count, last_used_at, sha256 FROM video_loops").fetchall()
            }
            assert len(current) == len(baseline)
            assert current == baseline


def test_challenger_real_db_audit():
    """Test 2: Real Database Audit on shorts_queue.db."""
    real_db = Path(DEFAULT_DB_PATH)
    assert real_db.is_file()

    conn = sqlite3.connect(str(real_db))
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) FROM video_loops").fetchone()[0]
    assert total >= 50, f"Expected >= 50 loops, got {total}"
    assert total == 88, f"Expected exactly 88 loops, got {total}"

    monos = conn.execute("""
        SELECT COUNT(*) FROM video_loops
        WHERE loop_id IN ('loop_maritime_lighthouse_h_544374', 'loop_arctic_desolation_v_800210')
           OR category IN ('maritime_lighthouse', 'arctic_desolation')
           OR (technology = 'ffmpeg_lavfi' AND sha256 = 'procedural')
    """).fetchone()[0]
    assert monos == 0, f"Monochrome loops not purged, found: {monos}"

    rows = conn.execute("SELECT loop_id, file_path, file_size_bytes, sha256 FROM video_loops").fetchall()
    for r in rows:
        p = resolve_loop_file_path(r["file_path"])
        assert p.is_file(), f"File missing: {r['file_path']}"
        assert p.stat().st_size >= 25_000, f"File size < 25KB: {p} ({p.stat().st_size} bytes)"
        assert compute_file_sha256(p) == r["sha256"], f"SHA mismatch for {r['loop_id']}"


def test_challenger_corrupt_asset_resilience_bug():
    """Test 3: Corrupt Asset Resilience - highlights that 100-byte corrupt files are not discarded."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        assets = tmp_path / "assets"
        (assets / "horizontal").mkdir(parents=True)
        (assets / "vertical").mkdir(parents=True)

        # 0-byte file
        (assets / "horizontal" / "zero.mp4").write_bytes(b"")
        # 100-byte corrupted file
        (assets / "horizontal" / "corrupt.mp4").write_bytes(b"x" * 100)

        db = tmp_path / "test.db"
        repo = LoopCatalogRepository(db_path=str(db), auto_seed=False)

        # Must not crash
        synced = repo.sync_catalog_from_assets(assets_dir=assets)

        # Verify whether 100-byte corrupt file was discarded:
        # If it was discarded, synced should be 0.
        # This assert proves the bug exists:
        indexed = repo.list_loops()
        # The defect: repo indexed 1 corrupted file instead of 0
        corrupt_indexed = [r for r in indexed if r.file_size_bytes < 25_000]
        assert len(corrupt_indexed) == 0, (
            f"Vulnerability confirmed: sync_catalog_from_assets() indexed {len(corrupt_indexed)} "
            f"corrupt file(s) (<25KB) instead of discarding them."
        )


def test_challenger_monochrome_fallback_elimination():
    """Test 4: Monochrome Fallback Elimination across adversarial queries."""
    engine = LoopVideoEngine()
    garbage_cats = ["garbage_cat_12345", "nonexistent_theme_xyz", "maritime_lighthouse", "arctic_desolation", ""]

    for cat in garbage_cats:
        for orient in ["vertical", "horizontal"]:
            for ch in ["moku", "aelithia"]:
                p = engine.resolve_loop_video(category=cat, orientation=orient, channel=ch)
                assert p.is_file()
                assert p.stat().st_size >= 25_000
                assert "maritime_lighthouse" not in p.name.lower()
                assert "arctic_desolation" not in p.name.lower()
                if ch == "moku":
                    assert "aelithia_" not in p.name.lower()
                elif ch == "aelithia":
                    assert "moku_" not in p.name.lower()
