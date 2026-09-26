from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch
import pytest

from src.agents.base_agent import (
    AIProviderChainExhausted,
    AgentRecoveryPolicy,
    CircuitBreaker,
    ProgrammaticAgent,
    RecoveryDecision,
)


def test_recovery_decision_dataclass_attributes():
    decision = RecoveryDecision(
        action="adjust",
        reason="semantic_drift_adjustment",
        attempt=2,
        correction_count=1,
        adjustments={"temperature": 0.1, "reasoning_effort": "medium", "compact_context": True},
        rationale="Repeated validation failure",
    )
    assert decision.action == "adjust"
    assert decision.reason == "semantic_drift_adjustment"
    assert decision.attempt == 2
    assert decision.correction_count == 1
    assert decision.adjustments == {"temperature": 0.1, "reasoning_effort": "medium", "compact_context": True}
    assert decision.rationale == "Repeated validation failure"
    assert isinstance(decision.timestamp, str)

    trace = decision.as_trace_record("validation: field X invalid")
    assert trace == {
        "attempt": 2,
        "action": "adjust",
        "reason": "semantic_drift_adjustment",
        "error": "validation: field X invalid",
        "adjustments": {"temperature": 0.1, "reasoning_effort": "medium", "compact_context": True},
        "rationale": "Repeated validation failure",
        "timestamp": decision.timestamp,
    }


def test_recovery_policy_decide_routing():
    policy = AgentRecoveryPolicy(max_attempts=3, max_corrections=2, retry_delay_seconds=0.1)

    # Transient transport failure -> retry, transient_execution_failure
    d_retry = policy.decide("connection reset by peer", attempt=1, correction_count=0)
    assert d_retry.action == "retry"
    assert d_retry.reason == "transient_execution_failure"

    # First schema validation failure -> correct, structured_output_validation
    d_correct = policy.decide("validation: missing 'loop_category'", attempt=1, correction_count=0)
    assert d_correct.action == "correct"
    assert d_correct.reason == "structured_output_validation"

    # Repeated validation failure with prior correction history -> adjust, semantic_drift_adjustment
    history = [{"action": "correct", "reason": "structured_output_validation"}]
    d_adjust = policy.decide(
        "validation: invalid 'loop_category'",
        attempt=2,
        correction_count=1,
        failure_history=history,
    )
    assert d_adjust.action == "adjust"
    assert d_adjust.reason == "semantic_drift_adjustment"
    assert d_adjust.adjustments == {"temperature": 0.1, "reasoning_effort": "medium", "compact_context": True}

    # Saturation signal (429, RESOURCE_EXHAUSTED) -> stop, provider_saturation
    d_sat_429 = policy.decide("HTTP 429 Too Many Requests", attempt=1, correction_count=0)
    assert d_sat_429.action == "stop"
    assert d_sat_429.reason == "provider_saturation"

    d_sat_res = policy.decide("google.api_core.exceptions.ResourceExhausted: 429 RESOURCE_EXHAUSTED", attempt=1, correction_count=0)
    assert d_sat_res.action == "stop"
    assert d_sat_res.reason == "provider_saturation"

    # Budget exhaustion: attempt >= max_attempts
    d_max_att = policy.decide("temporary socket failure", attempt=3, correction_count=0)
    assert d_max_att.action == "stop"
    assert d_max_att.reason == "recovery_budget_exhausted"

    # Budget exhaustion: correction_count >= max_corrections
    d_max_corr = policy.decide("validation: another error", attempt=2, correction_count=2)
    assert d_max_corr.action == "stop"
    assert d_max_corr.reason == "recovery_budget_exhausted"


def test_agentic_self_adjustment_hyperparameter_adaptation(tmp_path: Path):
    CircuitBreaker.reset_all()
    recorded_invocations: list[dict[str, Any]] = []

    def mock_chat(task: str, **kwargs: Any) -> dict[str, Any]:
        recorded_invocations.append({
            "task": task,
            "hyperparameters": dict(agent.current_hyperparameters) if hasattr(agent, "current_hyperparameters") else kwargs,
        })
        if len(recorded_invocations) < 3:
            return {"status": "SUCCESS", "response": "bad", "structured_output": {"bad": True}}
        return {"status": "SUCCESS", "response": "good", "structured_output": {"good": True}}

    def validator(data: dict) -> None:
        if not data.get("structured_output", {}).get("good"):
            raise ValueError("validation: missing 'good'")

    agent = ProgrammaticAgent(
        task_result_path=tmp_path / "result.json",
        instance_id="adjustment_test",
        app_data_dir=tmp_path / "appdata",
        response_validator=validator,
        recovery_policy=AgentRecoveryPolicy(max_attempts=3, max_corrections=2, retry_delay_seconds=0),
    )

    with patch.object(agent, "_chat_cli_fallback", side_effect=mock_chat):
        path = asyncio.run(agent._run_async("initial task prompt"))

    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["status"] == "ok"
    assert doc["failure_evidence"]["recovered"] is True
    trace = doc["failure_evidence"]["decision_trace"]
    actions = [t["action"] for t in trace]
    assert "correct" in actions
    assert "adjust" in actions
    adjust_record = next(t for t in trace if t["action"] == "adjust")
    assert adjust_record["adjustments"].get("temperature") == 0.1
    assert adjust_record["adjustments"].get("compact_context") is True


def test_agent_fail_closed_on_budget_exhaustion(tmp_path: Path):
    CircuitBreaker.reset_all()
    agent = ProgrammaticAgent(
        task_result_path=tmp_path / "result.json",
        instance_id="budget_exhaust_test",
        app_data_dir=tmp_path / "appdata",
        recovery_policy=AgentRecoveryPolicy(max_attempts=2, max_corrections=1, retry_delay_seconds=0),
    )
    with patch.object(agent, "_chat_cli_fallback", side_effect=RuntimeError("connection error")):
        with pytest.raises(AIProviderChainExhausted):
            asyncio.run(agent._run_async("failing task"))

    doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert doc["status"] == "error"
    assert doc["failure_evidence"]["recovered"] is False
    assert len(doc["failure_evidence"]["decision_trace"]) == 2
    assert doc["failure_evidence"]["decision_trace"][-1]["action"] == "stop"
    assert doc["failure_evidence"]["decision_trace"][-1]["reason"] == "recovery_budget_exhausted"


def test_decision_trace_telemetry_persisted_in_task_result(tmp_path: Path):
    CircuitBreaker.reset_all()
    calls = []

    def mock_chat(task: str) -> dict:
        calls.append(task)
        if len(calls) == 1:
            return {"status": "SUCCESS", "response": "invalid"}
        return {"status": "SUCCESS", "response": "valid"}

    def validator(data: dict) -> None:
        if data.get("response") != "valid":
            raise ValueError("validation: contract violation")

    agent = ProgrammaticAgent(
        task_result_path=tmp_path / "result.json",
        instance_id="telemetry_test",
        app_data_dir=tmp_path / "appdata",
        response_validator=validator,
        recovery_policy=AgentRecoveryPolicy(max_attempts=3, max_corrections=2, retry_delay_seconds=0),
    )

    with patch.object(agent, "_chat_cli_fallback", side_effect=mock_chat):
        path = asyncio.run(agent._run_async("telemetry task"))

    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["failure_evidence"]["recovered"] is True
    trace = doc["failure_evidence"]["decision_trace"]
    assert len(trace) >= 1
    first_record = trace[0]
    assert first_record["attempt"] == 1
    assert first_record["action"] == "correct"
    assert first_record["reason"] == "structured_output_validation"
    assert "contract violation" in first_record["error"]
    assert "rationale" in first_record
    assert "timestamp" in first_record


def test_circuit_breaker_isolation_and_immediate_saturation_trip():
    CircuitBreaker.reset_all()
    cb_a = CircuitBreaker.get("instance_a")
    cb_b = CircuitBreaker.get("instance_b")

    assert cb_a is not cb_b
    assert not cb_a.is_open()
    assert not cb_b.is_open()

    cb_a.record_failure("RESOURCE_EXHAUSTED: quota exceeded")
    assert cb_a.is_open(), "Circuit breaker must open immediately on saturation"
    assert not cb_b.is_open(), "Other instance circuit breaker must remain closed (isolated)"

    cb_b.record_failure("transient network glitch")
    assert not cb_b.is_open()
    cb_b.record_failure("transient network glitch")
    assert not cb_b.is_open()
    cb_b.record_failure("transient network glitch")
    assert cb_b.is_open(), "Circuit breaker must open after threshold failures"


def test_recovery_policy_is_bounded_and_explicit():
    policy = AgentRecoveryPolicy(max_attempts=2, max_corrections=1, retry_delay_seconds=0)
    assert policy.decide("temporary socket failure", attempt=1, correction_count=0).action == "retry"
    assert policy.decide("validation: missing field", attempt=1, correction_count=0).action == "correct"
    assert policy.decide("429 quota", attempt=1, correction_count=0).action == "stop"
    assert policy.decide("temporary socket failure", attempt=2, correction_count=0).action == "stop"
