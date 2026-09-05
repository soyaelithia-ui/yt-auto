"""WP1 — Runtime profile isolation tests (prod vs cli vs test)."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _fresh_is_test_environment(profile: str) -> str:
    """Ask a child interpreter (no pytest in sys.modules) whether the profile is test."""
    env = os.environ.copy()
    env["YT_PROFILE"] = profile
    env.pop("TEST_MODE", None)
    env.pop("PYTEST_CURRENT_TEST", None)
    env["PYTHONPATH"] = str(_REPO_ROOT)
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "from src.config import is_test_environment; print(int(is_test_environment()))",
        ],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr or proc.stdout)
    return proc.stdout.strip()


def _reload_config(
    monkeypatch: pytest.MonkeyPatch,
    yt_profile: str | None,
    extra_env: dict | None = None,
):
    """Reload src.config under a controlled environment.

    ``src.config`` loads the deployment ``.env`` at import time via
    ``load_dotenv``; we neutralize it so each profile resolves only from the
    test's environment. ``monkeypatch`` restores both the patch and the env
    automatically after each test (no global state).
    """
    monkeypatch.setenv("TEST_MODE", "0")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False, raising=False)
    for var in ("YOUTUBE_AUTOMATION_DB", "VIDEO_REVIEW_DB_PATH", "WORK_ROOT", "ARTIFACT_ROOT"):
        monkeypatch.delenv(var, raising=False)
    for key, value in (extra_env or {}).items():
        monkeypatch.setenv(key, value)
    if yt_profile is None:
        monkeypatch.delenv("YT_PROFILE", raising=False)
    else:
        monkeypatch.setenv("YT_PROFILE", yt_profile)
    import src.config as config

    return importlib.reload(config)


def test_default_manual_invocation_is_cli_sandbox(monkeypatch):
    # Simula invocación manual real: YT_PROFILE=cli explícito (bajo pytest el
    # auto-detect elegiría 'test', que es el comportamiento deseado).
    cfg = _reload_config(monkeypatch, "cli")
    try:
        assert cfg.RUNTIME_PROFILE == "cli"
        assert str(cfg.SETTINGS.database_path).endswith("data/cli/shorts_queue.db")
    finally:
        importlib.reload(cfg)


def test_prod_profile_keeps_canonical_roots(monkeypatch):
    cfg = _reload_config(monkeypatch, "prod")
    try:
        assert cfg.RUNTIME_PROFILE == "prod"
        root = cfg.PROFILE_DATA_ROOT
        assert root.name == "data"  # legacy canonical location, no subdir
        assert str(cfg.PROFILE_WORK_ROOT).endswith("work")
    finally:
        importlib.reload(cfg)


def test_explicit_env_override_wins_over_profile(monkeypatch):
    # dotenv neutralizado: el override explícito del test es la única fuente
    cfg = _reload_config(
        monkeypatch, "cli", {"YOUTUBE_AUTOMATION_DB": "/tmp/wp1_custom_queue.db"}
    )
    try:
        assert str(cfg.SETTINGS.database_path) == "/tmp/wp1_custom_queue.db"
    finally:
        importlib.reload(cfg)


def test_review_db_default_follows_profile(monkeypatch):
    monkeypatch.delenv("VIDEO_REVIEW_DB_PATH", raising=False)
    cfg = _reload_config(monkeypatch, "cli")
    try:
        assert str(cfg.default_review_db_path()).endswith("data/cli/review_state.db")
    finally:
        importlib.reload(cfg)


def test_yt_profile_test_is_test_environment_outside_pytest():
    """`main.py -p test` must skip the live agy chain (generate-only hang)."""
    assert _fresh_is_test_environment("test") == "1"


def test_yt_profile_cli_is_not_test_environment_outside_pytest():
    assert _fresh_is_test_environment("cli") == "0"
