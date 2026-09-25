from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from src.agents.base_agent import AgentRecoveryPolicy, CircuitBreaker, ProgrammaticAgent


def test_recovery_policy_is_bounded_and_explicit():
    policy = AgentRecoveryPolicy(max_attempts=2, max_corrections=1, retry_delay_seconds=0)
    assert policy.decide("temporary socket failure", attempt=1, correction_count=0).action == "retry"
    assert policy.decide("validation: missing field", attempt=1, correction_count=0).action == "correct"
    assert policy.decide("429 quota", attempt=1, correction_count=0).action == "stop"
    assert policy.decide("temporary socket failure", attempt=2, correction_count=0).action == "stop"


def test_agent_retries_and_records_failure_evidence(tmp_path: Path):
    CircuitBreaker.reset_all()
    agent = ProgrammaticAgent(
        task_result_path=tmp_path / "result.json",
        instance_id="recovery_test",
        app_data_dir=tmp_path / "appdata",
        recovery_policy=AgentRecoveryPolicy(max_attempts=2, max_corrections=0, retry_delay_seconds=0),
    )
    responses = [RuntimeError("temporary socket failure"), {"status": "SUCCESS", "response": "ok"}]
    with patch.object(agent, "_chat_cli_fallback", side_effect=responses):
        path = asyncio.run(agent._run_async("recover this task"))

    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["result"] == "ok"
    assert doc["failure_evidence"]["recovered"] is True
    assert doc["failure_evidence"]["attempts"][0]["action"] == "retry"
    assert doc["failure_evidence"]["policy"]["max_attempts"] == 2


def test_agent_applies_one_contract_correction(tmp_path: Path):
    CircuitBreaker.reset_all()
    calls: list[str] = []

    def validator(data: dict) -> None:
        if data.get("response") != "corrected":
            raise ValueError("response must be corrected")

    agent = ProgrammaticAgent(
        task_result_path=tmp_path / "result.json",
        instance_id="correction_test",
        app_data_dir=tmp_path / "appdata",
        response_validator=validator,
        recovery_policy=AgentRecoveryPolicy(max_attempts=2, max_corrections=1, retry_delay_seconds=0),
    )

    def respond(task: str) -> dict:
        calls.append(task)
        return {"status": "SUCCESS", "response": "wrong" if len(calls) == 1 else "corrected"}

    with patch.object(agent, "_chat_cli_fallback", side_effect=respond):
        path = asyncio.run(agent._run_async("return a response"))

    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["result"] == "ok"
    assert len(calls) == 2
    assert "Correction required" in calls[1]
    assert doc["failure_evidence"]["attempts"][0]["action"] == "correct"
