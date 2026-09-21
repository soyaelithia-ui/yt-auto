"""
Channel lock lifecycle and process mutual exclusion foundation.
Provides non-blocking file locking with deterministic context manager cleanup.
"""

from __future__ import annotations

import fcntl
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Optional

try:
    from src.config import LOCK_FILE_PATH
except (ImportError, AttributeError):
    LOCK_FILE_PATH = os.environ.get(
        "LOCK_FILE_PATH",
        str(Path(__file__).resolve().parent.parent.parent / "scratch" / "youtube_automation.lock")
    )

_INITIAL_LOCK_PATH = str(LOCK_FILE_PATH)


def _get_default_lock_path() -> str:
    main_mod = sys.modules.get("main")
    if main_mod and hasattr(main_mod, "LOCK_FILE_PATH"):
        if str(main_mod.LOCK_FILE_PATH) != _INITIAL_LOCK_PATH:
            return str(main_mod.LOCK_FILE_PATH)

    mod = sys.modules.get("src.core.lock")
    if mod and hasattr(mod, "LOCK_FILE_PATH"):
        if str(mod.LOCK_FILE_PATH) != _INITIAL_LOCK_PATH:
            return str(mod.LOCK_FILE_PATH)

    cfg_mod = sys.modules.get("src.config")
    if cfg_mod and hasattr(cfg_mod, "LOCK_FILE_PATH"):
        if str(cfg_mod.LOCK_FILE_PATH) != _INITIAL_LOCK_PATH:
            return str(cfg_mod.LOCK_FILE_PATH)

    return _INITIAL_LOCK_PATH


class ChannelLockError(RuntimeError):
    """Raised when a channel lock cannot be acquired due to collision or I/O error."""
    pass


def _is_file_locked(path: str) -> tuple[bool, str]:
    """Check non-blockingly if a lock file is held by fcntl.flock."""
    if not os.path.exists(path):
        return False, ""
    f = None
    try:
        f = open(path, "r+", encoding="utf-8")
    except FileNotFoundError:
        return False, ""
    except (IOError, OSError):
        try:
            f = open(path, "r", encoding="utf-8")
        except FileNotFoundError:
            return False, ""
        except (IOError, OSError):
            return True, "?"
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()
        return False, ""
    except (IOError, OSError):
        holder_pid = "?"
        try:
            f.seek(0)
            holder_pid = f.read().strip() or "?"
        except Exception:
            pass
        try:
            f.close()
        except Exception:
            pass
        return True, holder_pid


class ChannelLock:
    """
    Context manager for atomic per-channel file locking with optional timeout.
    Uses kernel-managed fcntl.flock to guarantee OS-level multi-process mutual exclusion.
    """

    DEFAULT_TIMEOUT: float = 30.0

    def __init__(
        self,
        channel_name: str = "global",
        lock_file_path: Optional[str | Path] = None,
        lock_dir: Optional[str | Path] = None,
        timeout: Optional[float] = None,
        poll_interval: float = 0.5,
    ) -> None:
        self.channel_name = channel_name if channel_name else "global"
        self.timeout = self.DEFAULT_TIMEOUT if timeout is None else float(timeout)
        self.poll_interval = max(0.05, float(poll_interval))
        self._file_handle: Optional[Any] = None
        self._acquired: bool = False
        self._is_reentrant: bool = False
        self._lock_file_path = lock_file_path
        self._lock_dir = lock_dir

        self.lock_file = self._resolve_lock_path(self.channel_name)

    def _resolve_lock_path(self, name: Any) -> str:
        name_str = getattr(name, "value", str(name)) if name is not None else ""
        if self._lock_file_path is not None:
            base_lock = str(self._lock_file_path)
            return base_lock if name_str in ("global", "", "None") else f"{base_lock}.{name_str}"
        elif self._lock_dir is not None:
            dir_path = Path(self._lock_dir)
            filename = "youtube_automation.lock" if name_str in ("global", "", "None") else f"youtube_automation.lock.{name_str}"
            return str(dir_path / filename)
        elif "YT_LOCK_DIR" in os.environ:
            dir_path = Path(os.environ["YT_LOCK_DIR"])
            filename = "youtube_automation.lock" if name_str in ("global", "", "None") else f"youtube_automation.lock.{name_str}"
            return str(dir_path / filename)
        else:
            base_lock = _get_default_lock_path()
            return str(base_lock) if name_str in ("global", "", "None") else f"{base_lock}.{name_str}"

    @property
    def is_acquired(self) -> bool:
        return self._acquired

    @property
    def path(self) -> str:
        return self.lock_file

    def acquire(
        self,
        timeout: Optional[float] = None,
        poll_interval: Optional[float] = None,
        reentrant: bool = False,
    ) -> bool:
        """
        Acquires exclusive lock on channel lock file.
        If timeout is provided, retries acquisition every poll_interval seconds until acquired or timeout expires.
        Raises ChannelLockError if lock is already held and cannot be acquired within timeout.
        """
        if self._acquired and self._file_handle is not None:
            return True

        if reentrant:
            held_lock = _active_locks.get(self.channel_name)
            if (
                held_lock is not None
                and held_lock._acquired
                and held_lock._file_handle is not None
                and os.path.abspath(held_lock.path) == os.path.abspath(self.path)
            ):
                self._file_handle = held_lock._file_handle
                self._acquired = True
                self._is_reentrant = True
                return True

        effective_timeout = timeout if timeout is not None else self.timeout
        effective_poll = poll_interval if poll_interval is not None else self.poll_interval
        deadline = (time.monotonic() + max(0.0, float(effective_timeout))) if effective_timeout is not None else None

        while True:
            # Hierarchy Conflict Check
            conflict_ch = None
            conflict_pid = None

            if self.channel_name == "all":
                cids: set[str] = set()
                try:
                    from src.core.channel_profile import ChannelProfileRegistry
                    cids.update(str(getattr(cid, "value", cid)) for cid in ChannelProfileRegistry.list_active_channel_ids())
                except Exception:
                    pass
                try:
                    from src.core.lanes import load_lanes
                    cids.update(str(getattr(lane.channel, "value", lane.channel)) for lane in load_lanes())
                except Exception:
                    pass
                try:
                    lock_dir_path = Path(self.lock_file).parent
                    dummy_name = Path(self._resolve_lock_path("___probe___")).name
                    prefix = dummy_name.replace("___probe___", "")
                    if lock_dir_path.exists():
                        for p in lock_dir_path.glob(f"{prefix}*"):
                            cand = p.name[len(prefix):]
                            if cand and cand != "all":
                                cids.add(cand)
                except Exception:
                    pass

                for cid in sorted(cids):
                    ch_path = self._resolve_lock_path(cid)
                    is_locked, holder = _is_file_locked(ch_path)
                    if is_locked:
                        conflict_ch = cid
                        conflict_pid = holder
                        break
            elif self.channel_name not in ("global", None, ""):
                all_path = self._resolve_lock_path("all")
                is_locked, holder = _is_file_locked(all_path)
                if is_locked:
                    conflict_ch = "all"
                    conflict_pid = holder

            if conflict_ch is not None:
                if deadline is not None and time.monotonic() < deadline:
                    time.sleep(min(effective_poll, max(0.05, deadline - time.monotonic())))
                    continue
                timeout_suffix = f" tras esperar {effective_timeout}s" if effective_timeout is not None else ""
                raise ChannelLockError(
                    f"Error: Another instance of the YouTube Automation script for channel [{conflict_ch}] "
                    f"is already running (pid={conflict_pid}){timeout_suffix}."
                )

            f = None
            try:
                os.makedirs(os.path.dirname(os.path.abspath(self.lock_file)), exist_ok=True)
                f = open(self.lock_file, "a+", encoding="utf-8")
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                f.seek(0)
                f.truncate()
                f.write(f"{os.getpid()}\n")
                f.flush()
                os.fsync(f.fileno())
                self._file_handle = f
                self._acquired = True
                return True
            except (IOError, OSError) as err:
                self._acquired = False
                if f is not None:
                    try:
                        f.close()
                    except Exception:
                        pass
                self._file_handle = None

                if deadline is not None and time.monotonic() < deadline:
                    time.sleep(min(effective_poll, max(0.05, deadline - time.monotonic())))
                    continue

                holder_pid = "?"
                try:
                    if os.path.exists(self.lock_file):
                        with open(self.lock_file, "r", encoding="utf-8") as lf:
                            holder_pid = lf.read().strip() or "?"
                except Exception:
                    pass

                timeout_suffix = f" tras esperar {effective_timeout}s" if effective_timeout is not None else ""
                raise ChannelLockError(
                    f"Error: Another instance of the YouTube Automation script for channel [{self.channel_name}] "
                    f"is already running (pid={holder_pid}){timeout_suffix}."
                ) from err

    def release(self) -> None:
        """
        Releases lock, closes descriptor, and unlinks file if PID matches current process.
        """
        if self._is_reentrant:
            self._acquired = False
            self._file_handle = None
            return

        if self._file_handle is not None:
            try:
                fcntl.flock(self._file_handle, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                self._file_handle.close()
            except Exception:
                pass
            self._file_handle = None

        if os.path.exists(self.lock_file):
            try:
                with open(self.lock_file, "r", encoding="utf-8") as lf:
                    pid_in_file = lf.read().strip()
                if pid_in_file == str(os.getpid()):
                    os.unlink(self.lock_file)
            except Exception:
                pass

        self._acquired = False

    def __enter__(self) -> ChannelLock:
        held_lock = _active_locks.get(self.channel_name)
        if (
            held_lock is not None
            and held_lock._acquired
            and held_lock._file_handle is not None
            and os.path.abspath(held_lock.path) == os.path.abspath(self.path)
        ):
            self._file_handle = held_lock._file_handle
            self._acquired = True
            self._is_reentrant = True
            return self

        self.acquire(timeout=self.timeout, poll_interval=self.poll_interval, reentrant=True)
        _active_locks[self.channel_name] = self
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            self.release()
        finally:
            if not self._is_reentrant and _active_locks.get(self.channel_name) is self:
                _active_locks.pop(self.channel_name, None)


_active_locks: dict[str, ChannelLock] = {}
_legacy_active_channel: str = "global"


def acquire_lock(
    channel_name: str = "global",
    timeout: Optional[float] = None,
    lock_dir: Optional[str | Path] = None,
    lock_file_path: Optional[str | Path] = None,
) -> None:
    """Legacy compatibility function for acquiring a lock."""
    global _legacy_active_channel
    _legacy_active_channel = channel_name if channel_name else "global"
    lock = ChannelLock(
        channel_name=_legacy_active_channel,
        lock_file_path=lock_file_path,
        lock_dir=lock_dir,
        timeout=timeout,
    )
    try:
        lock.acquire(reentrant=True)
        _active_locks[_legacy_active_channel] = lock
    except ChannelLockError as exc:
        print(str(exc))
        sys.exit(1)



def release_lock(channel_name: str | None = None) -> None:
    """Legacy compatibility function for releasing a lock."""
    global _legacy_active_channel
    if channel_name is None or channel_name == "":
        channels_to_release = list(_active_locks.keys())
        if not channels_to_release and _legacy_active_channel:
            channels_to_release = [_legacy_active_channel]
    else:
        channels_to_release = [channel_name]

    for ch in channels_to_release:
        lock = _active_locks.pop(ch, None)
        if lock is not None:
            lock.release()
        else:
            dummy = ChannelLock(channel_name=ch)
            dummy.release()


def _handle_signal(sig: int, frame: Any) -> None:
    """Signal handler for graceful termination and lock cleanup."""
    print(f"\nReceived signal {sig}, shutting down gracefully...")
    try:
        from src.daemon import request_shutdown
        request_shutdown()
    except Exception:
        pass
    release_lock()
    sys.exit(0)


def register_signal_handlers() -> None:
    """Register SIGINT and SIGTERM handlers."""
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
