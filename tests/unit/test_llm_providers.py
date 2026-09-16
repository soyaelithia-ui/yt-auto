"""Unit tests for LLM providers, REST Gemini integration, CircuitBreaker, and single-pass translation."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from src.core.domain import AIProviderChainExhausted
from src.core.providers import CapabilityUnavailable, CircuitBreaker, CircuitState
from src.llm import (
    _curate_with_gemini,
    curate_script,
    ensure_spanish_source,
    is_spanish_text,
)


class TestCircuitBreaker:
    """Comprehensive test suite for CircuitBreaker state transitions and behavior."""

    def test_circuit_breaker_initial_state_closed(self):
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10.0, name="test_init")
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True
        assert cb.is_open() is False
        assert cb.retry_after() == 0.0

    def test_circuit_breaker_trips_to_open_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=60.0, name="test_trip")
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False
        assert cb.is_open() is True
        assert cb.retry_after() > 0.0

    def test_circuit_breaker_half_open_recovery_on_success(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=10.0, name="test_half_open")
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

        # Simulate cooldown expiry
        cb._opened_at = time.monotonic() - 15.0
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.can_execute() is True

        # Successful test request restores CLOSED
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_circuit_breaker_half_open_reopens_on_failure(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=10.0, name="test_half_open_fail")
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Simulate cooldown expiry
        cb._opened_at = time.monotonic() - 15.0
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.can_execute() is True

        # Failed trial in HALF_OPEN immediately trips back to OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_circuit_breaker_reset(self):
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0, name="test_reset")
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_circuit_breaker_call_wrapper(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=10.0, name="test_call")

        # Success path
        result = cb.call(lambda x, y: x + y, 2, 3)
        assert result == 5

        # Error path
        def faulty():
            raise RuntimeError("upstream exploded")

        with pytest.raises(RuntimeError):
            cb.call(faulty)
        with pytest.raises(RuntimeError):
            cb.call(faulty)

        # Now tripped
        assert cb.is_open() is True
        with pytest.raises(CapabilityUnavailable):
            cb.call(lambda: "never called")


class TestGeminiDirectREST:
    """Tests for direct REST Gemini curation and circuit breaker integration."""

    def test_gemini_rest_success(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake_test_key_12345")
        monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash-high")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "<script>En las profundidades del laboratorio abandonado, los sensores registraron una señal anómala que nadie esperaba encontrar jamás. Las luces parpadearon en la oscuridad absoluta mientras los registros se borraban uno a uno.</script>"
                            }
                        ]
                    }
                }
            ]
        }

        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = _curate_with_gemini("Prompt de prueba para curación")
            assert result is not None
            assert "En las profundidades del laboratorio abandonado" in result
            assert "<script>" not in result
            mock_post.assert_called_once()
            called_url = mock_post.call_args[0][0]
            called_headers = mock_post.call_args[1].get("headers", {})
            assert "generativelanguage.googleapis.com" in called_url
            assert called_headers.get("x-goog-api-key") == "fake_test_key_12345"
            assert "gemini-3.8-flash-high" in called_url

    def test_gemini_rest_http_error_records_failure(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake_key")

        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"

        with patch("requests.post", return_value=mock_resp):
            result = _curate_with_gemini("Prompt de prueba")
            assert result is None

    def test_gemini_rest_missing_key_returns_none(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        result = _curate_with_gemini("Prompt de prueba")
        assert result is None


class TestEnsureSpanishSource:
    """Tests for single-pass pre-curation translation via ensure_spanish_source."""

    def test_spanish_text_and_title_pass_through_intact(self):
        spanish_text = (
            "Esta es una historia de terror completamente en español donde los "
            "investigadores de la fundación llegaron a la celda de contención "
            "cuando la alarma comenzó a sonar en medio de la noche."
        )
        spanish_title = "El Misterio de la Celda 404"

        content, title = ensure_spanish_source(spanish_text, spanish_title)
        assert content == spanish_text
        assert "El Misterio de la Celda 404" in title

    def test_english_text_translated_once(self):
        english_text = (
            "I used to work the night shift at an old gas station in the middle of nowhere. "
            "One stormy night, a strange customer walked in with glowing red eyes and no shadow."
        )
        english_title = "The Midnight Customer at the Gas Station"

        content, title = ensure_spanish_source(english_text, english_title)
        assert content is not None
        assert title is not None
        assert len(content) > 0
        assert len(title) > 0

    def test_empty_inputs_handled_safely(self):
        content, title = ensure_spanish_source("", "")
        assert content == ""
        assert title == "Relato Enigmático"
