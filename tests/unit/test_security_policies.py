"""Automated security policy and anti-hardcoding enforcement tests."""

import os
import re
from pathlib import Path

from src.config import BASE_DIR, MOKU, AELITHIA, SETTINGS


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
    
    # Check for forbidden secret patterns in .env.example
    forbidden_patterns = [
        r"AIzaSy[a-zA-Z0-9_-]{33}",      # Google API key
        r"GOCSPX-[a-zA-Z0-9_-]{28}",     # Google OAuth client secret
        r"sk-[a-zA-Z0-9]{20,}",          # OpenAI / generic API key
        r"\d{8,10}:[A-Za-z0-9_-]{35}",   # Telegram bot token
        r"ghp_[a-zA-Z0-9]{36}",          # GitHub personal access token
    ]
    for pattern in forbidden_patterns:
        match = re.search(pattern, content)
        assert match is None, f"Real secret pattern detected in .env.example: {match.group(0) if match else ''}"

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


def test_no_live_secrets_in_tracked_python_files():
    """Verify that no live Google/OAuth secrets are hardcoded in tracked Python files."""
    real_secret_patterns = [
        re.compile(r'AIzaSyDLdzaSALYSHGxj2KRlYf5CFCWPlN9iu1I'),
        re.compile(r'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'),
        re.compile(r'186861552313-639lqvbh06ettc8vbm4etgsrauejgimp'),
    ]

    for py_file in (BASE_DIR / "src").rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for pat in real_secret_patterns:
            assert not pat.search(text), f"Hardcoded credential pattern found in {py_file.relative_to(BASE_DIR)}"
