"""Unit tests for the daemon-liveness healthcheck gate (AUD-08) and degraded reports."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import healthcheck

from tests.unit.test_process_watch import _write_proc

CHECK_NAMES = [
    "disk",
    "binaries",
    "database",
    "daemon_heartbeat",
    "workers",
    "ffmpeg",
    "network",
]


def _make_db(tmp_path: Path, heartbeat: int | None) -> Path:
    db = tmp_path / "queue.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS daemon_liveness ("
        "id INTEGER PRIMARY KEY CHECK(id = 1), "
        "heartbeat_at INTEGER NOT NULL)"
    )
    if heartbeat is not None:
        conn.execute(
            "INSERT OR REPLACE INTO daemon_liveness(id, heartbeat_at) VALUES (1, ?)",
            (heartbeat,),
        )
    conn.commit()
    conn.close()
    return db


def _usage(free: int):
    return lambda path: SimpleNamespace(free=free)


def _which_ok(name: str) -> str:
    return f"/usr/bin/{name}"


def _proc_root(tmp_path: Path, *, ffmpeg_state: str | None = None, starttime: int = 100) -> Path:
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "uptime").write_text("500.0 0.0\n", encoding="ascii")
    if ffmpeg_state is not None:
        _write_proc(proc, pid=42, comm="ffmpeg", state=ffmpeg_state, starttime=starttime)
    return proc


def _route(tmp_path: Path, *, default: bool) -> Path:
    path = tmp_path / "route"
    dest = "00000000" if default else "0000000A"
    path.write_text(
        "Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\n"
        f"eth0 {dest} 010011AC 0003 0 0 0 00000000 0 0 0\n",
        encoding="ascii",
    )
    return path


def _report(tmp_path: Path, **kwargs):
    kwargs.setdefault("which_fn", _which_ok)
    kwargs.setdefault("check_timeout_seconds", 0)
    kwargs.setdefault("pid_alive_fn", lambda _pid: True)
    kwargs.setdefault("hang_seconds", 3600)
    if "proc_root" not in kwargs:
        kwargs["proc_root"] = _proc_root(tmp_path)
    if "route_path" not in kwargs:
        kwargs["route_path"] = _route(tmp_path, default=True)
    return healthcheck.collect_report(**kwargs)


def test_missing_table_is_treated_as_fresh(tmp_path):
    db = tmp_path / "empty.db"
    db.write_bytes(b"")
    assert healthcheck.daemon_heartbeat_fresh(db, now=1_000_000)


def test_zero_heartbeat_is_treated_as_fresh(tmp_path):
    db = _make_db(tmp_path, 0)  # INSERT OR IGNORE seed value
    assert healthcheck.daemon_heartbeat_fresh(db, now=1_000_000)


def test_recent_heartbeat_is_fresh(tmp_path):
    db = _make_db(tmp_path, 1_000_000)
    assert healthcheck.daemon_heartbeat_fresh(db, now=1_000_100, threshold=3600)


def test_stale_heartbeat_is_detected(tmp_path):
    db = _make_db(tmp_path, 1_000_000)
    assert not healthcheck.daemon_heartbeat_fresh(
        db, now=1_000_000 + 3601, threshold=3600
    )


def test_report_healthy_json_and_text(tmp_path, monkeypatch):
    db = _make_db(tmp_path, 1_000_000)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr("src.core.process_watch._clk_tck", lambda: 100.0)
    report = _report(
        tmp_path,
        db_path=db,
        disk_paths=[work],
        now=1_000_100,
        threshold=3600,
        usage_fn=_usage(5 * 1024**3),
    )
    assert report.status == "OK"
    assert report.exit_code == 0
    payload = json.loads(healthcheck.format_json(report))
    assert payload["status"] == "OK"
    assert payload["exit_code"] == 0
    names = [c["name"] for c in payload["checks"]]
    assert names == CHECK_NAMES
    text = healthcheck.format_text(report)
    assert text.startswith("status=OK exit=0")
    assert "disk: ok" in text


def test_report_degraded_low_disk_and_no_route_still_exits_zero(tmp_path, monkeypatch):
    db = _make_db(tmp_path, 1_000_000)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr("src.core.process_watch._clk_tck", lambda: 100.0)
    report = _report(
        tmp_path,
        db_path=db,
        disk_paths=[work],
        now=1_000_100,
        route_path=_route(tmp_path, default=False),
        usage_fn=_usage(int(1.5 * 1024**3)),
    )
    assert report.status == "DEGRADED"
    assert report.exit_code == 0
    by_name = {c.name: c for c in report.checks}
    assert by_name["disk"].status == "degraded"
    assert by_name["network"].status == "degraded"


def test_report_critical_on_disk_fail_floor(tmp_path, monkeypatch):
    db = _make_db(tmp_path, 1_000_000)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr("src.core.process_watch._clk_tck", lambda: 100.0)
    report = _report(
        tmp_path,
        db_path=db,
        disk_paths=[work],
        now=1_000_100,
        usage_fn=_usage(512 * 1024**2),
    )
    assert report.status == "CRITICAL"
    assert report.exit_code == 1


def test_stale_heartbeat_keeps_exit_code_two(tmp_path, monkeypatch):
    db = _make_db(tmp_path, 1_000_000)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr("src.core.process_watch._clk_tck", lambda: 100.0)
    report = _report(
        tmp_path,
        db_path=db,
        disk_paths=[work],
        now=1_000_000 + 4000,
        threshold=3600,
        usage_fn=_usage(5 * 1024**3),
    )
    assert report.exit_code == 2
    assert report.status == "CRITICAL"


def test_zombie_ffmpeg_is_degraded_not_fatal(tmp_path, monkeypatch):
    db = _make_db(tmp_path, 1_000_000)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr("src.core.process_watch._clk_tck", lambda: 100.0)
    report = _report(
        tmp_path,
        db_path=db,
        disk_paths=[work],
        now=1_000_100,
        proc_root=_proc_root(tmp_path, ffmpeg_state="Z", starttime=4000),
        usage_fn=_usage(5 * 1024**3),
    )
    assert report.status == "DEGRADED"
    assert report.exit_code == 0
    ffmpeg = next(c for c in report.checks if c.name == "ffmpeg")
    assert ffmpeg.status == "degraded"
    assert ffmpeg.data["processes"][0]["state"] == "Z"


def test_missing_binary_is_critical(tmp_path, monkeypatch):
    db = _make_db(tmp_path, 1_000_000)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr("src.core.process_watch._clk_tck", lambda: 100.0)
    report = _report(
        tmp_path,
        db_path=db,
        disk_paths=[work],
        now=1_000_100,
        usage_fn=_usage(5 * 1024**3),
        which_fn=lambda name: None,
    )
    assert report.status == "CRITICAL"
    assert report.exit_code == 1
    binaries = next(c for c in report.checks if c.name == "binaries")
    assert binaries.status == "critical"


def test_dead_worker_pid_is_degraded(tmp_path, monkeypatch):
    db = _make_db(tmp_path, 1_000_000)
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE lane_leases ("
        "job_id TEXT PRIMARY KEY, lane_id TEXT, channel TEXT, owner TEXT, "
        "run_id TEXT, acquired_at INTEGER, heartbeat_at INTEGER, expires_at INTEGER)"
    )
    conn.execute(
        "INSERT INTO lane_leases VALUES (?,?,?,?,?,?,?,?)",
        ("story-1", "moku-scp-shorts", "moku", "lane-moku-scp-shorts:999001", "run-1", 1, 1, 9_999_999),
    )
    conn.commit()
    conn.close()
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr("src.core.process_watch._clk_tck", lambda: 100.0)
    report = _report(
        tmp_path,
        db_path=db,
        disk_paths=[work],
        now=1_000_100,
        usage_fn=_usage(5 * 1024**3),
        pid_alive_fn=lambda _pid: False,
    )
    assert report.status == "DEGRADED"
    assert report.exit_code == 0
    workers = next(c for c in report.checks if c.name == "workers")
    assert workers.status == "degraded"
    assert workers.data["dead"] == 1


def test_budget_exhaustion_marks_remaining_degraded(tmp_path):
    db = _make_db(tmp_path, 1_000_000)
    work = tmp_path / "work"
    work.mkdir()
    report = healthcheck.collect_report(
        db_path=db,
        disk_paths=[work],
        now=1_000_100,
        usage_fn=_usage(5 * 1024**3),
        budget_seconds=-1,
        check_timeout_seconds=0,
        which_fn=_which_ok,
    )
    assert report.status == "DEGRADED"
    assert report.exit_code == 0
    assert all(c.status == "degraded" for c in report.checks)
    assert all("budget exhausted" in c.detail for c in report.checks)


def test_main_json_flag_emits_one_object(tmp_path, monkeypatch, capsys):
    db = _make_db(tmp_path, 1_000_000)
    work = tmp_path / "work"
    work.mkdir()
    original = healthcheck.collect_report

    def fake_report():
        return original(
            db_path=db,
            disk_paths=[work],
            now=1_000_100,
            proc_root=_proc_root(tmp_path),
            route_path=_route(tmp_path, default=True),
            usage_fn=_usage(5 * 1024**3),
            hang_seconds=3600,
            which_fn=_which_ok,
            check_timeout_seconds=0,
            pid_alive_fn=lambda _pid: True,
        )

    monkeypatch.setattr("healthcheck.collect_report", fake_report)
    monkeypatch.setattr("src.core.process_watch._clk_tck", lambda: 100.0)
    code = healthcheck.main(["--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    assert code == 0
    assert payload["status"] == "OK"
    assert captured.out.endswith("\n")
