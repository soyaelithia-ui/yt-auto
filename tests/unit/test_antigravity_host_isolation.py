"""Guarantees the agent harness never contaminates host Antigravity CLI state."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.agents.base_agent import (
    AgyStreamClient,
    _resolve_default_app_data_dir,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
HOST_GEMINI_PATH_RE = re.compile(r"/home/[^/\s\"']+/\.gemini/antigravity-cli")


def _seed_host_cli(tmp_path: Path) -> tuple[Path, Path]:
    fake_home = tmp_path / "host_home"
    host_cli = fake_home / ".gemini" / "antigravity-cli"
    host_cli.mkdir(parents=True)
    (host_cli / "antigravity-oauth-token").write_text("HOST_SECRET_TOKEN", encoding="utf-8")
    (host_cli / "settings.json").write_text("{}", encoding="utf-8")
    (host_cli / "bin").mkdir()
    (host_cli / "builtin").mkdir()
    return fake_home, host_cli


def test_prepare_env_does_not_symlink_or_read_host_antigravity(tmp_path, monkeypatch):
    fake_home, host_cli = _seed_host_cli(tmp_path)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("ANTIGRAVITY_APP_DATA_DIR", str(host_cli))
    monkeypatch.setenv("ANTIGRAVITY_CLI_HOME", str(fake_home / ".gemini"))
    monkeypatch.setenv("ANTIGRAVITY_AGENTS_APP_DATA_DIR", str(host_cli))

    bot_home = tmp_path / "bot_home"
    monkeypatch.setenv("BOT_HOME", str(bot_home))
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path / "empty_secrets"))
    isolated = bot_home / ".gemini" / "antigravity-cli"

    env = AgyStreamClient(app_data_dir=isolated)._prepare_env()

    assert (host_cli / "antigravity-oauth-token").read_text(encoding="utf-8") == "HOST_SECRET_TOKEN"
    assert list(isolated.glob("*")) == [] or all(not p.is_symlink() for p in isolated.rglob("*"))
    for name in ("antigravity-oauth-token", "settings.json", "bin", "builtin"):
        dst = isolated / name
        assert not dst.exists()
    assert env["HOME"] == str(bot_home)
    assert env["ANTIGRAVITY_APP_DATA_DIR"] == str(isolated)
    assert env["AGY_APP_DATA_DIR"] == str(isolated)
    assert str(host_cli) not in env.get("ANTIGRAVITY_APP_DATA_DIR", "")
    assert str(host_cli) not in env.get("ANTIGRAVITY_CLI_HOME", "")
    assert str(fake_home / ".gemini") not in env.get("ANTIGRAVITY_CLI_HOME", "")


def test_prepare_env_copies_token_from_secrets_not_host_home(tmp_path, monkeypatch):
    fake_home, host_cli = _seed_host_cli(tmp_path)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("ANTIGRAVITY_APP_DATA_DIR", str(host_cli))

    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "antigravity-oauth-token").write_text("PIPELINE_TOKEN", encoding="utf-8")
    monkeypatch.setenv("SECRETS_DIR", str(secrets))

    bot_home = tmp_path / "bot_home"
    isolated = bot_home / ".gemini" / "antigravity-cli"
    env = AgyStreamClient(app_data_dir=isolated)._prepare_env()

    token = isolated / "antigravity-oauth-token"
    assert token.is_file()
    assert not token.is_symlink()
    assert token.read_text(encoding="utf-8") == "PIPELINE_TOKEN"
    assert (host_cli / "antigravity-oauth-token").read_text(encoding="utf-8") == "HOST_SECRET_TOKEN"
    assert env["ANTIGRAVITY_APP_DATA_DIR"] == str(isolated)


def test_resolve_app_data_dir_rejects_host_interactive_cli(tmp_path, monkeypatch):
    fake_home, host_cli = _seed_host_cli(tmp_path)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("ANTIGRAVITY_AGENTS_APP_DATA_DIR", str(host_cli))
    monkeypatch.setenv("ANTIGRAVITY_APP_DATA_DIR", str(host_cli))
    monkeypatch.delenv("BOT_HOME", raising=False)

    resolved = _resolve_default_app_data_dir()
    assert resolved != host_cli.resolve()
    assert ".bot_home" in str(resolved)
    assert str(fake_home / ".gemini") not in str(resolved)


@patch("subprocess.run")
def test_send_task_env_never_points_at_host_gemini(mock_run, tmp_path, monkeypatch):
    fake_home, host_cli = _seed_host_cli(tmp_path)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("ANTIGRAVITY_CLI_HOME", str(fake_home / ".gemini"))

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(
        {"status": "SUCCESS", "response": "ok", "conversation_id": "iso_1"}
    )
    mock_run.return_value = mock_proc

    isolated = tmp_path / "bot_home" / ".gemini" / "antigravity-cli"
    client = AgyStreamClient(app_data_dir=isolated)
    client.send_task("ping")

    env = mock_run.call_args.kwargs["env"]
    for key in ("HOME", "ANTIGRAVITY_APP_DATA_DIR", "AGY_APP_DATA_DIR", "ANTIGRAVITY_CLI_HOME"):
        assert str(host_cli) not in str(env.get(key, ""))
        assert str(fake_home / ".gemini") != str(env.get(key, ""))
    assert not any(p.is_symlink() for p in isolated.rglob("*"))


def test_src_has_no_hardcoded_host_antigravity_paths():
    offenders = []
    for py in (REPO_ROOT / "src").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if HOST_GEMINI_PATH_RE.search(text):
            offenders.append(str(py.relative_to(REPO_ROOT)))
    assert offenders == []
