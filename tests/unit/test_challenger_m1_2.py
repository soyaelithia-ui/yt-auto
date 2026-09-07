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

    # Skip when CI checkout has empty assets/loops / empty DEFAULT_DB
    from src.core.catalog import LoopCatalogRepository as _LCR
    from src.config import DEFAULT_DB_PATH as _DB
    _probe = _LCR(db_path=str(_DB), auto_seed=True)
    if _probe.count_loops() < 50:
        # auto_seed may synthesize; real-db audit wants on-disk cinematic media
        from pathlib import Path as _P
        from src.config import BASE_DIR as _BD
        _media = list((_BD / "assets" / "loops").rglob("*.mp4"))
        if len(_media) < 50:
            pytest.skip("real DB audit requires committed loop media")
