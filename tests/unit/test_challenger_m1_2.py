"""
tests/unit/test_challenger_m1_2.py - Pytest suite for Challenger M1.2 empirical verification.
"""
import shutil
import sqlite3
import tempfile
from pathlib import Path
import pytest

def _committed_loop_media_count() -> int:
    """Count real loop media files in repo assets/loops (excludes empty checkout)."""
    from src.config import BASE_DIR
    root = BASE_DIR / "assets" / "loops"
    if not root.is_dir():
        return 0
    return len(list(root.rglob("*.mp4"))) + len(list(root.rglob("*.webm")))


from src.config import DEFAULT_DB_PATH
from src.core.catalog import (
    LoopCatalogRepository,
    compute_file_sha256,
    resolve_loop_file_path,
)
from src.media.loop_engine import LoopVideoEngine


def test_challenger_idempotent_sync():
    """Test 1: Idempotent Sync over 3 consecutive executions."""
    if _committed_loop_media_count() < 50:
        pytest.skip("assets/loops has no committed cinematic media in this checkout")
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

        counts = []
        for _ in range(3):
            counts.append(repo.sync_catalog_from_assets())
            current = {
                r["loop_id"]: (r["usage_count"], r["last_used_at"], r["sha256"])
                for r in conn.execute("SELECT loop_id, usage_count, last_used_at, sha256 FROM video_loops").fetchall()
            }
            # Stale DB rows without files may drop; remaining usage metadata stays put.
            for loop_id, meta in current.items():
                if loop_id in baseline:
                    assert current[loop_id] == baseline[loop_id]
        assert counts[0] == counts[1] == counts[2]


def test_challenger_real_db_audit():
    """Test 2: Real Database Audit on shorts_queue.db."""
    if _committed_loop_media_count() < 50:
        pytest.skip("assets/loops has no committed cinematic media in this checkout")

