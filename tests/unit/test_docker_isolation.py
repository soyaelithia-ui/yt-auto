"""Contracts for a self-contained, non-root Docker runtime (no host agy / ~/.gemini)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _compose() -> str:
    return (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def _dockerfile() -> str:
    return (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_compose_does_not_bind_host_agy_binary():
    compose = _compose()
    assert "AGY_BINARY_PATH" not in compose
    assert "/run/agy/agy" not in compose
    assert "/usr/local/bin/agy:" not in compose
    assert "${AGY_BINARY_PATH" not in compose


def test_compose_agy_bin_is_inside_the_image():
    compose = _compose()
    assert "AGY_BIN: /usr/local/bin/agy" in compose


def test_compose_does_not_bind_host_user_gemini():
    compose = _compose()
    assert "${HOME}/.gemini" not in compose
    assert "~/.gemini" not in compose
    assert "/root/.gemini" not in compose
    assert "./.bot_home/.gemini" not in compose
    assert "yt_agy_home:/home/appuser/.gemini" in compose


def test_compose_uses_named_volumes_not_host_workdir_binds():
    compose = _compose()
    for bind in (
        "./data:/app/data",
        "./work:/app/work",
        "./artifacts:/app/artifacts",
        "./logs:/app/logs",
        "./output:/app/output",
    ):
        assert bind not in compose
    assert "yt_data:/app/data" in compose
    assert "yt_work:/app/work" in compose
    assert "yt_artifacts:/app/artifacts" in compose
    assert "yt_logs:/app/logs" in compose
    assert "yt_output:/app/output" in compose
    assert "./secrets:/run/secrets:ro" in compose


def test_compose_does_not_override_image_user():
    compose = _compose()
    assert "YT_UID" not in compose
    assert "user: \"" not in compose
    assert "user: '" not in compose


def test_compose_keeps_hardening_flags():
    compose = _compose()
    assert "read_only: true" in compose
    assert "cap_drop:" in compose
    assert "no-new-privileges:true" in compose
    assert "127.0.0.1:8081:8081" in compose


def test_dockerfile_installs_agy_and_drops_root():
    docker = _dockerfile()
    assert "COPY build/agy /usr/local/bin/agy" in docker
    assert "USER 10001:10001" in docker
    assert "AGY_BIN=/usr/local/bin/agy" in docker
    assert "scripts/docker_entrypoint.sh" in docker


def test_gitignore_excludes_staged_agy_elf():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/build/" in gitignore or "build/agy" in gitignore


def test_dockerignore_keeps_secrets_and_host_gemini_out_of_image():
    ignore = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
    for pattern in ("secrets/", ".env", ".bot_home/", "data/", "work/"):
        assert pattern in ignore
    assert "build/agy" not in ignore.replace("!build/agy", "")


def test_stage_agy_script_exists_and_is_fail_closed():
    script = (REPO_ROOT / "scripts" / "stage_agy.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in script
    assert "build/agy" in script
    assert "exit 1" in script


def test_small_compose_override_caps_memory():
    small = (REPO_ROOT / "docker-compose.small.yml").read_text(encoding="utf-8")
    assert "mem_limit: 2g" in small
    assert "cpus: 2" in small
