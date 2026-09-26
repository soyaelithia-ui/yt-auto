"""Per-channel lock granularity for run-once batch mode (main --channel all).

Contract under test:
- No coarse '.lock.all' acquisition in batch mode (two scheduler lanes must
  not collide); each channel is probed individually.
- A channel whose per-channel lock is held by another process is SKIPPED with
  a warning; the remaining channels still run.
- If every channel is locked, the turn exits nonzero (mirrors the old
  single-lock failure semantics).
- Single-channel mode keeps the legacy acquire_lock/release_lock behavior.
"""

from __future__ import annotations

import builtins
import importlib
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


class _FakeChannelLock:
    """Stands in for src.core.lock.ChannelLock, recording acquisitions."""

    held_by_other: set[str] = set()
    acquisitions: list[str] = []

    def __init__(self, channel_name: str = "global", lock_file_path=None) -> None:
        self.channel_name = channel_name
        self.acquired = False

    def acquire(self) -> bool:
        _FakeChannelLock.acquisitions.append(self.channel_name)
        if self.channel_name in _FakeChannelLock.held_by_other:
            from src.core.lock import ChannelLockError as _Err

            raise _Err(f"locked: {self.channel_name}")
        self.acquired = True
        return True

    def release(self) -> None:
        self.acquired = False


@pytest.fixture()
def main_module(monkeypatch):
    """Import main with heavy side-effect modules stubbed out."""
    _FakeChannelLock.held_by_other = set()
    _FakeChannelLock.acquisitions = []

    stubs: dict[str, types.ModuleType] = {}

    def _stub(name: str, **attrs):
        mod = types.ModuleType(name)
        pkg_dir = REPO_ROOT / name.replace(".", "/")
        if pkg_dir.is_dir():
            mod.__path__ = [str(pkg_dir)]
        for key, value in attrs.items():
            setattr(mod, key, value)
        stubs[name] = mod
        monkeypatch.setitem(sys.modules, name, mod)
        return mod

    real_lock = importlib.import_module("src.core.lock")
    monkeypatch.setattr(real_lock, "ChannelLock", _FakeChannelLock)

    _stub(
        "src.api_health",
        check_all=lambda ch: {},
        format_status_report=lambda report, ch: "",
    )
    _stub("src.youtube.auth", exchange_code=lambda *a, **k: None, get_auth_url=lambda u: "")
    _stub(
        "src.branding",
        resolve_channel_key=lambda name: name,
    )
    _stub(
        "src.channel_manager",
        activate_channel=lambda name: {},
        get_active_channels=lambda: ["horror", "drama"],
    )
    _stub(
        "src.cleaner",
        clean_system_cache=lambda dry_run=False: {},
        clean_expired_failed_runs=lambda: 0,
        clean_untracked_temp_files=lambda: 0,
    )
    _stub("src.cli", print_queue=lambda **k: None, print_status=lambda **k: None)
    _stub(
        "src.daemon",
        request_shutdown=lambda: None,
        run_pipeline_once=lambda **k: {},
        _run_24h_maintenance_sweep=lambda *a, **k: None,
        start_daemon_lanes=lambda *a, **k: None,
    )
    _stub("src.monitor", run_publication_check=lambda: {})
    fake_orchestrator_mod = _stub("src.orchestrator")

    class _FakeOrchestrator:
        calls: list[dict] = []

        def __init__(self, db_path=None):
            self.db_path = db_path

        def run_channel(self, **kwargs):
            _FakeOrchestrator.calls.append(kwargs)
            return types.SimpleNamespace(status="SUCCESS", telegram_delivery=None, raw_result={})

        def run_all_channels(self, **kwargs):  # must NOT be used anymore
            raise AssertionError("run_all_channels no debe invocarse en el camino de locks por canal")

        def run_telegram_canary(self, **kwargs): ...

    fake_orchestrator_mod.PipelineOrchestrator = _FakeOrchestrator

    import src.config as real_config

    config_attrs = {k: getattr(real_config, k) for k in dir(real_config) if not k.startswith("__")}
    config_attrs.update(
        BASE_DIR=REPO_ROOT,
        DEFAULT_DB_PATH=str(REPO_ROOT / "data" / "test.db"),
        RUNTIME_PROFILE="test",
        LOCK_FILE_PATH=str(REPO_ROOT / "scratch" / "test.lock"),
        TOKEN_CHANNEL2_PATH="/tmp/t2.json",
        YOUTUBE_TOKEN_PATH="/tmp/t1.json",
        SETTINGS=types.SimpleNamespace(video_engine="loop", short_compositor="loop"),
        validate_runtime_config=lambda **k: None,
    )
    config_stub = _stub("src.config", **config_attrs)
    # main reads RUNTIME_PROFILE at call time via module attribute access on import
    monkeypatch.setattr(config_stub, "RUNTIME_PROFILE", "test", raising=False)

    telegram_pkg = _stub("src.telegram")
    telegram_pkg.check_pending_approvals = lambda: []
    _stub("src.observability")
    _stub(
        "src.log",
        setup_logging=lambda: None,
        get_logger=lambda name: logging.getLogger(name),
    )

    import logging  # noqa: F401  (used inside _stub above)

    if "main" in sys.modules:
        del sys.modules["main"]
    saved_argv = sys.argv
    sys.argv = ["main.py"]
    try:
        module = importlib.import_module("main")
    finally:
        sys.argv = saved_argv
    return module, _FakeChannelLock, _FakeOrchestrator


import logging  # noqa: E402


def _run(main_module, argv_tail):
    """Invoke main() with the given CLI tail; returns SystemExit or None."""
    argv = ["main.py"] + argv_tail
    saved = sys.argv
    sys.argv = argv
    try:
        try:
            main_module.main()
            return None
        except SystemExit as exc:
            return exc
    finally:
        sys.argv = saved


def test_batch_mode_takes_no_coarse_all_lock(main_module):
    mod, fake_lock, fake_orch = main_module
    exc = _run(mod, ["--run-once", "--channel", "all", "--db-path", "/tmp/x.db"])
    assert exc is None
    assert "all" not in fake_lock.acquisitions, fake_lock.acquisitions
    assert fake_lock.acquisitions.count("horror") >= 1
    assert fake_lock.acquisitions.count("drama") >= 1
    ran = [c["channel"] for c in fake_orch.calls]
    assert ran == ["horror", "drama"]


def test_batch_mode_skips_locked_channel_and_runs_rest(main_module, caplog):
    mod, fake_lock, fake_orch = main_module
    _FakeChannelLock.held_by_other.add("horror")
    with caplog.at_level(logging.WARNING, logger="main"):
        exc = _run(mod, ["--run-once", "--channel", "all", "--db-path", "/tmp/x.db"])
    assert exc is None  # at least one channel ran -> exit 0
    ran = [c["channel"] for c in fake_orch.calls]
    assert ran == ["drama"]
    assert any("horror" in r.message and "omitido" in r.message for r in caplog.records)


def test_batch_mode_all_locked_exits_nonzero(main_module, capsys):
    mod, fake_lock, _fake_orch = main_module
    _FakeChannelLock.held_by_other.update({"horror", "drama"})
    exc = _run(mod, ["--run-once", "--channel", "all", "--db-path", "/tmp/x.db"])
    assert isinstance(exc, SystemExit) and exc.code == 1
    out = capsys.readouterr().out
    assert "Ningún canal disponible" in out


def test_single_channel_keeps_legacy_lock(main_module, monkeypatch):
    mod, fake_lock, fake_orch = main_module

    acquired: list[str] = []
    released: list[str] = []

    def fake_acquire(channel_name="global"):
        acquired.append(channel_name)

    def fake_release(channel_name=None):
        released.append(channel_name)

    monkeypatch.setattr(mod, "acquire_lock", fake_acquire)
    monkeypatch.setattr(mod, "release_lock", fake_release)

    exc = _run(mod, ["--run-once", "--channel", "horror", "--db-path", "/tmp/x.db"])
    assert exc is None
    assert acquired == ["horror"]
    assert released == ["horror"]
    assert [c["channel"] for c in fake_orch.calls] == ["horror"]
