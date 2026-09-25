"""Unit tests for audio prompt leak telemetry and cluster alert escalation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.repository import QueueRepository, connect
from src.observability import clear_run_context, set_run_context
from src.sanitizer.security import PromptLeakError, validate_semantic_barrier
from src.sanitizer.tts import validate_pre_tts_script


@pytest.fixture(autouse=True)
def _clean_run_context():
    clear_run_context()
    yield
    clear_run_context()


@pytest.fixture
def repo(tmp_path: Path) -> QueueRepository:
    db_path = tmp_path / "test_leaks.db"
    r = QueueRepository(db_path)
    r.initialize()
    return r


def test_pre_tts_taboo_phrase_interception(repo: QueueRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert validate_pre_tts_script intercepts taboo phrases, emits audio_prompt_leak (WARNING), and re-raises PromptLeakError."""
    monkeypatch.setenv("DEFAULT_DB_PATH", str(repo.db_path))
    set_run_context(channel="horror", story_id="story-taboo-1", run_id="run-taboo-1", stage="stage_4_audio")

    text = "Aquí tienes tu guion para el locutor. La noche era fría y oscura en el bosque."

    with pytest.raises(PromptLeakError) as exc_info:
        validate_pre_tts_script(text)

    assert "Aquí tienes" in str(exc_info.value) or "taboo" in str(exc_info.value).lower()

    with connect(repo.db_path, read_only=True) as conn:
        events = conn.execute(
            "SELECT * FROM system_events WHERE event_type = 'audio_prompt_leak'"
        ).fetchall()
        assert len(events) >= 1
        ev = events[0]
        assert ev["level"] == "WARNING"
        assert ev["channel"] == "horror"
        details = json.loads(ev["details_json"])
        assert "leak_snippet" in details
        assert len(details["leak_snippet"]) <= 120


def test_pre_tts_prompt_leak_pattern_interception(repo: QueueRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert meta-cues emit audio_prompt_leak with truncated snippet <= 120 chars and matched pattern."""
    monkeypatch.setenv("DEFAULT_DB_PATH", str(repo.db_path))
    set_run_context(channel="scifi", story_id="story-scifi-9", run_id="run-scifi-9", stage="stage_2_script")

    long_suffix = " El sujeto de pruebas no mostró signos de agresión durante la primera fase de observación." * 5
    text = f"Como modelo de lenguaje no puedo experimentar emociones.{long_suffix}"

    with pytest.raises(PromptLeakError):
        validate_pre_tts_script(text)

    with connect(repo.db_path, read_only=True) as conn:
        events = conn.execute(
            "SELECT * FROM system_events WHERE event_type = 'audio_prompt_leak' AND channel = 'scifi'"
        ).fetchall()
        assert len(events) >= 1
        ev = events[-1]
        details = json.loads(ev["details_json"])
        assert "leak_snippet" in details
        assert len(details["leak_snippet"]) <= 120
        assert "matched_pattern" in details
        assert details["matched_pattern"] != ""


def test_prompt_leak_cluster_escalation(repo: QueueRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert >3 prompt leaks for the same model/channel within 30 minutes triggers send_operational_alert()."""
    monkeypatch.setenv("DEFAULT_DB_PATH", str(repo.db_path))
    set_run_context(channel="horror", story_id="story-cluster", run_id="run-cluster", stage="stage_2_script")

    # Reset cluster tracking state before test
    from src.sanitizer import security
    if hasattr(security, "_reset_leak_cluster_tracker"):
        security._reset_leak_cluster_tracker()

    mock_alert = MagicMock(return_value=True)
    monkeypatch.setattr("src.sanitizer.security.send_operational_alert", mock_alert, raising=False)

    taboo_samples = [
        "Aquí tienes tu guion 1 para el locutor de la anomalía.",
        "Aquí tienes tu guion 2 sin etiquetas para el canal.",
        "Aquí tienes tu guion 3 tono documental sin relleno.",
        "Aquí tienes tu guion 4 fin del guion y reglas obligatorias.",
    ]

    for idx, sample in enumerate(taboo_samples):
        try:
            validate_pre_tts_script(sample)
        except PromptLeakError:
            pass

    # The 4th leak (>3 within 30 min) MUST have triggered send_operational_alert
    assert mock_alert.called
    call_args = mock_alert.call_args
    subject = call_args[0][0] if call_args[0] else call_args[1].get("subject", "")
    assert "prompt leak" in subject.lower() or "cluster" in subject.lower()
