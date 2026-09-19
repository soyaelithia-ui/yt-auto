#!/usr/bin/env python3
"""Container healthcheck with no external network calls.

Report statuses: OK, DEGRADED, CRITICAL.

Exit codes:
    0 — OK or DEGRADED (disk warn, missing route, hung FFmpeg, dead worker PID)
    1 — CRITICAL infrastructure (disk fail floor, DB missing/corrupt, binaries)
    2 — CRITICAL stale daemon heartbeat (liveness gate, AUD-08)

Each check is budgeted so this process cannot block Docker's HEALTHCHECK.
No sockets and no DNS: a network drop is a local route-table read only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

STALE_THRESHOLD_SECONDS = int(os.environ.get("DAEMON_STALE_THRESHOLD_SECONDS", "3600"))
DISK_FAIL_BYTES = int(os.environ.get("HEALTHCHECK_DISK_FAIL_BYTES", str(1024**3)))
DISK_WARN_BYTES = int(os.environ.get("HEALTHCHECK_DISK_WARN_BYTES", str(2 * 1024**3)))
TMP_FAIL_BYTES = int(os.environ.get("HEALTHCHECK_TMP_FAIL_BYTES", str(64 * 1024**2)))
TMP_WARN_BYTES = int(os.environ.get("HEALTHCHECK_TMP_WARN_BYTES", str(512 * 1024**2)))
CHECK_TIMEOUT_SECONDS = float(os.environ.get("HEALTHCHECK_CHECK_TIMEOUT_SECONDS", "2"))
BUDGET_SECONDS = float(os.environ.get("HEALTHCHECK_BUDGET_SECONDS", "8"))
SQLITE_TIMEOUT_SECONDS = float(os.environ.get("HEALTHCHECK_SQLITE_TIMEOUT_SECONDS", "2"))
FFMPEG_HANG_SECONDS = int(os.environ.get("HEALTHCHECK_FFMPEG_HANG_SECONDS", "0"))

_STATUS_RANK = {"ok": 0, "degraded": 1, "critical": 2}
_OWNER_PID_RE = re.compile(r"[:_](\d+)$")
_REPORT_STATUS = {"ok": "OK", "degraded": "DEGRADED", "critical": "CRITICAL"}


@dataclass
class HealthCheck:
    name: str
    status: str
    detail: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {"name": self.name, "status": self.status, "detail": self.detail}
        payload.update(self.data)
        return payload


@dataclass
class HealthReport:
    status: str
    exit_code: int
    checks: list[HealthCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "checks": [check.to_dict() for check in self.checks],
        }


def disk_ok(path) -> bool:
    """At least the fail-floor free on the volume holding ``path``."""
    try:
        p = Path(path)
        floor = TMP_FAIL_BYTES if _is_temp_path(p) else DISK_FAIL_BYTES
        return shutil.disk_usage(path).free >= floor
    except OSError:
        return False


def _connect_readonly(db_path, timeout: float = SQLITE_TIMEOUT_SECONDS) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=timeout)
    conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
    return conn


def database_ok(db_path) -> bool:
    path = Path(db_path)
    if not path.exists():
        return False
    try:
        conn = _connect_readonly(path)
        try:
            return conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        finally:
            conn.close()
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
        conn = _connect_readonly(db_path)
        try:
            row = conn.execute(
                "SELECT heartbeat_at FROM daemon_liveness WHERE id = 1"
            ).fetchone()
        finally:
            conn.close()
    except Exception:
        return True  # table not migrated yet → infra checks only
    if not row or not row[0]:
        return True
    current = int(now) if now is not None else int(time.time())
    return (current - int(row[0])) <= threshold


def _default_binaries() -> tuple[str, ...]:
    raw = os.environ.get("HEALTHCHECK_BINARIES", "ffmpeg,ffprobe")
    return tuple(part.strip() for part in raw.split(",") if part.strip()) or ("ffmpeg", "ffprobe")


def _is_temp_path(path: Path) -> bool:
    temps: list[Path] = []
    for candidate in (Path("/tmp"), Path(tempfile.gettempdir())):
        try:
            temps.append(candidate.resolve())
        except OSError:
            temps.append(candidate)
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    return resolved in temps


def _disk_status(free_bytes: int, path: Path | None = None) -> str:
    is_tmp = path is not None and _is_temp_path(path)
    fail = TMP_FAIL_BYTES if is_tmp else DISK_FAIL_BYTES
    if free_bytes < fail:
        return "critical"
    warn = TMP_WARN_BYTES if is_tmp else DISK_WARN_BYTES
    if free_bytes < warn:
        return "degraded"
    return "ok"


def _default_disk_paths() -> list[Path]:
    from src.config import SETTINGS

    candidates = [
        SETTINGS.database_path.parent,
        SETTINGS.work_root,
        SETTINGS.artifact_root,
        Path("/tmp"),
        Path(tempfile.gettempdir()),
    ]
    seen: set[str] = set()
    paths: list[Path] = []
    for raw in candidates:
        path = Path(raw)
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return paths


def check_disk(
    paths: Iterable[Path | str] | None = None,
    *,
    usage_fn: Callable[[str | os.PathLike], Any] = shutil.disk_usage,
) -> HealthCheck:
    targets = [Path(p) for p in paths] if paths is not None else _default_disk_paths()
    entries: list[dict[str, Any]] = []
    worst = "ok"
    for path in targets:
        if not path.exists():
            continue
        try:
            free = int(usage_fn(path).free)
        except OSError as exc:
            entries.append(
                {"path": str(path), "free_bytes": 0, "status": "critical", "error": str(exc)}
            )
            worst = "critical"
            continue
        status = _disk_status(free, path)
        if _STATUS_RANK[status] > _STATUS_RANK[worst]:
            worst = status
        entries.append({"path": str(path), "free_bytes": free, "status": status})
    if not entries:
        return HealthCheck("disk", "critical", "no disk paths could be checked", {"paths": []})
    if worst == "critical":
        detail = "one or more volumes below 1 GB fail floor"
    elif worst == "degraded":
        detail = "one or more volumes below warn floor"
    else:
        detail = "all volumes above warn floor"
    return HealthCheck("disk", worst, detail, {"paths": entries})


def check_binaries(
    *,
    names: Iterable[str] | None = None,
    which_fn: Callable[[str], str | None] = shutil.which,
) -> HealthCheck:
    wanted = list(names) if names is not None else list(_default_binaries())
    found: dict[str, str | None] = {}
    missing: list[str] = []
    for name in wanted:
        path = which_fn(name)
        found[name] = path
        if not path:
            missing.append(name)
    if missing:
        return HealthCheck(
            "binaries",
            "critical",
            f"missing binaries: {', '.join(missing)}",
            {"binaries": found, "missing": missing},
        )
    return HealthCheck(
        "binaries",
        "ok",
        "key binaries present",
        {"binaries": found, "missing": []},
    )


def check_database(db_path) -> HealthCheck:
    path = Path(db_path)
    if not path.exists():
        return HealthCheck("database", "critical", "database file missing")
    if not database_ok(path):
        return HealthCheck("database", "critical", "sqlite quick_check failed")
    return HealthCheck("database", "ok", "quick_check ok")


def check_heartbeat(
    db_path,
    *,
    now: int | None = None,
    threshold: int = STALE_THRESHOLD_SECONDS,
) -> HealthCheck:
    current = int(now) if now is not None else int(time.time())
    try:
        conn = _connect_readonly(db_path)
        try:
            row = conn.execute(
                "SELECT heartbeat_at FROM daemon_liveness WHERE id = 1"
            ).fetchone()
        finally:
            conn.close()
    except Exception:
        return HealthCheck(
            "daemon_heartbeat",
            "ok",
            "liveness table absent (fresh install)",
            {"age_seconds": None},
        )
    if not row or not row[0]:
        return HealthCheck(
            "daemon_heartbeat",
            "ok",
            "heartbeat unset (fresh install)",
            {"age_seconds": None},
        )
    age = current - int(row[0])
    if age > threshold:
        return HealthCheck(
            "daemon_heartbeat",
            "critical",
            f"stale heartbeat ({age}s > {threshold}s)",
            {"age_seconds": age},
        )
    return HealthCheck(
        "daemon_heartbeat",
        "ok",
        f"fresh ({age}s)",
        {"age_seconds": age},
    )


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _owner_pid(owner: str) -> int | None:
    match = _OWNER_PID_RE.search(owner or "")
    return int(match.group(1)) if match else None


def check_workers(
    db_path,
    *,
    now: int | None = None,
    pid_alive_fn: Callable[[int], bool] | None = None,
) -> HealthCheck:
    """Read-only lease scan: dead worker PIDs are DEGRADED, never CRITICAL."""
    alive = pid_alive_fn or _pid_is_alive
    current = int(now) if now is not None else int(time.time())
    leases: list[dict[str, Any]] = []
    try:
        conn = _connect_readonly(db_path)
        try:
            queries = (
                ("leases", "SELECT owner, run_id, expires_at, NULL AS lane_id FROM leases"),
                ("lane_leases", "SELECT owner, run_id, expires_at, lane_id FROM lane_leases"),
            )
            for table, sql in queries:
                try:
                    rows = conn.execute(sql).fetchall()
                except sqlite3.OperationalError:
                    continue
                for owner, run_id, expires_at, lane_id in rows:
                    pid = _owner_pid(str(owner or ""))
                    expired = expires_at is not None and int(expires_at) < current
                    dead = pid is not None and not alive(pid)
                    leases.append(
                        {
                            "table": table,
                            "owner": owner,
                            "run_id": run_id,
                            "lane_id": lane_id,
                            "pid": pid,
                            "expired": expired,
                            "dead": dead,
                        }
                    )
        finally:
            conn.close()
    except Exception as exc:
        return HealthCheck(
            "workers",
            "ok",
            f"leases unread ({exc})",
            {"leases": []},
        )
    dead = [row for row in leases if row["dead"]]
    expired = [row for row in leases if row["expired"] and not row["dead"]]
    payload = {"leases": leases, "dead": len(dead), "expired": len(expired)}
    if dead:
        return HealthCheck(
            "workers",
            "degraded",
            f"{len(dead)} worker PID(s) dead",
            payload,
        )
    if expired:
        return HealthCheck(
            "workers",
            "degraded",
            f"{len(expired)} lease(s) expired",
            payload,
        )
    if leases:
        return HealthCheck(
            "workers",
            "ok",
            f"{len(leases)} active worker lease(s)",
            payload,
        )
    return HealthCheck("workers", "ok", "no active worker leases", payload)


def _ffmpeg_hang_seconds() -> int:
    if FFMPEG_HANG_SECONDS > 0:
        return FFMPEG_HANG_SECONDS
    try:
        from src.config import SETTINGS

        return int(SETTINGS.render_timeout_seconds)
    except Exception:
        return 10_800


def check_ffmpeg(
    *,
    proc_root: Path | str | None = None,
    hang_seconds: int | None = None,
) -> HealthCheck:
    from src.core.process_watch import list_ffmpeg_processes

    kwargs: dict[str, Any] = {}
    if proc_root is not None:
        kwargs["proc_root"] = proc_root
    try:
        processes = list_ffmpeg_processes(**kwargs)
    except Exception as exc:
        return HealthCheck("ffmpeg", "degraded", f"process scan failed: {exc}")
    limit = _ffmpeg_hang_seconds() if hang_seconds is None else hang_seconds
    hung = [snap for snap in processes if snap.is_hung(limit)]
    payload = {"processes": [snap.to_dict() for snap in processes], "hang_seconds": limit}
    if hung:
        zombies = sum(1 for snap in hung if snap.is_zombie)
        detail = (
            f"{len(hung)} hung/zombie ffmpeg "
            f"({zombies} zombie) of {len(processes)} running"
        )
        return HealthCheck("ffmpeg", "degraded", detail, payload)
    if processes:
        return HealthCheck(
            "ffmpeg",
            "ok",
            f"{len(processes)} ffmpeg running within timeout",
            payload,
        )
    return HealthCheck("ffmpeg", "ok", "no hung or zombie ffmpeg", payload)


def check_network(*, route_path: Path | str | None = None) -> HealthCheck:
    from src.core.process_watch import has_default_route

    present = has_default_route() if route_path is None else has_default_route(route_path)
    if present is None:
        return HealthCheck("network", "ok", "route table unreadable; skipped")
    if present:
        return HealthCheck("network", "ok", "default route present")
    return HealthCheck(
        "network",
        "degraded",
        "no default route (network disconnected)",
    )


def _worst_status(checks: list[HealthCheck]) -> str:
    worst = "ok"
    for check in checks:
        if _STATUS_RANK.get(check.status, 0) > _STATUS_RANK[worst]:
            worst = check.status
    return worst


def _call_with_timeout(
    factory: Callable[[], HealthCheck],
    timeout: float,
) -> HealthCheck | None:
    if timeout <= 0:
        return factory()
    box: list[HealthCheck | BaseException] = []

    def worker() -> None:
        try:
            box.append(factory())
        except BaseException as exc:  # noqa: BLE001 — surface to caller
            box.append(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive() or not box:
        return None
    value = box[0]
    if isinstance(value, BaseException):
        raise value
    return value


def collect_report(
    *,
    db_path: Path | str | None = None,
    disk_paths: Iterable[Path | str] | None = None,
    now: int | None = None,
    threshold: int | None = None,
    proc_root: Path | str | None = None,
    route_path: Path | str | None = None,
    usage_fn: Callable[[str | os.PathLike], Any] | None = None,
    hang_seconds: int | None = None,
    budget_seconds: float | None = None,
    which_fn: Callable[[str], str | None] | None = None,
    binaries: Iterable[str] | None = None,
    pid_alive_fn: Callable[[int], bool] | None = None,
    check_timeout_seconds: float | None = None,
) -> HealthReport:
    from src.config import SETTINGS

    deadline = time.monotonic() + (BUDGET_SECONDS if budget_seconds is None else budget_seconds)
    per_check = CHECK_TIMEOUT_SECONDS if check_timeout_seconds is None else check_timeout_seconds
    target_db = Path(db_path) if db_path is not None else SETTINGS.database_path
    checks: list[HealthCheck] = []

    def run(name: str, factory: Callable[[], HealthCheck]) -> None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            checks.append(
                HealthCheck(name, "degraded", "skipped: healthcheck budget exhausted")
            )
            return
        timeout = per_check if per_check <= 0 else min(per_check, remaining)
        try:
            result = _call_with_timeout(factory, timeout)
        except Exception as exc:
            checks.append(HealthCheck(name, "critical", f"check error: {exc}"))
            return
        if result is None:
            checks.append(HealthCheck(name, "degraded", "skipped: check timed out"))
            return
        checks.append(result)

    disk_kwargs: dict[str, Any] = {}
    if disk_paths is not None:
        disk_kwargs["paths"] = disk_paths
    if usage_fn is not None:
        disk_kwargs["usage_fn"] = usage_fn
    binary_kwargs: dict[str, Any] = {}
    if binaries is not None:
        binary_kwargs["names"] = binaries
    if which_fn is not None:
        binary_kwargs["which_fn"] = which_fn
    worker_kwargs: dict[str, Any] = {"db_path": target_db, "now": now}
    if pid_alive_fn is not None:
        worker_kwargs["pid_alive_fn"] = pid_alive_fn

    run("disk", lambda: check_disk(**disk_kwargs))
    run("binaries", lambda: check_binaries(**binary_kwargs))
    run("database", lambda: check_database(target_db))
    hb_kwargs: dict[str, Any] = {"db_path": target_db, "now": now}
    if threshold is not None:
        hb_kwargs["threshold"] = threshold
    run("daemon_heartbeat", lambda: check_heartbeat(**hb_kwargs))
    run("workers", lambda: check_workers(**worker_kwargs))
    run(
        "ffmpeg",
        lambda: check_ffmpeg(proc_root=proc_root, hang_seconds=hang_seconds),
    )
    run("network", lambda: check_network(route_path=route_path))

    worst = _worst_status(checks)
    heartbeat = next((c for c in checks if c.name == "daemon_heartbeat"), None)
    if heartbeat is not None and heartbeat.status == "critical":
        exit_code = 2
        status = "CRITICAL"
    elif worst == "critical":
        exit_code = 1
        status = "CRITICAL"
    else:
        exit_code = 0
        status = _REPORT_STATUS.get(worst, "OK")
    return HealthReport(status=status, exit_code=exit_code, checks=checks)


def format_text(report: HealthReport) -> str:
    lines = [f"status={report.status} exit={report.exit_code}"]
    for check in report.checks:
        lines.append(f"{check.name}: {check.status} — {check.detail}")
    return "\n".join(lines)


def format_json(report: HealthReport) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, separators=(",", ":"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Container liveness healthcheck")
    parser.add_argument("--json", action="store_true", help="emit a single JSON object")
    parser.add_argument("--quiet", action="store_true", help="exit code only")
    args = parser.parse_args(argv)
    as_json = args.json or os.environ.get("HEALTHCHECK_FORMAT", "").lower() == "json"
    report = collect_report()
    if not args.quiet:
        rendered = format_json(report) if as_json else format_text(report)
        sys.stdout.write(rendered if rendered.endswith("\n") else rendered + "\n")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
