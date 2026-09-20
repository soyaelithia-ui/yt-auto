"""Safe provider adapters and result verification helpers."""

from __future__ import annotations

import fcntl
import json
import os
import random
import re
import shutil
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

import threading
from enum import Enum

from src.config import SETTINGS, validate_runtime_config
from src.core.domain import (
    AIProviderChainExhausted,
    AuthenticationError,
    CanonicalChannel,
    ManualInterventionRequired,
    PermanentRejectionError,
    ProviderTimeoutError,
    ProviderValidationError,
    PublicationProof,
    QuotaError,
    canonical_channel,
)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Dedicated circuit breaker with configurable failure threshold, cooldown window,
    and half-open trial requests for AI and remote service providers."""

    _instances: dict[str, CircuitBreaker] = {}

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 120.0,
        half_open_max_trials: int = 1,
        name: str = "default",
    ) -> None:
        self.failure_threshold = max(1, int(failure_threshold))
        self.cooldown_seconds = max(0.0, float(cooldown_seconds))
        self.half_open_max_trials = max(1, int(half_open_max_trials))
        self.name = name

        self._state: CircuitState = CircuitState.CLOSED
        self._consecutive_failures: int = 0
        self._opened_at: float = 0.0
        self._half_open_trials: int = 0
        self._lock = threading.Lock()

    @classmethod
    def instance(cls, name: str = "default", **kwargs: Any) -> CircuitBreaker:
        if name not in cls._instances:
            cls._instances[name] = cls(name=name, **kwargs)
        return cls._instances[name]

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if (time.monotonic() - self._opened_at) >= self.cooldown_seconds:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_trials = 0
            return self._state

    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    def can_execute(self) -> bool:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if (time.monotonic() - self._opened_at) >= self.cooldown_seconds:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_trials = 0

            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_trials < self.half_open_max_trials:
                    self._half_open_trials += 1
                    return True
                return False
            return False

    def allow_request(self) -> bool:
        return self.can_execute()

    def record_success(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._opened_at = 0.0
            self._half_open_trials = 0

    def record_failure(self, exc: Any = None) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if self._state == CircuitState.HALF_OPEN or self._consecutive_failures >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                self._half_open_trials = 0

    def reset(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._opened_at = 0.0
            self._half_open_trials = 0

    def retry_after(self) -> float:
        with self._lock:
            if self._state == CircuitState.OPEN:
                remaining = self.cooldown_seconds - (time.monotonic() - self._opened_at)
                return max(0.0, remaining)
            return 0.0

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        if not self.can_execute():
            raise CapabilityUnavailable(
                f"Circuit breaker '{self.name}' is OPEN; cooling down for {self.retry_after():.1f}s"
            )
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as exc:
            self.record_failure(exc)
            raise


class CapabilityUnavailable(ProviderValidationError):
    code = "capability_unavailable"


@dataclass(frozen=True)
class DriveProof:
    file_id: str
    name: str
    size_bytes: int
    folder_id: str
    exists: bool

    def validate(
        self,
        *,
        expected_name: str,
        expected_size: int,
        expected_folder: str,
    ) -> None:
        if not self.file_id.strip() or not self.exists:
            raise ProviderValidationError("Drive no confirmó la existencia remota")
        if self.name != expected_name:
            raise ProviderValidationError("El nombre remoto de Drive no coincide")
        if self.size_bytes != expected_size:
            raise ProviderValidationError("El tamaño remoto de Drive no coincide")
        if self.folder_id != expected_folder:
            raise ProviderValidationError("La carpeta remota de Drive no coincide")


def classify_provider_failure(detail: str) -> type[Exception]:
    lowered = (detail or "").lower()
    if any(token in lowered for token in ("quota", "limit reached", "resource_exhausted")):
        return QuotaError
    if any(
        token in lowered
        for token in ("login", "sign in", "unauthorized", "invalid_grant", "session expired", "insufficient permissions", "insufficientpermissions", "file not found")
    ):
        return AuthenticationError
    if any(token in lowered for token in ("captcha", "verify it's you", "manual review")):
        return ManualInterventionRequired
    if any(token in lowered for token in ("policy violation", "permanently rejected")):
        return PermanentRejectionError
    return ProviderValidationError


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)




def publication_proof_from_response(
    response: Mapping[str, Any],
    *,
    expected_channel: str | CanonicalChannel,
    expected_title: str,
    expected_description: str,
) -> PublicationProof:
    """Build a proof only from independently confirmed uploader fields."""
    confirmed_channel = canonical_channel(str(response.get("channel") or ""))
    expected = canonical_channel(expected_channel)
    if confirmed_channel != expected:
        raise ProviderValidationError("La cuenta de YouTube confirmó otro canal")
    if not response.get("verified"):
        raise ProviderValidationError("La publicación no fue verificada independientemente")
    if response.get("title") != expected_title:
        raise ProviderValidationError("YouTube confirmó un título distinto")
    if response.get("description") != expected_description:
        raise ProviderValidationError("YouTube confirmó una descripción distinta")
    proof = PublicationProof(
        video_id=str(response.get("video_id") or ""),
        channel=confirmed_channel,
        visibility=str(response.get("visibility") or ""),
        title=expected_title,
        description=expected_description,
        thumbnail_confirmed=bool(response.get("thumbnail_confirmed")),
    )
    proof.validate()
    supplied_url = str(response.get("url") or "").strip()
    if supplied_url and supplied_url != proof.url:
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(supplied_url)
        extracted_id = parse_qs(parsed.query).get("v", [""])[0]
        if not extracted_id and "youtu.be" in (parsed.netloc or ""):
            extracted_id = parsed.path.strip("/").split("/")[0]
        if not extracted_id and "/shorts/" in (parsed.path or ""):
            extracted_id = parsed.path.split("/shorts/")[-1].split("/")[0].split("?")[0]
        if extracted_id != proof.video_id:
            raise ProviderValidationError("La URL devuelta no deriva del video_id")
    return proof


def backoff_with_jitter(
    attempt: int,
    *,
    base_seconds: float = 30.0,
    cap_seconds: float = 3_600.0,
    rng: random.Random | None = None,
) -> float:
    if attempt < 1:
        raise ValueError("attempt debe ser >= 1")
    source = rng or random.SystemRandom()
    ceiling = min(cap_seconds, base_seconds * (2 ** (attempt - 1)))
    return source.uniform(ceiling * 0.5, ceiling)
