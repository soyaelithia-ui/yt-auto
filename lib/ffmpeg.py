"""Centralized FFmpeg/FFprobe execution runtime, metadata probe, and workspace lifecycle manager."""
from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)

__all__ = [
    "FFmpegError",
    "FFmpegExecutionError",
    "FFmpegTimeoutError",
    "FFprobeError",
    "VideoStreamInfo",
    "AudioStreamInfo",
    "MediaProbeResult",
    "FFmpegCommandResult",
    "SubprocessWatchdog",
    "run_ffmpeg",
    "run_ffprobe",
    "probe_media",
    "has_faststart",
    "TempMediaContext",
]

# ---------------------------------------------------------------------------
# Exception Hierarchy
# ---------------------------------------------------------------------------


class FFmpegError(RuntimeError):
    """Base exception for all FFmpeg and FFprobe errors."""
    pass


class FFmpegExecutionError(FFmpegError):
    """Raised when an FFmpeg or FFprobe command returns a non-zero exit code or fails execution."""

    def __init__(
        self,
        message: str,
        returncode: Optional[int] = None,
        stderr: Optional[str] = None,
        command: Optional[Sequence[Union[str, Path]]] = None,
    ) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr or ""
        self.command = [str(c) for c in command] if command else []


class FFmpegTimeoutError(FFmpegError):
    """Raised when an FFmpeg or FFprobe command times out and process group is terminated."""

    def __init__(
        self,
        message: str,
        timeout: Optional[float] = None,
        command: Optional[Sequence[Union[str, Path]]] = None,
    ) -> None:
        super().__init__(message)
        self.timeout = timeout
        self.command = [str(c) for c in command] if command else []


class FFprobeError(FFmpegError):
    """Raised when media probing fails, stream data is corrupt/missing, or FFprobe fails."""

    def __init__(
        self,
        message: str,
        returncode: Optional[int] = None,
        stderr: Optional[str] = None,
        command: Optional[Sequence[Union[str, Path]]] = None,
    ) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr or ""
        self.command = [str(c) for c in command] if command else []


# ---------------------------------------------------------------------------
# Structured Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class VideoStreamInfo:
    codec_name: str
    width: int
    height: int
    fps: float
    pix_fmt: str
    duration: float
    bit_rate: Optional[int] = None
    nb_frames: Optional[int] = None
    profile: Optional[str] = None


@dataclass
class AudioStreamInfo:
    codec_name: str
    sample_rate: int
    channels: int
    duration: float
    bit_rate: Optional[int] = None


@dataclass
class MediaProbeResult:
    format_name: str
    duration: float
    size_bytes: int
    bit_rate: int = 0
    video_streams: List[VideoStreamInfo] = field(default_factory=list)
    audio_streams: List[AudioStreamInfo] = field(default_factory=list)
    raw_payload: Dict[str, Any] = field(default_factory=dict)
    file_path: Optional[str] = None
    has_video_override: Optional[bool] = None
    has_audio_override: Optional[bool] = None

    def __init__(
        self,
        format_name: str = "",
        duration: float = 0.0,
        size_bytes: int = 0,
        bit_rate: int = 0,
        video_streams: Optional[List[VideoStreamInfo]] = None,
        audio_streams: Optional[List[AudioStreamInfo]] = None,
        raw_payload: Optional[Dict[str, Any]] = None,
        file_path: Optional[str] = None,
        has_video: Optional[bool] = None,
        has_audio: Optional[bool] = None,
    ) -> None:
        self.format_name = format_name
        self.duration = duration
        self.size_bytes = size_bytes
        self.bit_rate = bit_rate
        self.video_streams = video_streams if video_streams is not None else []
        self.audio_streams = audio_streams if audio_streams is not None else []
        self.raw_payload = raw_payload if raw_payload is not None else {}
        self.file_path = file_path
        self.has_video_override = has_video
        self.has_audio_override = has_audio

    @property
    def has_video(self) -> bool:
        if self.has_video_override is not None:
            return self.has_video_override
        return len(self.video_streams) > 0 or bool(self.primary_video)

    @property
    def has_audio(self) -> bool:
        if self.has_audio_override is not None:
            return self.has_audio_override
        return len(self.audio_streams) > 0 or bool(self.primary_audio)

    @property
    def primary_video(self) -> Optional[VideoStreamInfo]:
        return self.video_streams[0] if self.video_streams else None

    @property
    def primary_audio(self) -> Optional[AudioStreamInfo]:
        return self.audio_streams[0] if self.audio_streams else None


@dataclass
class FFmpegCommandResult:
    command: List[str]
    returncode: int
    stdout: Union[str, bytes]
    stderr: Union[str, bytes]
    duration_sec: float


# ---------------------------------------------------------------------------
# Subprocess Watchdog & Resource Monitor
# ---------------------------------------------------------------------------


class SubprocessWatchdog:
    """
    Non-blocking subprocess watchdog:
    - Tracks process group liveness and execution time (<= timeout_sec, default 180.0s)
    - Monitors RSS memory consumption (<= max_rss_mb, default 4096.0 MB / 4.0 GB)
    - Reaps process group with SIGTERM / SIGKILL on timeout or memory threshold violation
    """

    def __init__(
        self,
        max_rss_mb: float = 4096.0,
        timeout_sec: float = 180.0,
        poll_interval_sec: float = 0.2,
    ) -> None:
        self.max_rss_mb = float(max_rss_mb)
        self.timeout_sec = float(timeout_sec)
        self.poll_interval_sec = float(poll_interval_sec)

    @staticmethod
    def get_process_rss_mb(pid: int) -> float:
        """Reads resident set size (RSS) in MB for given PID from Linux /proc/statm."""
        try:
            statm_path = Path(f"/proc/{pid}/statm")
            if statm_path.is_file():
                parts = statm_path.read_text().split()
                if len(parts) >= 2:
                    rss_pages = int(parts[1])
                    page_size_kb = os.sysconf("SC_PAGE_SIZE") / 1024.0
                    return (rss_pages * page_size_kb) / 1024.0
        except Exception:
            pass
        return 0.0

    def monitor_process(self, proc: subprocess.Popen) -> None:
        """
        Monitors a running subprocess until completion, terminating process group if limits are violated.
        """
        start_time = time.monotonic()
        while proc.poll() is None:
            elapsed = time.monotonic() - start_time
            if elapsed > self.timeout_sec:
                self._terminate_process_group(proc)
                raise FFmpegTimeoutError(
                    f"Subprocess exceeded timeout limit of {self.timeout_sec}s",
                    timeout=self.timeout_sec,
                    command=getattr(proc, "args", []),
                )

            current_rss = self.get_process_rss_mb(proc.pid)
            if current_rss > self.max_rss_mb:
                self._terminate_process_group(proc)
                raise FFmpegExecutionError(
                    f"Subprocess exceeded RSS memory limit of {self.max_rss_mb:.1f} MB (used: {current_rss:.1f} MB)",
                    returncode=-9,
                    stderr=f"OOM: RSS {current_rss:.1f}MB > {self.max_rss_mb:.1f}MB",
                    command=getattr(proc, "args", []),
                )

            time.sleep(self.poll_interval_sec)

    def _terminate_process_group(self, proc: subprocess.Popen) -> None:
        """Terminates process group with SIGTERM followed by SIGKILL."""
        try:
            pgid = os.getpgid(proc.pid)
        except (ProcessLookupError, PermissionError, OSError):
            pgid = proc.pid

        try:
            os.killpg(pgid, signal.SIGTERM)
            time.sleep(0.15)
        except (ProcessLookupError, PermissionError, OSError):
            pass

        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except Exception:
                pass
        try:
            proc.wait(timeout=1.0)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Core Execution Engine
# ---------------------------------------------------------------------------


def run_ffmpeg(
    cmd: Sequence[Union[str, Path]],
    timeout: float = 300.0,
    cwd: Optional[Union[str, Path]] = None,
    check: bool = True,
    binary: bool = False,
    stderr_file: Optional[Union[str, Path]] = None,
    max_rss_mb: float = 4096.0,
) -> FFmpegCommandResult:
    """
    Executes an FFmpeg command within an isolated process group (start_new_session=True).
    Utilizes SubprocessWatchdog polling for timeout and memory enforcement.
    Guarantees SIGKILL process group termination on timeout/OOM and typed error translation.

    ``stderr_file`` (R2): when provided, stderr is streamed to that path instead of
    being buffered in RAM — for long analyses (blackdetect over longform masters)
    logs can reach tens of MB. The returned result keeps a short tail in memory.
    """
    import threading

    cmd_str_list = [str(c) for c in cmd]
    proc = None
    start_time = time.monotonic()
    try:
        stderr_target = (
            open(stderr_file, "wb") if stderr_file else subprocess.PIPE
        )
        proc = subprocess.Popen(
            cmd_str_list,
            stdout=subprocess.PIPE,
            stderr=stderr_target,
            text=not binary,
            cwd=str(cwd) if cwd else None,
            start_new_session=True,
        )
        try:
            from src.core.lifecycle import register_process
            register_process(proc)
        except Exception:
            pass

        poll_interval = min(0.1, max(0.005, timeout / 10.0))
        watchdog = SubprocessWatchdog(
            max_rss_mb=max_rss_mb,
            timeout_sec=timeout,
            poll_interval_sec=poll_interval,
        )
        watchdog_err: list[Exception] = []

        def _monitor() -> None:
            try:
                watchdog.monitor_process(proc)
            except Exception as ex:
                watchdog_err.append(ex)

        t_watch = threading.Thread(target=_monitor, daemon=True)
        t_watch.start()

        stdout, stderr = proc.communicate()
        t_watch.join(timeout=1.0)

        duration_sec = time.monotonic() - start_time
        if watchdog_err:
            if check:
                raise watchdog_err[0]
            if isinstance(watchdog_err[0], FFmpegTimeoutError):
                return FFmpegCommandResult(
                    command=cmd_str_list,
                    returncode=124,
                    stdout="",
                    stderr="TimeoutExpired",
                    duration_sec=duration_sec,
                )
            raise watchdog_err[0]

        if stderr_file:
            try:
                stderr_target.close()
            except Exception:
                pass
            # keep a bounded tail in memory for error messages (R2)
            try:
                with open(stderr_file, "rb") as fh:
                    fh.seek(0, 2)
                    _size = fh.tell()
                    fh.seek(max(0, _size - 8192))
                    tail = fh.read()
                stderr = tail.decode("utf-8", errors="replace") if not binary else tail
            except OSError:
                stderr = ""
        res = FFmpegCommandResult(
            command=cmd_str_list,
            returncode=proc.returncode,
            stdout=stdout or "",
            stderr=stderr or "",
            duration_sec=duration_sec,
        )
        if check and res.returncode != 0:
            logger.warning(
                "FFmpeg command failed with returncode %d: %s",
                res.returncode,
                res.stderr.strip()[:400] if isinstance(res.stderr, str) else str(res.stderr)[:400],
            )
            raise FFmpegExecutionError(
                f"FFmpeg command failed with returncode {res.returncode}: {res.stderr.strip() if isinstance(res.stderr, str) else ''}",
                returncode=res.returncode,
                stderr=res.stderr if isinstance(res.stderr, str) else res.stderr.decode("utf-8", errors="replace"),
                command=cmd_str_list,
            )
        return res
    except (subprocess.TimeoutExpired, FFmpegTimeoutError) as te:
        duration_sec = time.monotonic() - start_time
        logger.warning("FFmpeg command timed out after %.1f seconds: %s", timeout, cmd_str_list)
        if proc:
            try:
                pgid = os.getpgid(proc.pid)
            except (ProcessLookupError, PermissionError, OSError):
                pgid = proc.pid
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    proc.kill()
                except Exception:
                    pass
            try:
                proc.wait(timeout=1.0)
            except Exception:
                pass
        if check:
            raise FFmpegTimeoutError(
                f"FFmpeg command timed out after {timeout} seconds",
                timeout=timeout,
                command=cmd_str_list,
            ) from te
        return FFmpegCommandResult(
            command=cmd_str_list,
            returncode=124,
            stdout="",
            stderr="TimeoutExpired",
            duration_sec=duration_sec,
        )
    except FileNotFoundError as e:
        duration_sec = time.monotonic() - start_time
        msg = f"ffmpeg binary not found: {e}"
        if check:
            logger.warning("%s", msg)
            raise FFmpegExecutionError(
                msg,
                returncode=127,
                stderr="ffmpeg binary not found",
                command=cmd_str_list,
            ) from e
        return FFmpegCommandResult(
            command=cmd_str_list,
            returncode=127,
            stdout="",
            stderr="ffmpeg binary not found",
            duration_sec=duration_sec,
        )
    finally:
        if proc is not None:
            try:
                from src.core.lifecycle import unregister_process
                unregister_process(proc)
            except Exception:
                pass


def run_ffprobe(
    cmd: Sequence[Union[str, Path]],
    timeout: float = 30.0,
    cwd: Optional[Union[str, Path]] = None,
) -> FFmpegCommandResult:
    """
    Executes an FFprobe command within an isolated process group.
    Raises FFprobeError on non-zero return code or missing binary, and FFmpegTimeoutError on timeout.
    """
    cmd_str_list = [str(c) for c in cmd]
    proc = None
    start_time = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd_str_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(cwd) if cwd else None,
            start_new_session=True,
        )
        stdout, stderr = proc.communicate(timeout=timeout)
        duration_sec = time.monotonic() - start_time
        res = FFmpegCommandResult(
            command=cmd_str_list,
            returncode=proc.returncode,
            stdout=stdout or "",
            stderr=stderr or "",
            duration_sec=duration_sec,
        )
        if res.returncode != 0:
            raise FFprobeError(
                f"FFprobe command failed with returncode {res.returncode}: {res.stderr.strip()}",
                returncode=res.returncode,
                stderr=res.stderr,
                command=cmd_str_list,
            )
        return res
    except subprocess.TimeoutExpired as te:
        if proc:
            try:
                pgid = os.getpgid(proc.pid)
            except (ProcessLookupError, PermissionError, OSError):
                pgid = proc.pid
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    proc.kill()
                except Exception:
                    pass
            try:
                proc.wait(timeout=1.0)
            except Exception:
                pass
        raise FFmpegTimeoutError(
            f"FFprobe command timed out after {timeout} seconds",
            timeout=timeout,
            command=cmd_str_list,
        ) from te
    except FileNotFoundError as e:
        raise FFprobeError(
            f"ffprobe binary not found: {e}",
            returncode=127,
            stderr="ffprobe binary not found",
            command=cmd_str_list,
        ) from e


# ---------------------------------------------------------------------------
# Metadata Probing & Stream Analysis
# ---------------------------------------------------------------------------


def _parse_fps(fps_val: Optional[Union[str, int, float]]) -> float:
    """Safely parse frame rate values from FFprobe fractional or numeric representation."""
    if fps_val is None:
        return 0.0
    fps_str = str(fps_val).strip()
    if not fps_str:
        return 0.0
    if "/" in fps_str:
        parts = fps_str.split("/", 1)
        try:
            num = float(parts[0])
            den = float(parts[1])
            return num / den if den != 0 else 0.0
        except (ValueError, ZeroDivisionError):
            return 0.0
    try:
        return float(fps_str)
    except ValueError:
        return 0.0


def probe_media(
    file_path: Union[str, Path],
    timeout: float = 30.0,
) -> MediaProbeResult:
    """
    Analyzes a media file using FFprobe and returns a typed MediaProbeResult.
    Raises FFprobeError if the file does not exist, probe execution fails, or payload is invalid JSON.
    """
    path = Path(file_path)
    if not path.exists():
        raise FFprobeError(f"File not found: {file_path}")

    cmd = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]

    cmd_res = run_ffprobe(cmd, timeout=timeout)
    try:
        raw_payload = json.loads(cmd_res.stdout or "{}")
    except ValueError as exc:
        raise FFprobeError(
            f"Failed to parse ffprobe JSON output: {exc}",
            returncode=cmd_res.returncode,
            stderr=cmd_res.stderr,
            command=cmd,
        ) from exc

    fmt = raw_payload.get("format", {})
    format_name = str(fmt.get("format_name", ""))
    duration = float(fmt.get("duration", 0.0) or 0.0)
    size_bytes = int(fmt.get("size", 0) or 0)
    bit_rate = int(fmt.get("bit_rate", 0) or 0)

    video_streams: List[VideoStreamInfo] = []
    audio_streams: List[AudioStreamInfo] = []

    for s in raw_payload.get("streams", []):
        codec_type = s.get("codec_type")
        if codec_type == "video":
            v_codec = str(s.get("codec_name", ""))
            width = int(s.get("width", 0) or 0)
            height = int(s.get("height", 0) or 0)
            fps = _parse_fps(s.get("r_frame_rate") or s.get("avg_frame_rate"))
            pix_fmt = str(s.get("pix_fmt", ""))
            v_dur = float(s.get("duration") or duration or 0.0)
            v_br = int(s.get("bit_rate")) if s.get("bit_rate") is not None else None
            nb_frames = int(s.get("nb_frames")) if s.get("nb_frames") is not None else None

            v_profile = s.get("profile")
            video_streams.append(
                VideoStreamInfo(
                    codec_name=v_codec,
                    width=width,
                    height=height,
                    fps=fps,
                    pix_fmt=pix_fmt,
                    duration=v_dur,
                    bit_rate=v_br,
                    nb_frames=nb_frames,
                    profile=str(v_profile) if v_profile is not None else None,
                )
            )
        elif codec_type == "audio":
            a_codec = str(s.get("codec_name", ""))
            sample_rate = int(s.get("sample_rate", 0) or 0)
            channels = int(s.get("channels", 0) or 0)
            a_dur = float(s.get("duration") or duration or 0.0)
            a_br = int(s.get("bit_rate")) if s.get("bit_rate") is not None else None

            audio_streams.append(
                AudioStreamInfo(
                    codec_name=a_codec,
                    sample_rate=sample_rate,
                    channels=channels,
                    duration=a_dur,
                    bit_rate=a_br,
                )
            )

    return MediaProbeResult(
        format_name=format_name,
        duration=duration,
        size_bytes=size_bytes,
        bit_rate=bit_rate,
        video_streams=video_streams,
        audio_streams=audio_streams,
        raw_payload=raw_payload,
    )


def has_faststart(path: Union[str, Path]) -> bool:
    """
    Inspects MP4 binary container atoms to verify that the 'moov' index atom precedes 'mdat'.
    Returns False if file does not exist, is empty/truncated, or 'mdat' occurs before 'moov'.
    """
    try:
        p = Path(path)
        if not p.exists() or p.stat().st_size < 8:
            return False
        with open(p, "rb") as handle:
            data = handle.read(1024 * 1024)
        offset = 0
        while offset + 8 <= len(data):
            size = int.from_bytes(data[offset:offset + 4], "big")
            atom = data[offset + 4:offset + 8]
            if size < 8:
                break
            if atom == b"mdat":
                return False
            if atom == b"moov":
                return True
            offset += size
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Workspace Lifecycle Manager
# ---------------------------------------------------------------------------


class TempMediaContext:
    """
    Context manager providing managed scratch workspace allocation with guaranteed cleanup.
    Supports debug retention via retain_on_error=True.
    """

    def __init__(
        self,
        work_dir: Optional[Union[str, Path]] = None,
        prefix: str = "media_tmp_",
        retain_on_error: bool = False,
    ) -> None:
        self.work_dir = Path(work_dir) if work_dir else None
        self.prefix = prefix
        self.retain_on_error = retain_on_error
        self.temp_dir: Optional[Path] = None
        self._cleaned: bool = False

    def __enter__(self) -> TempMediaContext:
        if self.work_dir:
            self.work_dir.mkdir(parents=True, exist_ok=True)
            created = tempfile.mkdtemp(prefix=self.prefix, dir=str(self.work_dir))
        else:
            created = tempfile.mkdtemp(prefix=self.prefix)
        self.temp_dir = Path(created)
        return self

    @property
    def path(self) -> Path:
        if not self.temp_dir:
            raise RuntimeError("TempMediaContext is not active")
        return self.temp_dir

    def create_temp_file(self, suffix: str = ".mp4", prefix: str = "clip_") -> Path:
        """Generates a uniquely named scratch file inside the active temporary workspace."""
        if not self.temp_dir or not self.temp_dir.exists():
            raise RuntimeError("TempMediaContext is not active or workspace directory does not exist")
        fd, file_path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=str(self.temp_dir))
        os.close(fd)
        return Path(file_path)

    def cleanup(self) -> None:
        """Deterministically removes the temporary workspace directory and all contents."""
        if self.temp_dir and self.temp_dir.exists() and not self._cleaned:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self._cleaned = True

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None and self.retain_on_error:
            logger.warning(
                "Preserving temporary media directory on error for debugging: %s",
                self.temp_dir,
            )
            return
        self.cleanup()
