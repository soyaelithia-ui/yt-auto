"""Safety and presence checks for agent worktree helpers.

Does not create live git worktrees (those are exercised operationally).
"""
from __future__ import annotations

import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_WORKTREE = REPO_ROOT / "scripts" / "agent_worktree.sh"
SETUP_ENV = REPO_ROOT / "scripts" / "setup_worktree_env.sh"


def test_worktree_scripts_are_executable():
    for path in (AGENT_WORKTREE, SETUP_ENV):
        assert path.is_file(), path
        mode = path.stat().st_mode
        assert mode & stat.S_IXUSR, f"{path} must be executable"


def test_agent_worktree_usage_exits_nonzero():
    result = subprocess.run(
        [str(AGENT_WORKTREE)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "create" in result.stdout
    assert "prune" in result.stdout


def test_agent_worktree_refuses_unsafe_remove_names():
    for name in (".", "..", "foo/bar", "../yt-auto", "foo bar"):
        result = subprocess.run(
            [str(AGENT_WORKTREE), "remove", name],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0, name
        combined = result.stdout + result.stderr
        assert "primary" in combined or "invalid" in combined or "Usage:" in combined


def test_setup_worktree_env_is_idempotent_on_primary():
    result = subprocess.run(
        [str(SETUP_ENV), str(REPO_ROOT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "secret" not in result.stdout.lower()
    assert "TOKEN" not in result.stdout
    assert "password" not in result.stdout.lower()


def test_integrity_scripts_use_repo_local_pytest_not_host_roots():
    for rel in ("scripts/verify_integrity.sh", "scripts/test.sh"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "/srv/projects/yt-auto/.venv/bin/pytest" not in text
        assert "/home/moku/projects/yt-auto/.venv/bin/pytest" not in text
        assert ".venv/bin/pytest" in text
