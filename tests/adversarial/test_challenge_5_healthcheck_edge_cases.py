"""Adversarial stress test for Challenge 5: Healthcheck Probe Edge Cases & Failure Modes."""
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from healthcheck import disk_ok, database_ok, daemon_heartbeat_fresh, main

def test_production_healthcheck_execution():
    """Verify that current system healthcheck exits with code 0."""
    res = subprocess.run(
        ["/home/moku/projects/yt-auto/.venv/bin/python", "healthcheck.py"],
        capture_output=True,
        text=True,
        cwd="/home/moku/projects/yt-auto"
    )
    assert res.returncode == 0, f"Healthcheck failed with code {res.returncode}. Stderr: {res.stderr}"

def test_healthcheck_missing_database(tmp_path):
    """Verify missing database returns code 1 (infrastructure failure)."""
    fake_db = tmp_path / "non_existent.sqlite"
    assert database_ok(fake_db) is False

def test_healthcheck_corrupted_database(tmp_path):
    """Verify corrupted sqlite file returns False / code 1."""
    corrupt_db = tmp_path / "corrupt.sqlite"
    with open(corrupt_db, "wb") as f:
        f.write(b"CORRUPTED_NON_SQLITE_GARBAGE_HEADER_12345" * 50)
    assert database_ok(corrupt_db) is False

def test_healthcheck_stale_daemon_heartbeat(tmp_path):
    """Verify stale daemon heartbeat (>3600s old) triggers exit code 2 (AUD-08 liveness gate)."""
    db_file = tmp_path / "test_heartbeat.sqlite"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE daemon_liveness (id INTEGER PRIMARY KEY, heartbeat_at INTEGER)")
    # Heartbeat is 5000 seconds in the past
    stale_ts = int(time.time()) - 5000
    conn.execute("INSERT INTO daemon_liveness (id, heartbeat_at) VALUES (1, ?)", (stale_ts,))
    conn.commit()
    conn.close()

    # Verify stale heartbeat detected with default 3600s threshold
    assert daemon_heartbeat_fresh(db_file, threshold=3600) is False

    # Verify fresh when threshold is widened to 10000s
    assert daemon_heartbeat_fresh(db_file, threshold=10000) is True

def test_healthcheck_fresh_daemon_heartbeat(tmp_path):
    """Verify fresh daemon heartbeat (<3600s old) returns True."""
    db_file = tmp_path / "test_heartbeat_fresh.sqlite"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE daemon_liveness (id INTEGER PRIMARY KEY, heartbeat_at INTEGER)")
    # Heartbeat is 30 seconds ago
    fresh_ts = int(time.time()) - 30
    conn.execute("INSERT INTO daemon_liveness (id, heartbeat_at) VALUES (1, ?)", (fresh_ts,))
    conn.commit()
    conn.close()

    assert daemon_heartbeat_fresh(db_file, threshold=3600) is True

def test_healthcheck_unmigrated_db_graceful_pass(tmp_path):
    """Verify database without daemon_liveness table treats heartbeat check as healthy (fresh install/pre-migration)."""
    db_file = tmp_path / "empty_db.sqlite"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE some_other_table (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    assert database_ok(db_file) is True
    assert daemon_heartbeat_fresh(db_file) is True

def test_healthcheck_low_disk_space_mock():
    """Verify disk below 1 GB triggers exit code 1."""
    # Mock disk_ok to simulate 500 MB remaining (< 1 GB threshold)
    low_space = MagicMock(free=500 * 1024 * 1024)
    with patch("shutil.disk_usage", return_value=low_space):
        assert disk_ok(Path("/home/moku")) is False

    high_space = MagicMock(free=5 * 1024 * 1024 * 1024)
    with patch("shutil.disk_usage", return_value=high_space):
        assert disk_ok(Path("/home/moku")) is True

def test_healthcheck_main_end_to_end_scenarios():
    """Verify main() exit codes across simulated infrastructure states."""
    # Healthy scenario
    with patch("healthcheck.disk_ok", return_value=True), \
         patch("healthcheck.database_ok", return_value=True), \
         patch("healthcheck.daemon_heartbeat_fresh", return_value=True):
        assert main() == 0

    # Low disk scenario
    with patch("healthcheck.disk_ok", return_value=False):
        assert main() == 1

    # Corrupt DB scenario
    with patch("healthcheck.disk_ok", return_value=True), \
         patch("healthcheck.database_ok", return_value=False):
        assert main() == 1

    # Stale daemon scenario
    with patch("healthcheck.disk_ok", return_value=True), \
         patch("healthcheck.database_ok", return_value=True), \
         patch("healthcheck.daemon_heartbeat_fresh", return_value=False):
        assert main() == 2

if __name__ == "__main__":
    pytest.main(["-v", __file__])
