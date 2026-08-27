"""Adversarial stress test for CircuitBreaker state machine transitions and Gemini provider."""

import time
from unittest.mock import patch, MagicMock
import pytest

from src.core.providers import (
    CircuitBreaker,
    CircuitState,
    CapabilityUnavailable,
)
from src.llm import _curate_with_gemini, _get_gemini_circuit_breaker


@pytest.mark.unit
class TestCircuitBreakerStateTransitionsStress:
    """Stress test the complete state machine lifecycle of CircuitBreaker:
    CLOSED -> consecutive failures >= threshold -> OPEN -> cooldown -> HALF_OPEN -> CLOSED / OPEN.
    """

    def test_circuit_breaker_full_lifecycle(self, monkeypatch):
        # Deterministic virtual clock
        virtual_time = [1000.0]
        monkeypatch.setattr(time, "monotonic", lambda: virtual_time[0])

        cb = CircuitBreaker(
            failure_threshold=3,
            cooldown_seconds=10.0,
            half_open_max_trials=1,
            name="test_lifecycle",
        )

        # 1. Initially CLOSED
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True
        assert cb.is_open() is False
        assert cb.retry_after() == 0.0

        # 2. Record 2 failures (below threshold 3) -> remains CLOSED
        cb.record_failure(RuntimeError("error 1"))
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

        cb.record_failure(RuntimeError("error 2"))
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

        # 3. 3rd failure hits threshold -> transitions to OPEN
        cb.record_failure(RuntimeError("error 3"))
        assert cb.state == CircuitState.OPEN
        assert cb.is_open() is True
        assert cb.can_execute() is False
        assert cb.retry_after() > 0.0

        # 4. While OPEN, call() raises CapabilityUnavailable immediately without invoking target func
        mock_func = MagicMock()
        with pytest.raises(CapabilityUnavailable) as exc_info:
            cb.call(mock_func)
        assert "OPEN" in str(exc_info.value)
        mock_func.assert_not_called()

        # 5. Advance time past cooldown (15s > 10s) -> transitions to HALF_OPEN
        virtual_time[0] += 15.0
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.is_open() is False
        assert cb.can_execute() is True

        # 6. In HALF_OPEN, trial request failure -> immediately transitions back to OPEN
        cb.record_failure(RuntimeError("half open trial failed"))
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

        # 7. Advance time again past cooldown -> HALF_OPEN -> trial succeeds -> transitions to CLOSED
        virtual_time[0] += 15.0
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.can_execute() is True

        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True
        assert cb._consecutive_failures == 0

    def test_circuit_breaker_call_wrapper_success_and_failure(self):
        cb = CircuitBreaker(
            failure_threshold=2,
            cooldown_seconds=10.0,
            name="test_call_wrapper",
        )

        def succeeding_fn(x, y):
            return x + y

        def failing_fn():
            raise ConnectionError("Network down")

        # Test successful calls via call()
        assert cb.call(succeeding_fn, 5, 7) == 12
        assert cb.state == CircuitState.CLOSED

        # Test failure 1
        with pytest.raises(ConnectionError):
            cb.call(failing_fn)
        assert cb.state == CircuitState.CLOSED

        # Test failure 2 (hits threshold)
        with pytest.raises(ConnectionError):
            cb.call(failing_fn)
        assert cb.state == CircuitState.OPEN

        # Subsequent call raises CapabilityUnavailable
        with pytest.raises(CapabilityUnavailable):
            cb.call(succeeding_fn, 1, 2)


@pytest.mark.unit
class TestGeminiProviderCircuitBreakerIntegration:
    """Test Gemini Provider B interaction with CircuitBreaker under error conditions."""

    def test_gemini_curation_skips_when_circuit_open(self, monkeypatch):
        cb = _get_gemini_circuit_breaker()
        cb.reset()

        monkeypatch.setenv("GEMINI_API_KEY", "dummy_key_12345")
        monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")

        # Force breaker to OPEN
        for _ in range(cb.failure_threshold):
            cb.record_failure(RuntimeError("Forced failure"))
        assert cb.is_open() is True

        with patch("requests.post") as mock_post:
            result = _curate_with_gemini("Genera un guión de terror")
            assert result is None
            mock_post.assert_not_called()

        cb.reset()

    def test_gemini_curation_handles_http_errors_and_trips_breaker(self, monkeypatch):
        cb = _get_gemini_circuit_breaker()
        cb.reset()

        monkeypatch.setenv("GEMINI_API_KEY", "dummy_key_12345")

        with patch("requests.post") as mock_post:
            # Mock 500 error
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.text = "Internal Server Error"
            mock_post.return_value = mock_resp

            # Trigger failures up to threshold
            for _ in range(cb.failure_threshold):
                res = _curate_with_gemini("Prompt de prueba")
                assert res is None

            # Breaker should now be OPEN
            assert cb.is_open() is True

        cb.reset()

    def test_gemini_curation_successful_response_records_success(self, monkeypatch):
        cb = _get_gemini_circuit_breaker()
        cb.reset()

        monkeypatch.setenv("GEMINI_API_KEY", "dummy_key_12345")

        valid_gemini_reply = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    "Esta es una historia de terror completa y detallada sobre una mansión abandonada "
                                    "en la colina. Las luces parpadeaban y las sombras se movían solas por los pasillos. "
                                    "Nadie que entró volvió a salir jamás de aquel lugar maldito."
                                )
                            }
                        ]
                    }
                }
            ]
        }

        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = valid_gemini_reply
            mock_post.return_value = mock_resp

            result = _curate_with_gemini("Escribe un relato de terror")
            assert result is not None
            assert "mansión abandonada" in result
            assert cb.state == CircuitState.CLOSED

        cb.reset()
