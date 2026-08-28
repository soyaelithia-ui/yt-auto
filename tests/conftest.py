"""Global offline guard for every non-live test."""

from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path

import pytest


def pytest_collection_modifyitems(config, items):
    """Keep explicitly live scenarios out of the normal local suite."""
    if os.environ.get("RUN_LIVE_TESTS") == "1":
        return
    skip_live = pytest.mark.skip(
        reason="Prueba live: requiere habilitación consciente con RUN_LIVE_TESTS=1"
    )
    for item in items:
        if item.get_closest_marker("live"):
            item.add_marker(skip_live)


@pytest.fixture(autouse=True)
def offline_provider_guard(monkeypatch, request):
    """Fail closed: a cache miss can never invoke a real provider."""
    if request.node.get_closest_marker("live"):
        yield
        return

    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("MOCK_DRIVE_UPLOAD", "1")
    monkeypatch.setenv("MOCK_YOUTUBE_UPLOAD", "1")
    test_review_db = str(Path(request.config.rootdir) / ".pytest_cache" / f"test_review_{os.getpid()}.db")
    monkeypatch.setenv("VIDEO_REVIEW_DB_PATH", test_review_db)
    original_run = subprocess.run
    original_popen = subprocess.Popen
    original_connect = socket.socket.connect

    def _blocked_command(command) -> bool:
        if not isinstance(command, (list, tuple)) or not command:
            return False
        return Path(str(command[0])).name in {"agy", "systemctl"}

    def guarded_run(*args, **kwargs):
        command = args[0] if args else kwargs.get("args")
        if _blocked_command(command):
            raise RuntimeError("AGY y systemd están bloqueados en pruebas")
        return original_run(*args, **kwargs)

    def guarded_popen(*args, **kwargs):
        command = args[0] if args else kwargs.get("args")
        if _blocked_command(command):
            raise RuntimeError("AGY y systemd están bloqueados en pruebas")
        return original_popen(*args, **kwargs)

    def guarded_connect(sock, address):
        host = str(address[0]) if isinstance(address, tuple) and address else ""
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise RuntimeError("La red externa está bloqueada en pruebas")
        return original_connect(sock, address)

    import time
    monkeypatch.setattr(subprocess, "run", guarded_run)
    monkeypatch.setattr(subprocess, "Popen", guarded_popen)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(time, "sleep", lambda secs: None)
    yield


def pytest_sessionfinish(session, exitstatus):
    """Teardown hook: automatically clean test artifacts under work/test."""
    try:
        from src.cleaner import clean_test_artifacts
        clean_test_artifacts(min_age_seconds=0, dry_run=False)
    except Exception:
        pass
