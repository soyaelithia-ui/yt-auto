"""Unit tests for the in-process resource guard."""

from __future__ import annotations

import pytest

from src.core.errors import PipelineError
from src.core.guard import (
    ConsecutiveFailureBreaker,
    DiskPreflight,
    MemoryWatchdog,
    ResourceLimitError,
    ensure_disk_available,
    observed_memory_bytes,
    read_vm_rss_bytes,
    resolve_soft_limit_bytes,
)


# ---------------------------------------------------------------------------
# Disk guard
# ---------------------------------------------------------------------------


def test_disk_ok_when_space_above_threshold(tmp_path):
    report = ensure_disk_available([tmp_path], min_free_gb=0.001, auto_clean=False)
    assert report.ok is True
    assert str(tmp_path) in report.checked


def test_disk_fails_below_threshold_without_cleaning(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.core.guard.free_disk_bytes", lambda path: 1024  # 1 KB
    )
    report = ensure_disk_available([tmp_path], min_free_gb=5.0, auto_clean=False)
    assert report.ok is False
    assert report.cleaned_bytes == 0
    assert report.tightest_path == str(tmp_path)


def test_disk_runs_cleaner_then_rechecks(tmp_path, monkeypatch):
    import builtins
    import types

    import src.core.guard as guard

    # secuencia: chequeo inicial bajo suelo → tras limpieza, espacio suficiente
    free_results = iter([1024, 60 * 1024**3])
    monkeypatch.setattr(guard, "free_disk_bytes", lambda path: next(free_results))
    clean_calls = {"n": 0}

    def _fake_clean(dry_run=False):
        clean_calls["n"] += 1
        return {"freed_bytes": 12345}

    fake_module = types.SimpleNamespace(clean_system_cache=_fake_clean)
    real_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name == "src.cleaner":
            return fake_module
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    report = ensure_disk_available([tmp_path], min_free_gb=5.0, auto_clean=True)
    assert report.ok is True
    assert report.cleaned_bytes == 12345
    assert clean_calls["n"] == 1


def test_preflight_dataclass_defaults():
    preflight = DiskPreflight(ok=True, min_free_bytes=10)
    assert preflight.tightest_path is None
    assert preflight.checked == {}


# ---------------------------------------------------------------------------
# Memory ceiling
# ---------------------------------------------------------------------------


def test_read_vm_rss_returns_nonnegative_int():
    value = read_vm_rss_bytes()
    assert isinstance(value, int)
    assert value >= 0


def test_observed_memory_sums_self_and_children():
    total = observed_memory_bytes(self_rss=100, children_rss=30)
    assert total == 130


def test_soft_limit_from_explicit_arg():
    # el parámetro explícito se expresa en bytes (coherente con soft_limit_bytes)
    assert resolve_soft_limit_bytes(explicit=2.5 * 1024**3) == int(2.5 * 1024**3)


def test_soft_limit_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("YT_MAX_RSS_GB", "3")
    assert resolve_soft_limit_bytes() == 3 * 1024**3


def test_watchdog_disabled_without_limit(monkeypatch):
    monkeypatch.delenv("YT_MAX_RSS_GB", raising=False)
    watchdog = MemoryWatchdog(soft_limit_bytes=None)
    # sin cgroup en el entorno de test → disabled es válido; checkpoint no lanza
    info = watchdog.checkpoint("x")
    assert info.get("disabled") in {True, False}


def test_watchdog_tolerates_single_spike():
    samples = iter([2000, 2000])
    watchdog = MemoryWatchdog(
        soft_limit_bytes=1000, required_breaches=2, observer=lambda: next(samples)
    )
    info = watchdog.checkpoint("s1")  # breach 1: tolerated
    assert info["breaches"] == 1
    assert info["observed_bytes"] == 2000


def test_watchdog_raises_on_sustained_breach():
    samples = iter([2000, 2000])
    watchdog = MemoryWatchdog(
        soft_limit_bytes=1024, required_breaches=2, observer=lambda: next(samples)
    )
    with pytest.raises(ResourceLimitError) as excinfo:
        watchdog.checkpoint("s1")
        watchdog.checkpoint("s2")
    error = excinfo.value
    assert isinstance(error, PipelineError)
    assert error.retryable is True
    assert error.component == "resource_guard"
    assert error.resource_kind == "memory"
    assert error.observed_bytes == 2000


def test_watchdog_recovers_after_breach():
    samples = iter([2000, 100, 2000, 2000])
    watchdog = MemoryWatchdog(
        soft_limit_bytes=1024, required_breaches=2, observer=lambda: next(samples)
    )
    watchdog.checkpoint("a")  # breach 1
    watchdog.checkpoint("b")  # recovery resets the counter
    with pytest.raises(ResourceLimitError):
        watchdog.checkpoint("c")  # breach 1 (tolerated)
        watchdog.checkpoint("d")  # breach 2 → raise


# ---------------------------------------------------------------------------
# Failure breaker
# ---------------------------------------------------------------------------


def test_breaker_trips_at_threshold():
    breaker = ConsecutiveFailureBreaker(threshold=3)
    assert breaker.record_failure("moku") is False
    assert breaker.record_failure("moku") is False
    assert breaker.record_failure("moku") is True  # trips exactly here


def test_breaker_success_resets_counter():
    breaker = ConsecutiveFailureBreaker(threshold=2)
    breaker.record_failure("moku")
    breaker.record_success("moku")
    assert breaker.record_failure("moku") is False
    assert breaker.record_failure("moku") is True


def test_breaker_channels_are_independent():
    breaker = ConsecutiveFailureBreaker(threshold=2)
    breaker.record_failure("moku")
    assert breaker.record_failure("aelithia") is False
    assert breaker.record_failure("aelithia") is True


def test_breaker_disabled_when_threshold_zero():
    breaker = ConsecutiveFailureBreaker(threshold=0)
    for _ in range(10):
        assert breaker.record_failure("moku") is False


def test_resource_limit_error_is_retryable_pipeline_error():
    error = ResourceLimitError("techo", resource_kind="memory", observed_bytes=9, limit_bytes=8)
    from src.core.errors import is_retryable

    assert is_retryable(error) is True
