"""Centralized typed exception hierarchy, policy classification engine, and diagnostics formatting."""

from __future__ import annotations

import http.client
import socket
import traceback
import urllib.error
from typing import Any, Optional


class PipelineError(Exception):
    """Base domain exception for all YT_auto pipeline errors."""

    def __init__(
        self,
        message: str,
        component: str = "pipeline",
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.component = component
        self.retryable = retryable
        self.details = dict(details) if details is not None else {}
        self.code = getattr(self, "code", component)

    def __str__(self) -> str:
        return self.message


class TransientAPIError(PipelineError):
    """Temporary network failure, rate limit (429), or server-side outage (503)."""

    def __init__(
        self,
        message: str,
        http_status: int | None = None,
        provider: str | None = None,
        details: dict[str, Any] | None = None,
        component: str = "api",
    ) -> None:
        merged_details = dict(details) if details is not None else {}
        if http_status is not None:
            merged_details.setdefault("http_status", http_status)
        if provider is not None:
            merged_details.setdefault("provider", provider)

        super().__init__(
            message=message,
            component=component,
            retryable=True,
            details=merged_details,
        )
        self.http_status = http_status
        self.provider = provider


class PermanentAPIError(PipelineError):
    """Unrecoverable API error: 401/403 auth failure, 400/422 validation, or 404."""

    def __init__(
        self,
        message: str,
        http_status: int | None = None,
        provider: str | None = None,
        details: dict[str, Any] | None = None,
        component: str = "api",
    ) -> None:
        merged_details = dict(details) if details is not None else {}
        if http_status is not None:
            merged_details.setdefault("http_status", http_status)
        if provider is not None:
            merged_details.setdefault("provider", provider)

        super().__init__(
            message=message,
            component=component,
            retryable=False,
            details=merged_details,
        )
        self.http_status = http_status
        self.provider = provider


class QuotaExceededError(PermanentAPIError):
    """API or account credit exhaustion requiring quota replenishment or wait state."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        quota_type: str | None = None,
        details: dict[str, Any] | None = None,
        http_status: int | None = 429,
        component: str = "quota",
    ) -> None:
        merged_details = dict(details) if details is not None else {}
        if quota_type is not None:
            merged_details.setdefault("quota_type", quota_type)

        super().__init__(
            message=message,
            http_status=http_status,
            provider=provider,
            details=merged_details,
            component=component,
        )
        self.quota_type = quota_type
        self.retryable = False


class LLMGenerationError(PipelineError):
    """Narrative generation, prompt execution, or JSON parsing failures in LLM."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        model: str | None = None,
        prompt_preview: str | None = None,
        details: dict[str, Any] | None = None,
        component: str = "llm",
        retryable: bool = False,
    ) -> None:
        merged_details = dict(details) if details is not None else {}
        if provider is not None:
            merged_details.setdefault("provider", provider)
        if model is not None:
            merged_details.setdefault("model", model)
        if prompt_preview is not None:
            merged_details.setdefault("prompt_preview", prompt_preview)

        super().__init__(
            message=message,
            component=component,
            retryable=retryable,
            details=merged_details,
        )
        self.provider = provider
        self.model = model
        self.prompt_preview = prompt_preview


class TTSSynthesisError(PipelineError):
    """Voice generation, audio conversion, or speech synthesis failures in TTS."""

    def __init__(
        self,
        message: str,
        voice: str | None = None,
        provider: str | None = "edge-tts",
        details: dict[str, Any] | None = None,
        component: str = "tts",
        retryable: bool = False,
    ) -> None:
        merged_details = dict(details) if details is not None else {}
        if voice is not None:
            merged_details.setdefault("voice", voice)
        if provider is not None:
            merged_details.setdefault("provider", provider)

        super().__init__(
            message=message,
            component=component,
            retryable=retryable,
            details=merged_details,
        )
        self.voice = voice
        self.provider = provider


class MediaCompositionError(PipelineError):
    """Video filtering, FFmpeg composition, or audio mixing failures."""

    def __init__(
        self,
        message: str,
        command: list[str] | None = None,
        returncode: int | None = None,
        stderr: str | None = None,
        details: dict[str, Any] | None = None,
        component: str = "media",
        retryable: bool = False,
    ) -> None:
        merged_details = dict(details) if details is not None else {}
        if command is not None:
            merged_details.setdefault("command", command)
        if returncode is not None:
            merged_details.setdefault("returncode", returncode)
        if stderr is not None:
            merged_details.setdefault("stderr", stderr)

        super().__init__(
            message=message,
            component=component,
            retryable=retryable,
            details=merged_details,
        )
        self.command = command or []
        self.returncode = returncode
        self.stderr = stderr


class InputValidationError(PermanentAPIError):
    """Input payload or configuration schema validation failure."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any = None,
        details: dict[str, Any] | None = None,
        component: str = "validation",
    ) -> None:
        merged_details = dict(details) if details is not None else {}
        if field is not None:
            merged_details.setdefault("field", field)
        if value is not None:
            merged_details.setdefault("value", value)

        super().__init__(
            message=message,
            http_status=400,
            provider=None,
            details=merged_details,
            component=component,
        )
        self.field = field
        self.value = value


_TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_PERMANENT_STATUS_CODES = frozenset({400, 401, 403, 404, 405, 422})
_TRANSIENT_EXCEPTION_TYPES = (
    TimeoutError,
    ConnectionError,
    socket.timeout,
    urllib.error.URLError,
    http.client.RemoteDisconnected,
)


def is_retryable(exc: BaseException) -> bool:
    """Evaluate whether an exception is retryable with exponential backoff."""
    # 1. Quota exhaustion is never immediately retryable
    if isinstance(exc, QuotaExceededError):
        return False

    # 2. Transient API errors are explicitly retryable
    if isinstance(exc, TransientAPIError):
        return True

    # 3. Permanent API errors (401, 403, 400, etc.) are never retryable
    if isinstance(exc, PermanentAPIError):
        return False

    # 4. Explicit positive retryable attribute (PipelineError, ProviderError, duck-typed)
    if getattr(exc, "retryable", None) is True:
        return True

    # 5. HTTP status code inspection
    status = getattr(exc, "http_status", None) or getattr(exc, "status_code", None)
    if status is not None:
        if status in _PERMANENT_STATUS_CODES:
            return False
        if status in _TRANSIENT_STATUS_CODES:
            return True

    # 6. Standard library / OS network & timeout exception types
    if isinstance(exc, _TRANSIENT_EXCEPTION_TYPES):
        return True

    # 7. Check cause / context chain if present
    cause = exc.__cause__ or (exc.__context__ if not getattr(exc, "__suppress_context__", False) else None)
    if cause is not None and cause is not exc:
        return is_retryable(cause)

    return False


def should_fallback(exc: BaseException) -> bool:
    """Evaluate whether an error warrants falling back to a secondary provider or model."""
    if isinstance(exc, (TTSSynthesisError, LLMGenerationError, TransientAPIError, QuotaExceededError)):
        return True

    if isinstance(exc, (InputValidationError, PermanentAPIError)):
        return False

    if exc.__cause__ is not None:
        return should_fallback(exc.__cause__)

    return False


def format_error_diagnostics(exc: BaseException) -> dict[str, Any]:
    """Format structured diagnostic payload including component, cause, and traceback."""
    cause_info: Optional[dict[str, Any]] = None
    cause = exc.__cause__ or (exc.__context__ if not getattr(exc, "__suppress_context__", False) else None)
    if cause is not None:
        cause_info = {
            "error_type": type(cause).__name__,
            "message": str(cause),
        }

    formatted_tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) if exc.__traceback__ else f"Traceback:\n  {type(exc).__name__}: {str(exc)}"

    return {
        "error_type": type(exc).__name__,
        "message": str(exc),
        "component": getattr(exc, "component", "unknown"),
        "retryable": is_retryable(exc),
        "details": getattr(exc, "details", {}),
        "cause": cause_info,
        "traceback": formatted_tb,
    }
