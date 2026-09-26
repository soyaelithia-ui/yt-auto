"""Non-blocking process inspection for healthcheck and the production daemon.

Stdlib only. Does not import ``src.media`` — hung FFmpeg is detected from
``/proc`` so render-pipeline branches can keep landing independently.
"""

from __future__ import annotations

import os
import signal
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


_DEFAULT_PROC_ROOT = Path("/proc")
_FFMPEG_NAMES = frozenset({"ffmpeg", "ffprobe"})


@dataclass(frozen=True)
class ProcSnapshot:
    pid: int
    name: str
    state: str
    ppid: int
    elapsed_seconds: float
    cmdline: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["elapsed_seconds"] = round(self.elapsed_seconds, 1)
        return payload

    @property
    def is_zombie(self) -> bool:
        return self.state == "Z"

    def is_hung(self, max_age_seconds: float) -> bool:
        if self.is_zombie:
            return True
        # max_age_seconds <= 0 means "kill now" (daemon abort / turn timeout).
        return self.elapsed_seconds >= max_age_seconds


def reap_zombies() -> int:
    """Reap exited children without blocking the caller. Returns how many were joined."""
    reaped = 0
    while True:
        try:
            pid, _status = os.waitpid(-1, os.WNOHANG)
        except (ChildProcessError, OSError):
            break
        if pid == 0:
            break
        reaped += 1
    return reaped


def _clk_tck() -> float:
    try:
        value = os.sysconf("SC_CLK_TCK")
    except (ValueError, OSError, AttributeError):
        return 100.0
    return float(value) if value and value > 0 else 100.0


def _read_uptime_seconds(proc_root: Path) -> float | None:
    try:
        raw = (proc_root / "uptime").read_text(encoding="ascii").split()[0]
        return float(raw)
    except (OSError, IndexError, ValueError):
        return None


def _parse_stat(stat_text: str) -> tuple[str, str, int, int] | None:
    """Return ``(name, state, ppid, starttime_ticks)`` from a ``/proc/pid/stat`` line."""
    start = stat_text.find("(")
    end = stat_text.rfind(")")
    if start < 0 or end < 0 or end <= start:
        return None
    name = stat_text[start + 1 : end]
    rest = stat_text[end + 1 :].split()
    if len(rest) < 20:
        return None
    try:
        state = rest[0]
        ppid = int(rest[1])
        starttime = int(rest[19])
    except (ValueError, IndexError):
        return None
    return name, state, ppid, starttime


def _read_cmdline(pid_dir: Path) -> str:
    try:
        raw = (pid_dir / "cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()


def list_named_processes(
    names: Iterable[str] = _FFMPEG_NAMES,
    *,
    proc_root: Path | str = _DEFAULT_PROC_ROOT,
    parent_pid: int | None = None,
) -> list[ProcSnapshot]:
    """List processes whose comm matches ``names``. Optionally restrict to descendants."""
    root = Path(proc_root)
    wanted = {n.lower() for n in names}
    uptime = _read_uptime_seconds(root)
    ticks = _clk_tck()
    snapshots: list[ProcSnapshot] = []
    for entry in _iter_pid_dirs(root):
        snap = _snapshot_pid(entry, uptime=uptime, ticks=ticks)
        if snap is None or snap.name.lower() not in wanted:
            continue
        snapshots.append(snap)
    if parent_pid is None:
        return snapshots
    descendants = _descendant_pids(snapshots_ppids=_ppid_index(root, snapshots), root_pid=parent_pid)
    descendants.add(parent_pid)
    return [snap for snap in snapshots if snap.pid in descendants or snap.ppid in descendants]


def list_ffmpeg_processes(
    *,
    proc_root: Path | str = _DEFAULT_PROC_ROOT,
    parent_pid: int | None = None,
) -> list[ProcSnapshot]:
    return list_named_processes(_FFMPEG_NAMES, proc_root=proc_root, parent_pid=parent_pid)


def hung_ffmpeg_processes(
    max_age_seconds: float,
    *,
    proc_root: Path | str = _DEFAULT_PROC_ROOT,
    parent_pid: int | None = None,
    exclude_pids: Iterable[int] = (),
) -> list[ProcSnapshot]:
    excluded = set(exclude_pids)
    return [
        snap
        for snap in list_ffmpeg_processes(proc_root=proc_root, parent_pid=parent_pid)
        if snap.pid not in excluded and snap.is_hung(max_age_seconds)
    ]


def has_default_route(route_path: Path | str = "/proc/net/route") -> bool | None:
    """True when an IPv4 default route exists. None if the table cannot be read.

    No sockets and no DNS — a network drop is reported as degraded, never as a
    probe that could itself hang the healthcheck.
    """
    path = Path(route_path)
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except OSError:
        return None
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        if parts[1] == "00000000":
            return True
    return False


def terminate_hung_ffmpeg(
    max_age_seconds: float,
    *,
    proc_root: Path | str = _DEFAULT_PROC_ROOT,
    parent_pid: int | None = None,
    grace_seconds: float = 2.0,
    exclude_pids: Iterable[int] = (),
) -> dict[str, Any]:
    """SIGTERM then SIGKILL our hung FFmpeg descendants. Never touches unrelated PIDs."""
    owner = os.getpid() if parent_pid is None else int(parent_pid)
    targets = hung_ffmpeg_processes(
        max_age_seconds,
        proc_root=proc_root,
        parent_pid=owner,
        exclude_pids=exclude_pids,
    )
    signaled: list[int] = []
    killed: list[int] = []
    for snap in targets:
        try:
            os.kill(snap.pid, signal.SIGTERM)
            signaled.append(snap.pid)
        except (ProcessLookupError, PermissionError, OSError):
            continue
    if signaled and grace_seconds > 0:
        time.sleep(grace_seconds)
    still = {snap.pid for snap in hung_ffmpeg_processes(
        max_age_seconds,
        proc_root=proc_root,
        parent_pid=owner,
        exclude_pids=exclude_pids,
    )}
    for pid in signaled:
        if pid not in still:
            continue
        try:
            os.kill(pid, signal.SIGKILL)
            killed.append(pid)
        except (ProcessLookupError, PermissionError, OSError):
            continue
    reap_zombies()
    return {"signaled": signaled, "killed": killed}


def _iter_pid_dirs(proc_root: Path) -> Iterable[Path]:
    try:
        entries = proc_root.iterdir()
    except OSError:
        return
    for entry in entries:
        if entry.name.isdigit():
            yield entry


def _snapshot_pid(pid_dir: Path, *, uptime: float | None, ticks: float) -> ProcSnapshot | None:
    try:
        stat_text = (pid_dir / "stat").read_text(encoding="ascii")
    except OSError:
        return None
    parsed = _parse_stat(stat_text)
    if parsed is None:
        return None
    name, state, ppid, starttime = parsed
    elapsed = 0.0
    if uptime is not None and ticks > 0:
        elapsed = max(0.0, uptime - (starttime / ticks))
    try:
        pid = int(pid_dir.name)
    except ValueError:
        return None
    return ProcSnapshot(
        pid=pid,
        name=name,
        state=state,
        ppid=ppid,
        elapsed_seconds=elapsed,
        cmdline=_read_cmdline(pid_dir),
    )


def _ppid_index(proc_root: Path, snapshots: list[ProcSnapshot]) -> dict[int, int]:
    index = {snap.pid: snap.ppid for snap in snapshots}
    for entry in _iter_pid_dirs(proc_root):
        pid = int(entry.name)
        if pid in index:
            continue
        snap = _snapshot_pid(entry, uptime=None, ticks=100.0)
        if snap is not None:
            index[snap.pid] = snap.ppid
    return index


def _descendant_pids(snapshots_ppids: dict[int, int], root_pid: int) -> set[int]:
    children: dict[int, list[int]] = {}
    for pid, ppid in snapshots_ppids.items():
        children.setdefault(ppid, []).append(pid)
    found: set[int] = set()
    stack = list(children.get(root_pid, ()))
    while stack:
        pid = stack.pop()
        if pid in found:
            continue
        found.add(pid)
        stack.extend(children.get(pid, ()))
    return found
