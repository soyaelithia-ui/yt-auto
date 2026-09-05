"""Unit tests for non-blocking process inspection (zombies, hung FFmpeg, routes)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from src.core.process_watch import (
    has_default_route,
    hung_ffmpeg_processes,
    list_ffmpeg_processes,
    reap_zombies,
    terminate_hung_ffmpeg,
)


def _stat_line(pid: int, comm: str, state: str, starttime: int, ppid: int = 1) -> str:
    rest = [state, str(ppid)] + ["0"] * 17 + [str(starttime)]
    return f"{pid} ({comm}) {' '.join(rest)}\n"


def _write_proc(
    proc_root: Path,
    *,
    pid: int,
    comm: str,
    state: str = "S",
    starttime: int = 100,
    ppid: int = 1,
    cmdline: str = "ffmpeg -i in.mp4",
) -> None:
    pid_dir = proc_root / str(pid)
    pid_dir.mkdir(parents=True)
    (pid_dir / "stat").write_text(
        _stat_line(pid, comm, state, starttime, ppid=ppid), encoding="ascii"
    )
    (pid_dir / "comm").write_text(f"{comm}\n", encoding="ascii")
    (pid_dir / "cmdline").write_bytes(cmdline.replace(" ", "\x00").encode("ascii") + b"\x00")


def test_reap_zombies_is_non_blocking():
    with patch("os.waitpid", side_effect=[(4242, 0), (0, 0)]) as waitpid:
        assert reap_zombies() == 1
        waitpid.assert_called_with(-1, os.WNOHANG)


def test_reap_zombies_handles_no_children():
    with patch("os.waitpid", side_effect=ChildProcessError):
        assert reap_zombies() == 0


def test_list_ffmpeg_reports_elapsed_and_ignores_unrelated(tmp_path):
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "uptime").write_text("100.0 0.0\n", encoding="ascii")
    _write_proc(proc, pid=10, comm="ffmpeg", starttime=1000)  # 100 - 10 = 90s if CLK=100
    _write_proc(proc, pid=11, comm="python", starttime=100)
    with patch("src.core.process_watch._clk_tck", return_value=100.0):
        found = list_ffmpeg_processes(proc_root=proc)
    assert [snap.pid for snap in found] == [10]
    assert found[0].elapsed_seconds == 90.0
    assert found[0].state == "S"


def test_hung_ffmpeg_includes_zombies_regardless_of_age(tmp_path):
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "uptime").write_text("50.0 0.0\n", encoding="ascii")
    _write_proc(proc, pid=7, comm="ffmpeg", state="Z", starttime=4000)
    with patch("src.core.process_watch._clk_tck", return_value=100.0):
        hung = hung_ffmpeg_processes(3600, proc_root=proc)
    assert len(hung) == 1
    assert hung[0].is_zombie


def test_hung_ffmpeg_flags_over_age_process(tmp_path):
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "uptime").write_text("500.0 0.0\n", encoding="ascii")
    _write_proc(proc, pid=8, comm="ffmpeg", starttime=100)  # elapsed 499s
    with patch("src.core.process_watch._clk_tck", return_value=100.0):
        assert hung_ffmpeg_processes(600, proc_root=proc) == []
        hung = hung_ffmpeg_processes(100, proc_root=proc)
    assert [snap.pid for snap in hung] == [8]


def test_has_default_route_true_false_and_unreadable(tmp_path):
    table = tmp_path / "route"
    table.write_text(
        "Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\n"
        "eth0 00000000 010011AC 0003 0 0 0 00000000 0 0 0\n",
        encoding="ascii",
    )
    assert has_default_route(table) is True
    table.write_text(
        "Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\n"
        "eth0 0000000A 00000000 0001 0 0 0 00FFFFFF 0 0 0\n",
        encoding="ascii",
    )
    assert has_default_route(table) is False
    assert has_default_route(tmp_path / "missing") is None


def test_zero_max_age_treats_live_ffmpeg_as_hung(tmp_path):
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "uptime").write_text("50.0 0.0\n", encoding="ascii")
    _write_proc(proc, pid=3, comm="ffmpeg", starttime=4000)
    with patch("src.core.process_watch._clk_tck", return_value=100.0):
        hung = hung_ffmpeg_processes(0, proc_root=proc)
    assert [snap.pid for snap in hung] == [3]


def test_terminate_hung_ffmpeg_only_signals_descendants(tmp_path):
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "uptime").write_text("500.0 0.0\n", encoding="ascii")
    _write_proc(proc, pid=50, comm="ffmpeg", starttime=100, ppid=9)
    _write_proc(proc, pid=51, comm="ffmpeg", starttime=100, ppid=1)
    signaled: list[tuple[int, int]] = []

    def fake_kill(pid, sig):
        signaled.append((pid, sig))

    with patch("src.core.process_watch._clk_tck", return_value=100.0), patch(
        "os.kill", side_effect=fake_kill
    ), patch("src.core.process_watch.reap_zombies", return_value=0), patch(
        "time.sleep"
    ):
        report = terminate_hung_ffmpeg(
            100, proc_root=proc, parent_pid=9, grace_seconds=0
        )
    assert report["signaled"] == [50]
    assert 51 not in report["signaled"]
