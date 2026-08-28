"""Unit tests for native Antigravity Agents using Pro harness and gemini-3.6-flash."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.agents.base_agent import ProgrammaticAgent, CANONICAL_MODEL
from src.agents.investigator import StoryInvestigatorAgent
from src.agents.translator import TranslatorAgent

def test_canonical_model_is_gemini_flash():
    assert CANONICAL_MODEL in ("gemini-3.6-flash", "gemini-3.7-flash")

def test_programmatic_agent_consume(tmp_path):
    res_file = tmp_path / "task_result.json"
    dummy_data = {"result": "ok", "output": {"reply": "Test reply"}}
    res_file.write_text(json.dumps(dummy_data), encoding="utf-8")
    
    consumed = ProgrammaticAgent.consume(res_file)
    assert consumed["result"] == "ok"
    assert consumed["output"]["reply"] == "Test reply"

@patch.object(ProgrammaticAgent, "_chat_cli_fallback")
def test_programmatic_agent_run_success(mock_cli, tmp_path):
    from src.agents.base_agent import CircuitBreaker
    CircuitBreaker.instance().reset()

    mock_cli.return_value = {
        "response": "Compilado correctamente",
        "status": "SUCCESS",
        "conversation_id": "conv_123",
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        "structured_output": None,
    }
    res_file = tmp_path / "custom_result.json"

    agent = ProgrammaticAgent(task_result_path=res_file)
    out_path = agent.run("Verificar compuertas")

    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["result"] == "ok"
    assert "Compilado correctamente" in data["output"]["reply"]
    assert data["output"]["conversation_id"] == "conv_123"
    assert data["output"]["usage"]["total_tokens"] == 15

def test_story_investigator_agent_instantiation():
    agent = StoryInvestigatorAgent()
    assert agent.model == CANONICAL_MODEL
    assert agent.role_name == "story-investigator-agent"

def test_translator_agent_instantiation():
    agent = TranslatorAgent()
    assert agent.model == CANONICAL_MODEL
    assert agent.role_name == "translator-agent"


def test_default_app_data_dir_isolation(monkeypatch, tmp_path):
    from src.agents.base_agent import _resolve_default_app_data_dir

    # When ANTIGRAVITY_AGENTS_APP_DATA_DIR is set explicitly
    isolated = tmp_path / "custom_agent_data"
    monkeypatch.setenv("ANTIGRAVITY_AGENTS_APP_DATA_DIR", str(isolated))
    monkeypatch.setenv("ANTIGRAVITY_APP_DATA_DIR", "/home/Moku/.gemini/antigravity-cli")
    assert _resolve_default_app_data_dir() == isolated.resolve()

    # When ANTIGRAVITY_AGENTS_APP_DATA_DIR is not set, it should not use host ANTIGRAVITY_APP_DATA_DIR
    monkeypatch.delenv("ANTIGRAVITY_AGENTS_APP_DATA_DIR", raising=False)
    resolved = _resolve_default_app_data_dir()
    assert "/home/Moku/.gemini/antigravity-cli" != str(resolved)
    assert ".bot_home" in str(resolved) or "secrets" in str(resolved)


def test_cleanup_ephemeral_sessions(tmp_path):
    import time
    from src.agents.base_agent import cleanup_ephemeral_sessions

    app_dir = tmp_path / "app_data"
    brain_dir = app_dir / "brain"
    brain_dir.mkdir(parents=True)

    old_conv = brain_dir / "old_conv_1"
    old_conv.mkdir()
    (old_conv / "data.json").write_text("{}")

    # Set mtime to 48 hours ago
    past_time = time.time() - (48 * 3600)
    import os
    os.utime(old_conv, (past_time, past_time))

    new_conv = brain_dir / "new_conv_1"
    new_conv.mkdir()
    (new_conv / "data.json").write_text("{}")

    removed = cleanup_ephemeral_sessions(app_data_dir=app_dir, max_age_hours=24)
    assert removed == 1
    assert not old_conv.exists()
    assert new_conv.exists()

