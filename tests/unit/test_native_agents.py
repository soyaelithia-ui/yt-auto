"""Unit tests for native Antigravity Agents using Pro harness, persistent stream, and SDK."""
import json
import os
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from src.agents.base_agent import (
    ProgrammaticAgent,
    CANONICAL_MODEL,
    CircuitBreaker,
    AgyStreamClient,
    _resolve_default_app_data_dir,
    _seed_appdata_from_secrets,
    cleanup_ephemeral_sessions,
)
from src.agents.story_director import StoryDirectorAgent, StoryInvestigatorAgent
from src.agents.atmospheric_director import AtmosphericDirectorAgent
from src.agents.translator import TranslatorAgent
from src.agents.seo_optimizer import SeoOptimizerAgent, ViralPackagingAgent
from src.agents.video_qa import VideoQAAgent, MultimodalReviewAgent


def test_canonical_model_is_gemini_flash():
    assert CANONICAL_MODEL == "gemini-3.8-flash-high"


def test_programmatic_agent_consume(tmp_path):
    res_file = tmp_path / "task_result.json"
    dummy_data = {"result": "ok", "output": {"reply": "Test reply"}}
    res_file.write_text(json.dumps(dummy_data), encoding="utf-8")
    
    consumed = ProgrammaticAgent.consume(res_file)
    assert consumed["result"] == "ok"
    assert consumed["output"]["reply"] == "Test reply"


@patch.object(ProgrammaticAgent, "_chat_cli_fallback")
def test_programmatic_agent_run_success(mock_cli, tmp_path):
    CircuitBreaker.reset_all()

    mock_cli.return_value = {
        "response": "Compilado correctamente",
        "status": "SUCCESS",
        "conversation_id": "conv_123",
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        "structured_output": None,
    }
    res_file = tmp_path / "custom_result.json"

    agent = ProgrammaticAgent(
        task_result_path=res_file,
        instance_id="test_worker",
        app_data_dir=tmp_path / "worker_appdata",
    )
    out_path = agent.run("Verificar compuertas")

    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["result"] == "ok"
    assert "Compilado correctamente" in data["output"]["reply"]
    assert data["output"]["conversation_id"] == "conv_123"
    assert data["output"]["usage"]["total_tokens"] == 15
    assert data["agent"]["instance_id"] == "test_worker"


def test_agent_defaults_are_canonical_model_and_high_effort():
    inv = StoryInvestigatorAgent()
    assert inv.model == CANONICAL_MODEL
    assert inv.reasoning_effort == "high"

    trans = TranslatorAgent()
    assert trans.model == CANONICAL_MODEL
    assert trans.reasoning_effort == "high"

    seo = SeoOptimizerAgent()
    assert seo.model == CANONICAL_MODEL
    assert seo.reasoning_effort == "high"


def test_story_director_agent_instantiation():
    agent = StoryDirectorAgent(instance_id="creative_lane", reasoning_effort="high")
    assert agent.model == CANONICAL_MODEL
    assert agent.role_name == "story-director-agent"
    assert agent.instance_id == "creative_lane"
    assert agent.reasoning_effort == "high"


def test_atmospheric_director_agent_instantiation():
    agent = AtmosphericDirectorAgent(instance_id="atmos_lane", reasoning_effort="high")
    assert agent.model == CANONICAL_MODEL
    assert agent.role_name == "atmospheric-director-agent"
    assert agent.instance_id == "atmos_lane"


def test_story_investigator_agent_instantiation():
    agent = StoryInvestigatorAgent(instance_id="creative_lane", reasoning_effort="high")
    assert agent.model == CANONICAL_MODEL
    assert agent.instance_id == "creative_lane"
    assert agent.reasoning_effort == "high"


def test_translator_agent_instantiation():
    agent = TranslatorAgent(instance_id="trans_lane", reasoning_effort="low")
    assert agent.model == CANONICAL_MODEL
    assert agent.role_name == "translator-agent"
    assert agent.instance_id == "trans_lane"
    assert agent.reasoning_effort == "low"


def test_seo_optimizer_agent_instantiation():
    agent = SeoOptimizerAgent(instance_id="seo_lane", reasoning_effort="low")
    assert agent.model == CANONICAL_MODEL
    assert agent.instance_id == "seo_lane"
    assert agent.reasoning_effort == "low"


def test_seo_optimizer_agent_optimize_with_agent_mock(monkeypatch, tmp_path):
    monkeypatch.setenv("USE_AGENT_HARNESS", "1")
    agent = SeoOptimizerAgent(instance_id="seo_lane")
    
    valid_metadata = {
        "version": "2.0",
        "topic": "SCP-173",
        "target_format": "short",
        "viral_title_options": ["SCP-173 Revelado", "El Monstruo de Concreto", "No Parpadees Jamas"],
        "selected_title": "SCP-173 Revelado",
        "description": "00:00 - Intro\n00:30 - Climax del SCP\n00:50 - Conclusion final",
        "tags": ["scp", "horror", "creepy"],
        "hashtags": ["#scp", "#shorts"],
        "pinned_comment": "Qué opinas de SCP-173?",
        "thumbnail_concepts": [
            {
                "visual_layout": "Primer plano estatua",
                "big_headline": "NO PARPADEES",
                "color_palette": ["#ff0000", "#000000"],
            }
        ],
    }
    
    mock_payload = {
        "result": "ok",
        "output": {
            "reply": json.dumps(valid_metadata),
            "structured_output": valid_metadata,
        },
    }
    
    with patch.object(ProgrammaticAgent, "run", return_value=tmp_path / "task_result.json"), \
         patch.object(ProgrammaticAgent, "consume", return_value=mock_payload):
        meta = agent.optimize("SCP-173", target_format="short", niche="Horror", use_agent=True)
        assert meta["selected_title"] == "SCP-173 Revelado"
        assert len(meta["viral_title_options"]) == 3


def test_default_app_data_dir_isolation(monkeypatch, tmp_path):
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


def test_multi_instance_app_data_dir_isolation(monkeypatch, tmp_path):
    # Distinct instances should resolve to distinct directories
    inst_1 = _resolve_default_app_data_dir(instance_id="worker_1")
    inst_2 = _resolve_default_app_data_dir(instance_id="worker_2")
    assert inst_1 != inst_2
    assert "worker_1" in str(inst_1)
    assert "worker_2" in str(inst_2)


def test_circuit_breaker_multi_instance_isolation():
    CircuitBreaker.reset_all()
    cb1 = CircuitBreaker.get("instance_alpha")
    cb2 = CircuitBreaker.get("instance_beta")

    assert cb1 is not cb2
    assert not cb1.is_open()
    assert not cb2.is_open()

    # Trip cb1
    cb1.record_failure()
    cb1.record_failure()
    cb1.record_failure()

    assert cb1.is_open()
    assert not cb2.is_open()  # cb2 must remain closed and healthy


@patch("subprocess.run")
def test_agy_stream_client_send_task(mock_run, tmp_path):
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps({
        "status": "SUCCESS",
        "response": "Respuesta por stream",
        "conversation_id": "stream_conv_1",
    })
    mock_run.return_value = mock_proc

    client = AgyStreamClient(
        model="gemini-3.8-flash-high",
        reasoning_effort="high",
        app_data_dir=tmp_path / "app_data",
    )
    res = client.send_task("Hola stream")

    assert res["status"] == "SUCCESS"
    assert res["response"] == "Respuesta por stream"
    assert res["conversation_id"] == "stream_conv_1"
    client.close()


def test_native_sdk_chat_async_mock(tmp_path):
    import asyncio
    agent = ProgrammaticAgent(
        task_result_path=tmp_path / "sdk_result.json",
        use_sdk=True,
        instance_id="sdk_test",
        app_data_dir=tmp_path / "sdk_appdata",
    )
    with patch.object(agent, "_can_use_sdk", return_value=True), \
         patch.object(agent, "_chat_async") as mock_sdk:
        mock_sdk.return_value = {
            "response": "Respuesta directa SDK",
            "status": "SUCCESS",
            "conversation_id": "sdk_conv_99",
            "usage": {"total_tokens": 42},
            "structured_output": None,
        }
        res_path = asyncio.run(agent._run_async("Prompt SDK"))
        assert res_path.exists()
        doc = json.loads(res_path.read_text(encoding="utf-8"))
        assert doc["result"] == "ok"
        assert doc["output"]["reply"] == "Respuesta directa SDK"
        assert doc["agent"]["connection"] == "antigravity-sdk"


def test_cleanup_ephemeral_sessions(tmp_path):
    import time
    import os

    app_dir = tmp_path / "app_data"
    brain_dir = app_dir / "brain"
    brain_dir.mkdir(parents=True)

    old_conv = brain_dir / "old_conv_1"
    old_conv.mkdir()
    (old_conv / "data.json").write_text("{}")

    # Set mtime to 12 hours ago (cutoff is 6 hours)
    past_time = time.time() - (12 * 3600)
    os.utime(old_conv, (past_time, past_time))

    new_conv = brain_dir / "new_conv_1"
    new_conv.mkdir()
    (new_conv / "data.json").write_text("{}")

    removed = cleanup_ephemeral_sessions(app_data_dir=app_dir, max_age_hours=6)
    assert removed == 1
    assert not old_conv.exists()
    assert new_conv.exists()


def test_seed_appdata_from_secrets_updates_newer(tmp_path, monkeypatch):
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    bot_appdata = tmp_path / "bot_appdata"
    bot_appdata.mkdir()

    token_src = secrets_dir / "antigravity-oauth-token"
    token_src.write_text("token_v1")
    monkeypatch.setenv("SECRETS_DIR", str(secrets_dir))

    _seed_appdata_from_secrets(bot_appdata)
    token_dst = bot_appdata / "antigravity-oauth-token"
    assert token_dst.read_text() == "token_v1"

    # Update src with newer timestamp and new content
    import time
    time.sleep(0.05)
    token_src.write_text("token_v2")
    future_time = time.time() + 10
    os.utime(token_src, (future_time, future_time))

    _seed_appdata_from_secrets(bot_appdata)
    assert token_dst.read_text() == "token_v2"


