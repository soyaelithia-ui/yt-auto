#!/usr/bin/env python3
"""Container healthcheck with no external network calls.

Exit codes:
    0 — healthy (disk, SQLite integrity, daemon heartbeat fresh or absent)
    1 — infrastructure failure (disk below 1 GB, DB missing/corrupt)
    2 — stale daemon heartbeat (liveness gate, AUD-08)
"""

from __future__ import annotations

import os
import shutil
import time

from src.config import SETTINGS
from src.core.repository import connect

STALE_THRESHOLD_SECONDS = int(
    os.environ.get("DAEMON_STALE_THRESHOLD_SECONDS", "3600")
)


def disk_ok(path) -> bool:
    """At least 1 GB free on the volume holding the database."""
    try:
        return shutil.disk_usage(path).free >= 1024**3
    except OSError:
        return False


def database_ok(db_path) -> bool:
    if not db_path.exists():
        return False
    try:
        with connect(db_path, read_only=True) as conn:
            return conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    except Exception:
        return False


def daemon_heartbeat_fresh(
    db_path,
    *,
    now: int | None = None,
    threshold: int = STALE_THRESHOLD_SECONDS,
) -> bool:
    """True when the daemon heartbeat is missing (fresh install) or recent.

    A missing ``daemon_liveness`` row/table is treated as healthy so that
    fresh installs and pre-migration databases do not flap the container.
    """
    try:
        with connect(db_path, read_only=True) as conn:
            row = conn.execute(
                "SELECT heartbeat_at FROM daemon_liveness WHERE id = 1"
            ).fetchone()
    except Exception:
        return True  # table not migrated yet → infra checks only
    if not row or not row[0]:
        return True
    current = int(now) if now is not None else int(time.time())
    return (current - int(row[0])) <= threshold


from pathlib import Path


def main() -> int:
    for check_dir in [
        SETTINGS.database_path.parent,
        SETTINGS.work_root,
        SETTINGS.artifact_root,
        Path("/tmp"),
    ]:
        if Path(check_dir).exists() and not disk_ok(check_dir):
            return 1
    if not database_ok(SETTINGS.database_path):
        return 1
    if not daemon_heartbeat_fresh(SETTINGS.database_path):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
