"""Unit tests for the observability pipe: migration 004, emitter, context."""

from __future__ import annotations

import json
import logging
import sqlite3

import pytest

from src.core.repository import QueueRepository
from src.observability import (
    clear_run_context,
    emit_error,
    emit_event,
    get_run_context,
    set_run_context,
    update_run_context,
)


@pytest.fixture(autouse=True)
def _clean_context():
    clear_run_context()
    yield
    clear_run_context()


def _repo(tmp_path) -> QueueRepository:
    repo = QueueRepository(str(tmp_path / "queue.db"))
    repo.initialize()
    return repo


def test_migration_004_creates_system_events(tmp_path):
    repo = _repo(tmp_path)
    conn = sqlite3.connect(repo.db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "system_events" in tables
        versions = {
            row[0] for row in conn.execute("SELECT version FROM schema_migrations")
        }
        assert 4 in versions
    finally:
        conn.close()


def test_record_and_query_roundtrip(tmp_path):
    repo = _repo(tmp_path)
    event_id = repo.record_system_event(
        "run_failed",
        level="ERROR",
        run_id="r1",
        channel="moku",
        component="pipeline",
        stage="render",
        error_code="boom",
        message="falló",
        details={"k": "v"},
    )
    assert event_id >= 1
    rows = repo.query_system_events(limit=10)
    assert len(rows) == 1
    row = rows[0]
    assert row["event_type"] == "run_failed"
    assert row["level"] == "ERROR"
    assert row["run_id"] == "r1"
    assert json.loads(row["details_json"]) == {"k": "v"}


def test_query_filters(tmp_path):
    repo = _repo(tmp_path)
    repo.record_system_event("a", level="INFO")
    repo.record_system_event("b", level="ERROR", component="llm")
    repo.record_system_event("c", level="WARNING", run_id="rx")
    assert len(repo.query_system_events(level="ERROR")) == 1
    assert repo.query_system_events(component="llm")[0]["event_type"] == "b"
    assert repo.query_system_events(run_id="rx")[0]["event_type"] == "c"
    assert len(repo.query_system_events(limit=2)) == 2


def test_invalid_level_rejected(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(ValueError):
        repo.record_system_event("x", level="LOUD")


def test_prune_respects_max_rows(tmp_path):
    repo = _repo(tmp_path)
    for index in range(7):
        repo.record_system_event("bulk", level="INFO", details={"i": index})
    deleted = repo.prune_system_events(retention_days=30, max_rows=3)
    assert deleted >= 4
    assert len(repo.query_system_events(limit=50)) == 3


def test_emit_event_persists_and_mirrors_jsonl(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    jsonl = tmp_path / "events.jsonl"
    monkeypatch.setenv("YT_EVENTS_LOG_PATH", str(jsonl))
    assert emit_event(
        "guard_triggered",
        level="WARNING",
        message="hola",
        db_path=repo.db_path,
        component="resource_guard",
    )
    rows = repo.query_system_events()
    assert rows and rows[0]["message"] == "hola"
    lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["persisted"] is True
    assert payload["component"] == "resource_guard"


def test_emit_event_never_raises_on_bad_db(tmp_path, monkeypatch):
    monkeypatch.setenv("YT_EVENTS_LOG_PATH", str(tmp_path / "mirror.jsonl"))
    broken = tmp_path / "not_a_db.sqlite"
    broken.write_text("esto no es una base de datos", encoding="utf-8")
    assert emit_event("x", db_path=str(broken)) is False  # no exception


def test_emit_error_includes_diagnostics(tmp_path, monkeypatch):
    from src.core.errors import TransientAPIError

    repo = _repo(tmp_path)
    monkeypatch.setenv("YT_EVENTS_LOG_PATH", str(tmp_path / "m.jsonl"))
    emit_error("run_failed", TransientAPIError("down", http_status=503), db_path=repo.db_path)
    row = repo.query_system_events()[0]
    details = json.loads(row["details_json"])
    assert details["diagnostics"]["error_type"] == "TransientAPIError"
    assert details["diagnostics"]["retryable"] is True
    assert row["error_code"] in {"api", "TransientAPIError"}


def test_run_context_flows_into_emit(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    monkeypatch.setenv("YT_EVENTS_LOG_PATH", str(tmp_path / "m.jsonl"))
    set_run_context(run_id="abc", channel="aelithia", component="pipeline", stage="tts")
    emit_event("stage_note", db_path=repo.db_path)
    row = repo.query_system_events()[0]
    assert row["run_id"] == "abc"
    assert row["channel"] == "aelithia"
    assert row["stage"] == "tts"


def test_update_run_context_merges():
    set_run_context(run_id="r", channel="moku")
    update_run_context(stage="compose")
    context = get_run_context()
    assert context.run_id == "r" and context.stage == "compose"


def test_logging_filter_injects_correlation(caplog):
    from src.log import RunContextFilter

    logger = logging.getLogger("yt_auto.test_filter_case")
    handler = caplog.handler
    handler.addFilter(RunContextFilter())
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG)
    set_run_context(run_id="rid9", stage="qa")
    logger.info("con contexto")
    record = caplog.records[-1]
    assert record.run_id == "rid9"
    assert record.stage == "qa"


def test_recent_failed_runs_shape(tmp_path):
    repo = _repo(tmp_path)
    # runs table exists but is empty → empty list, no crash
    assert repo.recent_failed_runs(limit=5) == []
