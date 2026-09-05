"""Automated security policy and anti-hardcoding enforcement tests."""

import os
import re
import subprocess
from pathlib import Path

from src.config import BASE_DIR, MOKU, AELITHIA, SETTINGS

_AGENT_HOME_GITIGNORE = (
    ".codex/",
    ".claude/",
    ".gemini/",
    ".agents/",
    ".opencode/",
)

_AGENT_HOME_PREFIXES = (
    ".codex/",
    ".claude/",
    ".gemini/",
    ".agents/",
    ".opencode/",
    ".grok/",
    ".copilot/",
    ".cursor/",
    ".atl/",
)

# Format signatures only. Never embed live credential literals in tests or fixtures.
_PRODUCTION_SECRET_PATTERNS = [
    re.compile(r"AIzaSy[a-zA-Z0-9_-]{33}"),  # Google API key
    re.compile(r"GOCSPX-[a-zA-Z0-9_-]{28}"),  # Google OAuth client secret
    re.compile(r"(?<![0-9])\d{12}-[a-z0-9]{32}(?![a-z0-9.])"),  # Google OAuth client ID
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),  # OpenAI / generic API key
    re.compile(r"\d{8,10}:[A-Za-z0-9_-]{35}"),  # Telegram bot token
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),  # GitHub personal access token
]

_SCAN_ROOTS = ("src", "tests", "dev", "scripts")


def test_public_dict_does_not_leak_credential_paths():
    """Verify that public_dict() never exposes absolute or relative paths to secrets."""
    for channel in (MOKU, AELITHIA):
        pdict = channel.public_dict()
        assert "cookies_path" not in pdict, f"cookies_path leaked in {channel.key}"
        assert "youtube_token_path" not in pdict, f"youtube_token_path leaked in {channel.key}"
        assert "cookies_available" in pdict
        assert "youtube_token_available" in pdict
        assert isinstance(pdict["cookies_available"], bool)
        assert isinstance(pdict["youtube_token_available"], bool)


def test_env_example_contains_no_real_secrets():
    """Ensure .env.example contains only template placeholders and no live credentials."""
    env_example = BASE_DIR / ".env.example"
    assert env_example.is_file(), ".env.example must exist and be committed"

    content = env_example.read_text(encoding="utf-8")

    for pat in _PRODUCTION_SECRET_PATTERNS:
        assert pat.search(content) is None, (
            "Real secret pattern detected in .env.example"
        )

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if ("SECRET" in key or "KEY" in key or "TOKEN" in key or "PASSWORD" in key) and not (key.endswith("_PATH") or key.endswith("_FILE")):
                assert val == "", f"Secret variable {key} in .env.example must be empty, found: {val}"


def test_gitignore_enforces_secret_rules():
    """Verify that .gitignore blocks .env, secrets/, and credential artifacts."""
    gitignore = BASE_DIR / ".gitignore"
    assert gitignore.is_file()

    content = gitignore.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines()]

    assert ".env" in lines
    assert "secrets/" in lines
    assert "!.env.example" in lines
    assert "*.token" in lines or "*.key" in lines
    assert "*token*.json" in lines
    assert "*client_secret*.json" in lines
    for home in _AGENT_HOME_GITIGNORE:
        assert home in lines, f"{home} must be gitignored"
    assert "!.codex/hooks.json" not in lines


def test_no_live_secrets_in_tracked_python_files():
    """Verify tracked Python files do not embed production-format credentials."""
    scanned = 0
    for folder in _SCAN_ROOTS:
        root = BASE_DIR / folder
        if not root.is_dir():
            continue
        for py_file in root.rglob("*.py"):
            text = py_file.read_text(encoding="utf-8")
            scanned += 1
            for pat in _PRODUCTION_SECRET_PATTERNS:
                assert pat.search(text) is None, (
                    f"Hardcoded credential pattern found in {py_file.relative_to(BASE_DIR)}"
                )
    assert scanned > 0, "Expected to scan at least one Python file"


def test_no_agent_homedirs_tracked():
    """Agent homedirs and hooks must not be present in git ls-files."""
    tracked = subprocess.check_output(
        ["git", "ls-files"],
        cwd=BASE_DIR,
        text=True,
    ).splitlines()
    leaked = [
        path
        for path in tracked
        if path.startswith(_AGENT_HOME_PREFIXES) or path in {p.rstrip("/") for p in _AGENT_HOME_PREFIXES}
    ]
    assert leaked == [], f"Agent homedir files are tracked: {leaked}"
