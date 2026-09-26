"""Global offline guard for every non-live test."""

from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path

import pytest


_CATALOG_MEDIA_MODULES = {
    "test_challenger_m1_empirical",
    "test_challenger_m1_2",
    "test_loops_bank",
}

_STRESS_MODULES = {
    "test_m2_challenger_stress",
}

_DOMAIN_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("mcp", ("mcp",)),
    ("audio", ("audio", "voice", "synth", "tts")),
    ("media", (
        "video", "visual", "loop", "scene", "thumbnail", "thumb", "subtitle",
        "subtitles", "svg", "analog", "compositor", "ken_burns", "ctr", "image",
        "m2_challenger", "procedural_math", "ffmpeg", "compose_streamed", "xfade",
        "h264", "font_vendoring", "camera_path", "media_integrity", "scenic",
        "luminance", "title_card", "catalog_asset", "challenger_m1", "challenger_m2",
    )),
    ("narrative", (
        "narrative", "script", "curator", "story", "beats", "adaptation", "archetype",
        "agent", "llm", "seo", "topic", "shot_mix", "niche", "outro", "sanitizer",
        "scraper", "ai_first", "editorial", "narration_hooks", "cadence", "lore",
        "template", "remediation_edge_cases", "director",
    )),
    ("review", ("telegram", "review", "auto_approve", "auto_publish", "publication")),
    ("observability", ("observability", "ops", "profiling", "retention", "scoring", "analytics", "quality_audit", "healthcheck")),
    ("pipeline", (
        "pipeline", "daemon", "cli", "process", "watchdog", "resource", "runonce",
        "docker", "antigravity", "lifecycle", "youtube_control", "youtube_uploader",
        "ingest_quality", "stage9_mock",
    )),
    ("core", (
        "core", "channel", "channels", "db", "multichannel", "queue", "repository",
        "lane", "lanes", "migration", "purge", "cookies", "cookie", "drive",
        "google_auth", "checkpoints", "cleaner", "resilience", "resolution", "errors",
        "architectural", "api_health", "branding", "audit_remediation", "harness_m1",
        "runtime_profiles", "v3_1_architecture", "anti_regression", "security",
        "docs_integrity", "live_rss", "d2_timing",
    )),
]


def pytest_collection_modifyitems(config, items):
    """Keep explicitly live scenarios out of normal local suite and assign domain & lifecycle tags."""
    run_live = os.environ.get("RUN_LIVE_TESTS") == "1"
    skip_live = pytest.mark.skip(
        reason="Prueba live: requiere habilitación consciente con RUN_LIVE_TESTS=1"
    )

    for item in items:
        mod_name = Path(item.fspath).stem.lower()

        # Empirical catalog loops requiring uncommitted local production assets
        if any(target in mod_name for target in _CATALOG_MEDIA_MODULES):
            item.add_marker(pytest.mark.catalog_media)

        # Stress tests with high computational/memory soak
        if any(target in mod_name for target in _STRESS_MODULES):
            item.add_marker(pytest.mark.stress)

        # Domain marker classification
        for domain, keywords in _DOMAIN_RULES:
            if any(kw in mod_name for kw in keywords):
                item.add_marker(getattr(pytest.mark, domain))
                break

        if not run_live and item.get_closest_marker("live"):
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
    monkeypatch.setenv("USE_AGENT_HARNESS", "0")
    test_review_db = str(Path(request.config.rootdir) / ".pytest_cache" / f"test_review_{os.getpid()}.db")
    monkeypatch.setenv("VIDEO_REVIEW_DB_PATH", test_review_db)
    test_agents_dir = str(Path(request.config.rootdir) / ".pytest_cache" / f"test_agents_{os.getpid()}")
    monkeypatch.setenv("ANTIGRAVITY_AGENTS_APP_DATA_DIR", test_agents_dir)
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

    class guarded_popen(original_popen):
        def __init__(self, *args, **kwargs):
            command = args[0] if args else kwargs.get("args")
            if _blocked_command(command):
                raise RuntimeError("AGY y systemd están bloqueados en pruebas")
            super().__init__(*args, **kwargs)

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
    try:
        import shutil
        for item in Path(session.config.rootdir).glob(".bot_home*"):
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
        output_dir = Path(session.config.rootdir) / "output"
        if output_dir.is_dir():
            for item in output_dir.glob("*.json"):
                item.unlink(missing_ok=True)
    except Exception:
        pass
