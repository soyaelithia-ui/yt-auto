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
    ".cursor/",
    ".hermes/",
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
    ".hermes/",
)

# Format signatures only. Never embed live credential literals in tests or fixtures.
_PRODUCTION_SECRET_PATTERNS = [
    re.compile(r"AIzaSy[a-zA-Z0-9_-]{33}"),  # Google API key
    re.compile(r"GOCSPX-[a-zA-Z0-9_-]{28}"),  # Google OAuth client secret
    re.compile(r"(?<![0-9])\d{12}-[a-z0-9]{32}(?![a-z0-9.])"),  # Google OAuth client ID
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),  # OpenAI / generic API key
    re.compile(r"\d{8,10}:[A-Za-z0-9_-]{35}"),  # Telegram bot token
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),  # GitHub personal access token
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),  # PEM private key
    re.compile(r"ya29\.[A-Za-z0-9_-]{50,}"),  # long Google access token
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
]

_PEM_PATTERN = _PRODUCTION_SECRET_PATTERNS[6]
_YA29_PATTERN = _PRODUCTION_SECRET_PATTERNS[7]
_AKIA_PATTERN = _PRODUCTION_SECRET_PATTERNS[8]
_SA_TYPE_PATTERN = re.compile(r'"type"\s*:\s*"service_account"')
_SA_KEY_PATTERN = re.compile(r'"private_key"')

_SCAN_ROOTS = ("src", "tests", "dev", "scripts")
_NON_PYTHON_SUFFIXES = (".md", ".json", ".sh", ".yml", ".yaml", ".txt", ".toml")
_SA_SCAN_SKIP_PREFIXES = ("openspec/",)
_SA_SCAN_SKIP_FILES = {
    "tests/unit/test_security_policies.py",
    "dev/audit_security.py",
}
_HYGIENE_DOCS = (
    "SECURITY.md",
    "AGENTS.md",
    "docs/CONFIGURACION_SECRETOS.md",
)
_DEFAULT_APPLY_SCAN_ROOTS = ("scripts", "dev", ".githooks", ".github")
_HOOK_PATH = BASE_DIR / ".githooks" / "pre-commit"
_AUDIT_PATH = BASE_DIR / "dev" / "audit_security.py"
_GITIGNORE_PATH = BASE_DIR / ".gitignore"


def _gitignore_lines() -> list[str]:
    assert _GITIGNORE_PATH.is_file()
    return [line.strip() for line in _GITIGNORE_PATH.read_text(encoding="utf-8").splitlines()]


def _hook_text() -> str:
    assert _HOOK_PATH.is_file()
    return _HOOK_PATH.read_text(encoding="utf-8")


def _audit_text() -> str:
    assert _AUDIT_PATH.is_file()
    return _AUDIT_PATH.read_text(encoding="utf-8")


def _assert_no_live_format(rel_path: str, text: str) -> None:
    for pat in _PRODUCTION_SECRET_PATTERNS:
        assert pat.search(text) is None, (
            f"Hardcoded credential pattern found in {rel_path}"
        )
    if rel_path in _SA_SCAN_SKIP_FILES or rel_path.startswith(_SA_SCAN_SKIP_PREFIXES):
        return
    if _SA_TYPE_PATTERN.search(text) and _SA_KEY_PATTERN.search(text):
        raise AssertionError(f"Hardcoded credential pattern found in {rel_path}")


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
    """Ensure .env.example has empty secret keys; non-secret defaults/path placeholders OK."""
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
            secretish = ("SECRET" in key or "KEY" in key or "TOKEN" in key or "PASSWORD" in key)
            path_placeholder = key.endswith(("_PATH", "_FILE", "_DIR"))
            if secretish and not path_placeholder:
                assert val == "", f"Secret variable {key} in .env.example must be empty, found: {val}"


def test_gitignore_enforces_secret_rules():
    """Verify that .gitignore blocks .env, secrets/, and credential artifacts."""
    lines = _gitignore_lines()

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
            _assert_no_live_format(str(py_file.relative_to(BASE_DIR)), text)
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


def test_gitignore_ignores_cookie_txt_class():
    """Cookie-txt class must be gitignored outside secrets/."""
    lines = _gitignore_lines()
    assert "cookies.txt" in lines
    assert "*cookies*.txt" in lines


def test_gitignore_ignores_drive_key_json():
    """drive_key.json must be gitignored outside secrets/."""
    lines = _gitignore_lines()
    assert "drive_key.json" in lines


def test_precommit_has_filename_regexes_extras_and_cached():
    """Pre-commit must reject secret filenames and extra signatures on the index."""
    hook = _hook_text()
    assert "--cached" in hook
    assert ".env.example" in hook
    assert re.search(r"cookies\\.json", hook)
    assert re.search(r"secrets/", hook)
    assert "-----BEGIN [A-Z ]*PRIVATE KEY-----" in hook
    assert "ya29\\.[A-Za-z0-9_-]{50,}" in hook
    assert "AKIA[0-9A-Z]{16}" in hook
    assert "service_account" in hook
    assert '"private_key"' in hook


def test_precommit_blocks_hermes_without_printing_matches():
    """Hermes homes are blocked; failure output must stay path-only."""
    hook = _hook_text()
    assert re.search(r"hermes", hook)
    assert "grep -o" not in hook
    assert "BASH_REMATCH" not in hook
    assert ".group(" not in hook


def test_precommit_greps_docs_like_without_exec():
    """Staged docs-like files are grepped as text, never executed."""
    hook = _hook_text()
    assert re.search(r"grep\s+-I\s+-E\s+-q", hook)
    for forbidden in (
        'bash "$file"',
        'sh "$file"',
        'source "$file"',
        'exec "$file"',
        'python "$file"',
        'python3 "$file"',
    ):
        assert forbidden not in hook


def test_precommit_uses_cached_and_diff_filter_acm():
    """Commit-state checks inspect the index only."""
    hook = _hook_text()
    assert "--cached" in hook
    assert "--diff-filter=ACM" in hook


def test_no_live_secrets_in_tracked_non_python_text():
    """Tracked non-Python text must not contain production-format signatures."""
    listed = subprocess.check_output(
        [
            "git",
            "ls-files",
            "*.md",
            "*.json",
            "*.sh",
            "*.yml",
            "*.yaml",
            "*.txt",
            "*.toml",
        ],
        cwd=BASE_DIR,
        text=True,
    ).splitlines()
    scanned = 0
    for rel_path in listed:
        suffix = Path(rel_path).suffix.lower()
        if suffix not in _NON_PYTHON_SUFFIXES:
            continue
        full = BASE_DIR / rel_path
        if not full.is_file():
            continue
        text = full.read_text(encoding="utf-8", errors="ignore")
        scanned += 1
        _assert_no_live_format(rel_path, text)
    assert scanned > 0, "Expected to scan at least one non-Python tracked text file"


def test_gitignore_requires_cursor_and_hermes_homes():
    """Agent-home gitignore rules must include .cursor/ and .hermes/."""
    lines = _gitignore_lines()
    assert ".cursor/" in lines
    assert ".hermes/" in lines


def test_audit_stays_inside_workspace():
    """Audit permission checks stay under ROOT_DIR; no out-of-workspace secret path."""
    audit = _audit_text()
    assert "/home/moku/secrets/google" not in audit
    assert 'Path("/home/' not in audit
    assert "ROOT_DIR / \".env\"" in audit
    assert "ROOT_DIR / \"secrets\"" in audit
    assert "drive_key.json" in audit
    assert "cookies.txt" in audit


def test_audit_findings_append_rel_path_only():
    """Audit findings identify paths and must not print matched secret text."""
    audit = _audit_text()
    assert "rel_path" in audit
    assert ".group(" not in audit
    assert "match.group" not in audit
    assert "group(0)" not in audit


def test_hook_and_audit_use_generic_signatures_not_live_literals():
    """Hook and audit pattern sources are generic format regexes, not live needles."""
    hook = _hook_text()
    audit = _audit_text()
    for rel, text in ((".githooks/pre-commit", hook), ("dev/audit_security.py", audit)):
        for pat in _PRODUCTION_SECRET_PATTERNS:
            assert pat.search(text) is None, f"live-format literal in {rel}"
        assert "-----BEGIN [A-Z ]*PRIVATE KEY-----" in text
        assert "ya29\\.[A-Za-z0-9_-]{50,}" in text
        assert "AKIA[0-9A-Z]{16}" in text
        assert "service_account" in text
        assert '"private_key"' in text


def test_synthetic_fixtures_use_placeholders_not_live_secrets():
    """Token-shaped samples are runtime-built or placeholders, never live copies."""
    pem = "-----BEGIN " + "RSA PRIVATE KEY-----"
    ya29 = "ya29." + ("A" * 50)
    akia = "AKIA" + ("0" * 16)
    sa = '{"type": "' + "service_account" + '", "' + "private_key" + '": "x"}'
    telegram = ("0" * 9) + ":" + ("A" * 35)
    assert _PEM_PATTERN.search(pem)
    assert _YA29_PATTERN.search(ya29)
    assert _AKIA_PATTERN.search(akia)
    assert _SA_TYPE_PATTERN.search(sa) and _SA_KEY_PATTERN.search(sa)
    assert any(pat.search(telegram) for pat in _PRODUCTION_SECRET_PATTERNS)
    this_file = Path(__file__).read_text(encoding="utf-8")
    for pat in _PRODUCTION_SECRET_PATTERNS:
        assert pat.search(this_file) is None, (
            "security policy tests must not embed live-format literals"
        )


def test_security_docs_mention_residual_git_object_and_ref_risk():
    """Residual history risk docs mention git objects and stale refs."""
    for rel in _HYGIENE_DOCS:
        text = (BASE_DIR / rel).read_text(encoding="utf-8").lower()
        assert "git objects" in text, rel
        assert "stale refs" in text, rel


def test_security_docs_say_history_rewrite_is_not_required():
    """History rewrite remains out of scope in the three security docs."""
    for rel in _HYGIENE_DOCS:
        text = (BASE_DIR / rel).read_text(encoding="utf-8").lower()
        assert "rewrite" in text, rel
        assert "not required" in text, rel


def test_no_default_apply_remote_delete_script():
    """Default apply must not ship a remote-delete script."""
    hits: list[str] = []
    for root_name in _DEFAULT_APPLY_SCAN_ROOTS:
        root = BASE_DIR / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            name = path.name.lower()
            if "remote-delete" in name or "delete-remote" in name:
                hits.append(str(path.relative_to(BASE_DIR)))
    assert hits == [], f"default apply must not ship remote-delete helpers: {hits}"


def test_no_default_apply_git_push_delete_helper():
    """Default apply must not include a git push --delete helper."""
    hits: list[str] = []
    for root_name in _DEFAULT_APPLY_SCAN_ROOTS:
        root = BASE_DIR / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".py", ".sh", ".yml", ".yaml", ""}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "git push --delete" in text:
                hits.append(str(path.relative_to(BASE_DIR)))
    assert hits == [], f"default apply must not contain git push --delete: {hits}"
