"""Handler for Systemd service management and build automation."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SERVICE = "youtube_daemon.service"
ROOT = Path(__file__).resolve().parents[3]


def _run(command: list[str], *, cwd: Path | None = None, timeout: float = 30.0) -> int:
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            shell=False,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"Command timed out after {timeout}s: {' '.join(command)}", file=sys.stderr)
        return 124
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"Command execution error: {exc}", file=sys.stderr)
        return 1
    return int(result.returncode)


def handle_service(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Execute Systemd service controls, build validation, or journal logs."""
    action = getattr(args, "action", None) or getattr(args, "command", None)
    if action == "build":
        python_status = _run(
            [sys.executable, "-m", "compileall", "-q", "src", "main.py", "manage.py"],
            cwd=ROOT,
        )
        ts_dir = ROOT / "ts_services"
        node_status = _run(["npm", "run", "build"], cwd=ts_dir) if ts_dir.is_dir() else 0
        return python_status or node_status
    if action in {"start", "stop", "restart"}:
        return _run(["systemctl", action, SERVICE])
    if action == "logs":
        return _run(["journalctl", "-u", SERVICE, "-n", "200", "--no-pager"])
    return 2
