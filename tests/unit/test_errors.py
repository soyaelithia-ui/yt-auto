"""Unit tests for centralized typed error hierarchy and policy classification engine."""

import socket
import sys
import unittest
from typing import Any

import pytest

from src.core.errors import (
    InputValidationError,
    LLMGenerationError,
    MediaCompositionError,
    PermanentAPIError,
    PipelineError,
    QuotaExceededError,
    TTSSynthesisError,
    TransientAPIError,
    format_error_diagnostics,
    is_retryable,
    should_fallback,
)


class TestPipelineErrorHierarchy(unittest.TestCase):
    """Tests for domain exception inheritance, attributes, and diagnostics context."""

    def test_pipeline_error_base_attributes(self):
        """PipelineError must initialize default component, retryable flag, and details dictionary."""
        err = PipelineError("Base pipeline failure")
        self.assertIsInstance(err, Exception)
        self.assertEqual(str(err), "Base pipeline failure")
        self.assertEqual(err.message, "Base pipeline failure")
        self.assertEqual(err.component, "pipeline")
        self.assertFalse(err.retryable)
        self.assertEqual(err.details, {})

    def test_pipeline_error_custom_attributes(self):
        """PipelineError must store explicit component, retryable flag, and custom details."""
        details = {"step": "video_render", "job_id": 42}
        err = PipelineError("Custom failure", component="orchestrator", retryable=True, details=details)
        self.assertEqual(err.component, "orchestrator")
        self.assertTrue(err.retryable)
        self.assertEqual(err.details, details)

    def test_transient_api_error_defaults_and_attributes(self):
        """TransientAPIError must inherit from PipelineError, default retryable to True, and store status/provider."""
        err = TransientAPIError(
            "Service unavailable",
            http_status=503,
            provider="gemini",
            details={"retry_after": 10},
        )
        self.assertIsInstance(err, PipelineError)
        self.assertTrue(err.retryable)
        self.assertEqual(err.http_status, 503)
        self.assertEqual(err.provider, "gemini")
        self.assertEqual(err.component, "api")
        self.assertEqual(err.details["http_status"], 503)
        self.assertEqual(err.details["provider"], "gemini")

    def test_permanent_api_error_defaults_and_attributes(self):
        """PermanentAPIError must inherit from PipelineError, default retryable to False, and store status/provider."""
        err = PermanentAPIError(
            "Unauthorized access",
            http_status=401,
            provider="gemini",
            details={"scope": "aiplatform"},
        )
        self.assertIsInstance(err, PipelineError)
        self.assertFalse(err.retryable)
        self.assertEqual(err.http_status, 401)
        self.assertEqual(err.provider, "gemini")
        self.assertEqual(err.details["http_status"], 401)

    def test_quota_exceeded_error_hierarchy_and_attributes(self):
        """QuotaExceededError must inherit from PermanentAPIError, have retryable=False, and store quota type."""
        err = QuotaExceededError(
            "Daily generation quota exhausted",
            provider="gemini",
            quota_type="rpm_tokens",
            details={"limit": 1000},
        )
        self.assertIsInstance(err, PermanentAPIError)
        self.assertIsInstance(err, PipelineError)
        self.assertFalse(err.retryable)
        self.assertEqual(err.provider, "gemini")
        self.assertEqual(err.quota_type, "rpm_tokens")
        self.assertEqual(err.http_status, 429)

    def test_llm_generation_error_attributes(self):
        """LLMGenerationError must store provider, model, prompt_preview, and component."""
        err = LLMGenerationError(
            "Invalid JSON output from model",
            provider="gemini",
            model="gemini-3.6-flash",
            prompt_preview="Generate story about...",
            details={"attempt": 3},
        )
        self.assertIsInstance(err, PipelineError)
        self.assertEqual(err.component, "llm")
        self.assertEqual(err.provider, "gemini")
        self.assertEqual(err.model, "gemini-3.6-flash")
        self.assertEqual(err.prompt_preview, "Generate story about...")

    def test_tts_synthesis_error_attributes(self):
        """TTSSynthesisError must store voice, provider, and component."""
        err = TTSSynthesisError(
            "Edge-TTS synthesis connection dropped",
            voice="es-MX-JorgeNeural",
            provider="edge-tts",
            details={"chars": 450},
        )
        self.assertIsInstance(err, PipelineError)
        self.assertEqual(err.component, "tts")
        self.assertEqual(err.voice, "es-MX-JorgeNeural")
        self.assertEqual(err.provider, "edge-tts")

    def test_media_composition_error_attributes(self):
        """MediaCompositionError must store command list, returncode, and stderr output."""
        cmd = ["ffmpeg", "-i", "in.mp4", "out.mp4"]
        err = MediaCompositionError(
            "FFmpeg composition exited with code 1",
            command=cmd,
            returncode=1,
            stderr="Error: Invalid codec parameters",
            details={"duration": 12.5},
        )
        self.assertIsInstance(err, PipelineError)
        self.assertEqual(err.component, "media")
        self.assertEqual(err.command, cmd)
        self.assertEqual(err.returncode, 1)
        self.assertEqual(err.stderr, "Error: Invalid codec parameters")

    def test_input_validation_error_attributes(self):
        """InputValidationError must inherit from PermanentAPIError and store field and value."""
        err = InputValidationError(
            "Missing required title field",
            field="title",
            value="",
        )
        self.assertIsInstance(err, PermanentAPIError)
        self.assertEqual(err.component, "validation")
        self.assertEqual(err.field, "title")
        self.assertEqual(err.value, "")


class TestPolicyEngineClassification(unittest.TestCase):
    """Tests for is_retryable and should_fallback classification policies."""

    def test_is_retryable_transient_api_error(self):
        """TransientAPIError and HTTP 503/429 transient errors must be retryable."""
        err1 = TransientAPIError("503 Service Unavailable", http_status=503)
        self.assertTrue(is_retryable(err1))

        err2 = TransientAPIError("429 Rate Limit Exceeded", http_status=429)
        self.assertTrue(is_retryable(err2))

    def test_is_retryable_network_and_timeout_errors(self):
        """Standard socket, connection, and timeout exceptions must be retryable."""
        self.assertTrue(is_retryable(TimeoutError("Operation timed out")))
        self.assertTrue(is_retryable(ConnectionResetError("Connection reset by peer")))
        self.assertTrue(is_retryable(socket.timeout("Socket read timed out")))

    def test_is_retryable_permanent_api_error(self):
        """PermanentAPIError and 400/401/403/404/422 status codes must NOT be retryable."""
        err1 = PermanentAPIError("401 Unauthorized", http_status=401)
        self.assertFalse(is_retryable(err1))

        err2 = PermanentAPIError("403 Forbidden", http_status=403)
        self.assertFalse(is_retryable(err2))

        err3 = PermanentAPIError("400 Bad Request", http_status=400)
        self.assertFalse(is_retryable(err3))

        err4 = InputValidationError("Invalid channel name", field="channel", value="unknown")
        self.assertFalse(is_retryable(err4))

    def test_is_retryable_quota_exceeded_error(self):
        """QuotaExceededError must NOT be retryable via standard transient retry."""
        quota_err = QuotaExceededError("Gemini quota exhausted", provider="gemini")
        self.assertFalse(is_retryable(quota_err))

    def test_is_retryable_chained_underlying_cause(self):
        """When an outer error wraps a transient exception, is_retryable must inspect the cause."""
        cause = ConnectionRefusedError("Connection refused by upstream")
        wrapped = PipelineError("Pipeline step failed")
        wrapped.__cause__ = cause
        self.assertTrue(is_retryable(wrapped))

    def test_is_retryable_generic_unhandled_error(self):
        """Generic unhandled exceptions (ValueError, TypeError, KeyError) must NOT be retryable."""
        self.assertFalse(is_retryable(ValueError("Invalid syntax in configuration")))
        self.assertFalse(is_retryable(KeyError("missing_key")))

    def test_should_fallback_policy(self):
        """should_fallback must return True for fallback-eligible subsystems and errors."""
        self.assertTrue(should_fallback(TTSSynthesisError("TTS failure", voice="es-MX-JorgeNeural")))
        self.assertTrue(should_fallback(LLMGenerationError("LLM parse failure", model="gemini-3.6-flash")))
        self.assertTrue(should_fallback(TransientAPIError("Primary endpoint down", http_status=503)))
        self.assertTrue(should_fallback(QuotaExceededError("Primary account quota exhausted")))

        self.assertFalse(should_fallback(InputValidationError("Invalid field", field="title")))
        self.assertFalse(should_fallback(PermanentAPIError("Invalid credentials", http_status=401)))


class TestDiagnosticsFormatting(unittest.TestCase):
    """Tests for structured diagnostic reporting and cause chain inspection."""

    def test_format_error_diagnostics_preserves_root_cause(self):
        """format_error_diagnostics must capture exception type, message, details, and root cause."""
        root = TimeoutError("HTTP connection timeout after 30s")
        try:
            try:
                raise root
            except TimeoutError as exc:
                raise LLMGenerationError(
                    "Narrative generation failed",
                    provider="gemini",
                    model="gemini-3.6-flash",
                    prompt_preview="Story about ghosts...",
                    details={"attempt": 2},
                ) from exc
        except LLMGenerationError as domain_exc:
            diagnostics = format_error_diagnostics(domain_exc)

            self.assertEqual(diagnostics["error_type"], "LLMGenerationError")
            self.assertEqual(diagnostics["message"], "Narrative generation failed")
            self.assertEqual(diagnostics["component"], "llm")
            self.assertTrue(diagnostics["retryable"])
            self.assertEqual(diagnostics["details"]["model"], "gemini-3.6-flash")
            self.assertEqual(diagnostics["details"]["provider"], "gemini")
            self.assertEqual(diagnostics["details"]["prompt_preview"], "Story about ghosts...")
            self.assertEqual(diagnostics["details"]["attempt"], 2)

            self.assertIsNotNone(diagnostics["cause"])
            self.assertEqual(diagnostics["cause"]["error_type"], "TimeoutError")
            self.assertEqual(diagnostics["cause"]["message"], "HTTP connection timeout after 30s")
            self.assertIn("Traceback", diagnostics["traceback"])

    def test_format_error_diagnostics_media_error(self):
        """format_error_diagnostics must include FFmpeg command, returncode, and stderr snippets."""
        media_err = MediaCompositionError(
            "Video composition failed",
            command=["ffmpeg", "-y", "-i", "scene.png", "out.mp4"],
            returncode=137,
            stderr="fatal: out of memory",
            details={"resolution": "1080x1920"},
        )
        diag = format_error_diagnostics(media_err)
        self.assertEqual(diag["error_type"], "MediaCompositionError")
        self.assertEqual(diag["component"], "media")
        self.assertEqual(diag["details"]["returncode"], 137)
        self.assertEqual(diag["details"]["stderr"], "fatal: out of memory")
        self.assertEqual(diag["details"]["resolution"], "1080x1920")
        self.assertEqual(diag["details"]["command"], ["ffmpeg", "-y", "-i", "scene.png", "out.mp4"])

    def test_format_error_diagnostics_without_cause_or_traceback(self):
        """format_error_diagnostics must handle simple un-raised exceptions without causes."""
        err = PipelineError("Simple un-raised pipeline error")
        diag = format_error_diagnostics(err)
        self.assertEqual(diag["error_type"], "PipelineError")
        self.assertEqual(diag["message"], "Simple un-raised pipeline error")
        self.assertIsNone(diag["cause"])
        self.assertIn("PipelineError: Simple un-raised pipeline error", diag["traceback"])

    def test_is_retryable_deeply_nested_cause(self):
        """is_retryable must inspect multiple levels of exception causes."""
        root = socket.timeout("Socket read timed out")
        mid = RuntimeError("Intermediate step failure")
        mid.__cause__ = root
        top = PipelineError("Top level orchestration failure")
        top.__cause__ = mid
        self.assertTrue(is_retryable(top))

    def test_is_retryable_duck_typed_retryable_attribute(self):
        """is_retryable should respect objects with retryable attribute like ProviderError."""
        class CustomDuckTypedError(Exception):
            retryable = True

        self.assertTrue(is_retryable(CustomDuckTypedError("Duck typed retryable error")))

