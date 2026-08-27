"""Unit tests for the daemon-liveness healthcheck gate (AUD-08)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import healthcheck


def _make_db(tmp_path: Path, heartbeat: int | None) -> Path:
    db = tmp_path / "queue.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS daemon_liveness ("
        "id INTEGER PRIMARY KEY CHECK(id = 1), "
        "heartbeat_at INTEGER NOT NULL)"
    )
    if heartbeat is not None:
        conn.execute(
            "INSERT OR REPLACE INTO daemon_liveness(id, heartbeat_at) VALUES (1, ?)",
            (heartbeat,),
        )
    conn.commit()
    conn.close()
    return db


def test_missing_table_is_treated_as_fresh(tmp_path):
    db = tmp_path / "empty.db"
    db.write_bytes(b"")
    assert healthcheck.daemon_heartbeat_fresh(db, now=1_000_000)


def test_zero_heartbeat_is_treated_as_fresh(tmp_path):
    db = _make_db(tmp_path, 0)  # INSERT OR IGNORE seed value
    assert healthcheck.daemon_heartbeat_fresh(db, now=1_000_000)


def test_recent_heartbeat_is_fresh(tmp_path):
    db = _make_db(tmp_path, 1_000_000)
    assert healthcheck.daemon_heartbeat_fresh(db, now=1_000_100, threshold=3600)


def test_stale_heartbeat_is_detected(tmp_path):
    db = _make_db(tmp_path, 1_000_000)
    assert not healthcheck.daemon_heartbeat_fresh(
        db, now=1_000_000 + 3601, threshold=3600
    )
