"""Unit tests for cookie lifecycle telemetry, incident emission, and 1-hour deduplication."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.cookies import (
    SessionHealthResult,
    SessionStatus,
    validate_youtube_session_cookies,
)
from src.core.repository import QueueRepository, connect


@pytest.fixture
def repo(tmp_path: Path) -> QueueRepository:
    db_path = tmp_path / "test_cookies.db"
    r = QueueRepository(db_path)
    r.initialize()
    return r


def test_cookie_failure_event_emission(repo: QueueRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert SessionStatus.EXPIRED, INCOMPLETE, INVALID emit cookie_failure (ERROR) into system_events."""
    monkeypatch.setenv("DEFAULT_DB_PATH", str(repo.db_path))

    from src.core import cookies
    if hasattr(cookies, "_reset_cookie_dedup_registry"):
        cookies._reset_cookie_dedup_registry()

    # 1. Invalid / Empty cookies -> INVALID
    res_invalid = cookies.validate_and_emit_cookie_health([], channel="horror", db_path=str(repo.db_path))
    assert res_invalid.status == SessionStatus.INVALID

    # 2. Incomplete cookies (missing LOGIN_INFO) -> INCOMPLETE
    cookies_incomplete = [{"name": "SID", "value": "xyz", "expires": time.time() + 86400 * 30}]
    res_incomplete = cookies.validate_and_emit_cookie_health(cookies_incomplete, channel="drama", db_path=str(repo.db_path))
    assert res_incomplete.status == SessionStatus.INCOMPLETE

    # 3. Expired cookies (past expiration) -> EXPIRED
    cookies_expired = [
        {"name": "LOGIN_INFO", "value": "abc", "expires": time.time() - 3600},
        {"name": "SID", "value": "xyz", "expires": time.time() - 3600},
    ]
    res_expired = cookies.validate_and_emit_cookie_health(cookies_expired, channel="scifi", db_path=str(repo.db_path))
    assert res_expired.status == SessionStatus.EXPIRED

    with connect(repo.db_path, read_only=True) as conn:
        events = conn.execute(
            "SELECT * FROM system_events WHERE event_type = 'cookie_failure' ORDER BY event_id ASC"
        ).fetchall()
        assert len(events) == 3
        for ev in events:
            assert ev["level"] == "ERROR"
            details = json.loads(ev["details_json"])
            assert "channel" in details
            assert "status" in details


def test_cookie_warning_event_emission(repo: QueueRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert SessionStatus.EXPIRING_SOON (< 48h remaining) emits cookie_warning (WARNING) into system_events."""
    monkeypatch.setenv("DEFAULT_DB_PATH", str(repo.db_path))

    from src.core import cookies
    if hasattr(cookies, "_reset_cookie_dedup_registry"):
        cookies._reset_cookie_dedup_registry()

    # Expiring in 24 hours (< 48h)
    cookies_expiring = [
        {"name": "LOGIN_INFO", "value": "token_abc", "expires": time.time() + 24 * 3600},
        {"name": "SID", "value": "token_sid", "expires": time.time() + 24 * 3600},
    ]
    res = cookies.validate_and_emit_cookie_health(cookies_expiring, channel="horror", db_path=str(repo.db_path))
    assert res.status == SessionStatus.EXPIRING_SOON

    with connect(repo.db_path, read_only=True) as conn:
        events = conn.execute(
            "SELECT * FROM system_events WHERE event_type = 'cookie_warning'"
        ).fetchall()
        assert len(events) == 1
        ev = events[0]
        assert ev["level"] == "WARNING"
        assert ev["channel"] == "horror"
        details = json.loads(ev["details_json"])
        assert "hours_left" in details
        assert details["hours_left"] <= 48.0


def test_cookie_incident_1hour_deduplication(repo: QueueRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert multiple health checks within 1 hour for the same channel and status emit exactly 1 event."""
    monkeypatch.setenv("DEFAULT_DB_PATH", str(repo.db_path))

    from src.core import cookies
    if hasattr(cookies, "_reset_cookie_dedup_registry"):
        cookies._reset_cookie_dedup_registry()

    cookies_expiring = [
        {"name": "LOGIN_INFO", "value": "token_abc", "expires": time.time() + 10 * 3600},
        {"name": "SID", "value": "token_sid", "expires": time.time() + 10 * 3600},
    ]

    # First check -> emits
    cookies.validate_and_emit_cookie_health(cookies_expiring, channel="horror", db_path=str(repo.db_path))
    # Second check immediately after -> suppressed
    cookies.validate_and_emit_cookie_health(cookies_expiring, channel="horror", db_path=str(repo.db_path))
    # Third check -> suppressed
    cookies.validate_and_emit_cookie_health(cookies_expiring, channel="horror", db_path=str(repo.db_path))

    with connect(repo.db_path, read_only=True) as conn:
        events = conn.execute(
            "SELECT * FROM system_events WHERE event_type = 'cookie_warning' AND channel = 'horror'"
        ).fetchall()
        assert len(events) == 1


def test_cookie_status_transition_bypasses_dedup(repo: QueueRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert status transition (e.g. EXPIRING_SOON -> EXPIRED) emits immediately without waiting for 1 hour."""
    monkeypatch.setenv("DEFAULT_DB_PATH", str(repo.db_path))

    from src.core import cookies
    if hasattr(cookies, "_reset_cookie_dedup_registry"):
        cookies._reset_cookie_dedup_registry()

    # Step 1: EXPIRING_SOON
    cookies_expiring = [
        {"name": "LOGIN_INFO", "value": "token_abc", "expires": time.time() + 10 * 3600},
        {"name": "SID", "value": "token_sid", "expires": time.time() + 10 * 3600},
    ]
    cookies.validate_and_emit_cookie_health(cookies_expiring, channel="horror", db_path=str(repo.db_path))

    # Step 2: Transition to EXPIRED (different status)
    cookies_expired = [
        {"name": "LOGIN_INFO", "value": "token_abc", "expires": time.time() - 60},
        {"name": "SID", "value": "token_sid", "expires": time.time() - 60},
    ]
    cookies.validate_and_emit_cookie_health(cookies_expired, channel="horror", db_path=str(repo.db_path))

    with connect(repo.db_path, read_only=True) as conn:
        warnings = conn.execute(
            "SELECT * FROM system_events WHERE event_type = 'cookie_warning' AND channel = 'horror'"
        ).fetchall()
        failures = conn.execute(
            "SELECT * FROM system_events WHERE event_type = 'cookie_failure' AND channel = 'horror'"
        ).fetchall()
        assert len(warnings) == 1
        assert len(failures) == 1
