"""Audio mastering helpers (shared core): loudness normalization, ducking, mastering, dramatic pauses."""
from __future__ import annotations

import logging
import os
import re
import subprocess
import wave
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from lib.ffmpeg import (
    FFmpegError as CoreFFmpegError,
    FFmpegExecutionError as CoreFFmpegExecutionError,
    FFmpegTimeoutError as CoreFFmpegTimeoutError,
    run_ffmpeg,
)

logger = logging.getLogger(__name__)


class AudioProcessingError(RuntimeError):
    """Base exception for audio processing failures."""
    pass


class FFmpegExecutionError(CoreFFmpegExecutionError, AudioProcessingError):
    """Raised when FFmpeg execution fails during audio processing."""
    def __init__(
        self,
        message: str,
        returncode: Optional[int] = None,
        stderr: Optional[str] = None,
    ) -> None:
        super().__init__(message, returncode=returncode, stderr=stderr)


def _ffmpeg_run(
    cmd: list[str],
    check: bool = False,
    timeout: float = 300.0,
) -> subprocess.CompletedProcess:
    """Executes FFmpeg subprocess via lib.ffmpeg runner."""
    try:
        res = run_ffmpeg(cmd, timeout=timeout, check=check)
        return subprocess.CompletedProcess(res.command, res.returncode, res.stdout, res.stderr)
    except CoreFFmpegTimeoutError as te:
        logger.warning("FFmpeg command timed out after %s seconds: %s", timeout, cmd)
        if check:
            raise FFmpegExecutionError(
                f"FFmpeg command timed out after {timeout} seconds",
                returncode=124,
                stderr="TimeoutExpired",
            ) from te
        return subprocess.CompletedProcess(cmd, returncode=124, stdout="", stderr="TimeoutExpired")
    except CoreFFmpegExecutionError as ee:
        if check:
            raise FFmpegExecutionError(
                str(ee),
                returncode=ee.returncode,
                stderr=ee.stderr,
            ) from ee
        return subprocess.CompletedProcess(
            ee.command or cmd,
            returncode=ee.returncode if ee.returncode is not None else 1,
            stdout="",
            stderr=ee.stderr,
        )
    except FileNotFoundError as e:
        if check:
            logger.warning("ffmpeg binary not found")
            raise FFmpegExecutionError("ffmpeg binary not found", returncode=127, stderr="ffmpeg binary not found") from e
        return subprocess.CompletedProcess(cmd, returncode=127, stdout="", stderr="ffmpeg binary not found")


def _looks_like_real_input(path: str | os.PathLike | None) -> bool:
    if not path:
        return False
    p = Path(path)
    return p.exists() and p.stat().st_size > 0


# ============================================================================
# Dramatic Pause Parsing & Handling
# ============================================================================

PAUSE_TAG_REGEX = re.compile(
    r"\[\s*(?:PAUSA|PAUSE|SILENCE)(?:\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*(ms|s|sec|seconds|segundos|s\.)?)?\s*\]",
    re.IGNORECASE,
)


def parse_pause_duration(val_str: str | None, unit_str: str | None, default_sec: float = 1.2) -> float:
    """Parses duration string and unit (s, ms, etc.) into seconds, bounded safely."""
    if not val_str:
        return default_sec
    try:
        val = float(val_str)
        unit = (unit_str or "s").lower().strip()
        if unit == "ms":
            dur = val / 1000.0
        else:
            dur = val
        return max(0.1, min(30.0, round(dur, 3)))
    except (ValueError, TypeError):
        return default_sec


def parse_dramatic_pauses(script_text: str) -> list[dict[str, Any]]:
    """
    Parses script text for dramatic pause tags ([PAUSA: <dur>], [PAUSE: <dur>], [SILENCE: <dur>]).
    Splits text into narrative segments and associated pause durations.

    Returns a list of segment dicts with keys:
    - index: segment index
    - text: segment narrative text
    - pause_after: pause duration in seconds to follow this segment (0.0 if none)
    - pause_duration: alias for pause_after
    - tag: matched pause tag string (or None)
    - has_pause: bool indicating if a pause follows
    """
    if not script_text or not isinstance(script_text, str):
        return []

    matches = list(PAUSE_TAG_REGEX.finditer(script_text))
    if not matches:
        return [{
            "index": 0,
            "text": script_text.strip(),
            "pause_after": 0.0,
            "pause_duration": 0.0,
            "tag": None,
            "has_pause": False,
        }]

    segments: list[dict[str, Any]] = []
    last_end = 0

    for idx, match in enumerate(matches):
        start, end = match.span()
        segment_text = script_text[last_end:start].strip()
        dur = parse_pause_duration(match.group(1), match.group(2))
        tag_str = match.group(0)

        segments.append({
            "index": idx,
            "text": segment_text,
            "pause_after": dur,
            "pause_duration": dur,
            "tag": tag_str,
            "has_pause": True,
        })
        last_end = end

    trailing_text = script_text[last_end:].strip()
    if trailing_text or not segments:
        segments.append({
            "index": len(segments),
            "text": trailing_text,
            "pause_after": 0.0,
            "pause_duration": 0.0,
            "tag": None,
            "has_pause": False,
        })

    return segments


def extract_dramatic_pauses(script_text: str) -> list[dict[str, Any]]:
    """Extracts metadata of all dramatic pause tags present in script text."""
    if not script_text or not isinstance(script_text, str):
        return []
    pauses: list[dict[str, Any]] = []
    for m in PAUSE_TAG_REGEX.finditer(script_text):
        dur = parse_pause_duration(m.group(1), m.group(2))
        pauses.append({
            "tag": m.group(0),
            "duration_sec": dur,
            "start": m.start(),
            "end": m.end(),
        })
    return pauses


def strip_dramatic_pauses(script_text: str) -> str:
    """Strips all dramatic pause tags from script text, returning pure spoken text."""
    if not script_text or not isinstance(script_text, str):
        return ""
    cleaned = PAUSE_TAG_REGEX.sub(" ", script_text)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
    return cleaned.strip()


def generate_silence_audio(
    output_path: str | os.PathLike,
    duration_sec: float,
    sample_rate: int = 48000,
    channels: int = 2,
) -> str:
    """
    Generates a calibrated low-amplitude / silence PCM audio file of exact duration.
    Uses 16-bit PCM WAV to avoid NaN encoder issues downstream.
    """
    out_target = str(output_path)
    Path(out_target).parent.mkdir(parents=True, exist_ok=True)
    duration_sec = max(0.05, float(duration_sec))
    num_samples = int(sample_rate * duration_sec)

    with wave.open(out_target, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        zero_frame = struct.pack(f"<{channels}h", *([0] * channels))
        chunk_size = 4096
        full_chunks, remainder = divmod(num_samples, chunk_size)
        chunk_bytes = zero_frame * chunk_size
        for _ in range(full_chunks):
            wav_file.writeframes(chunk_bytes)
        if remainder:
            wav_file.writeframes(zero_frame * remainder)

    return out_target


def shift_word_timestamps_with_pauses(
    chunk_timestamps: list[list[dict]],
    chunk_durations: list[float],
    pause_durations: list[float],
) -> list[dict]:
    """
    Calculates monotonically shifted word boundary timestamps across multiple audio chunks
    separated by calibrated pause durations.

    Each chunk's timestamps are offset by the cumulative sum of previous chunk durations + pause durations.
    """
    combined: list[dict] = []
    cumulative_offset = 0.0

    num_chunks = len(chunk_timestamps)
    for i in range(num_chunks):
        words = chunk_timestamps[i]
        c_dur = chunk_durations[i] if i < len(chunk_durations) else (words[-1]["end"] if words else 0.0)
        p_dur = pause_durations[i] if i < len(pause_durations) else 0.0

        for w in words:
            combined.append({
                "word": w.get("word", ""),
                "start": round(w.get("start", 0.0) + cumulative_offset, 3),
                "end": round(w.get("end", 0.0) + cumulative_offset, 3),
            })

        cumulative_offset += c_dur + p_dur

    return combined


def insert_dramatic_pauses_to_audio(
    audio_paths: list[str | os.PathLike],
    pause_durations: list[float],
    output_path: str | os.PathLike,
    word_timestamps_per_chunk: list[list[dict]] | None = None,
) -> tuple[str, list[dict]]:
    """
    Concatenates speech audio segments inserting calibrated silence intervals for dramatic pauses.
    Also returns monotonic word boundary timestamps with shifted offsets.
    """
    valid_paths = [str(p) for p in audio_paths if _looks_like_real_input(p)]
    if not valid_paths:
        return (str(output_path), [])

    out_target = str(output_path)
    Path(out_target).parent.mkdir(parents=True, exist_ok=True)

    if len(valid_paths) == 1 and (not pause_durations or pause_durations[0] <= 0):
        if Path(valid_paths[0]).resolve() != Path(out_target).resolve():
            import shutil
            shutil.copyfile(valid_paths[0], out_target)
        words = word_timestamps_per_chunk[0] if word_timestamps_per_chunk else []
        return (out_target, words)

    seq_files: list[str] = []
    temp_silence_files: list[str] = []
    chunk_durations: list[float] = []

    try:
        from lib.tts import get_audio_duration
        for idx, chunk_path in enumerate(valid_paths):
            seq_files.append(chunk_path)
            c_dur = get_audio_duration(chunk_path)
            chunk_durations.append(c_dur)

            p_dur = pause_durations[idx] if idx < len(pause_durations) else 0.0
            if p_dur > 0 and idx < len(valid_paths) - 1:
                silence_p = out_target + f".tmp_silence_{idx}.wav"
                generate_silence_audio(silence_p, duration_sec=p_dur, sample_rate=48000, channels=2)
                temp_silence_files.append(silence_p)
                seq_files.append(silence_p)

        n = len(seq_files)
        inputs_cmd = []
        filter_inputs = []
        for i, f_path in enumerate(seq_files):
            inputs_cmd.extend(["-i", str(f_path)])
            filter_inputs.append(f"[{i}:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a{i}];")

        concat_str = "".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[aout]"
        filter_complex = "".join(filter_inputs) + concat_str

        cmd = [
            "ffmpeg", "-y",
            *inputs_cmd,
            "-filter_complex", filter_complex,
            "-map", "[aout]",
            "-ar", "48000", "-ac", "2",
            out_target
        ]
        _ffmpeg_run(cmd, check=True)

        shifted_words: list[dict] = []
        if word_timestamps_per_chunk:
            shifted_words = shift_word_timestamps_with_pauses(
                word_timestamps_per_chunk,
                chunk_durations,
                pause_durations[:len(chunk_durations)],
            )

        return (out_target, shifted_words)
    finally:
        for sf in temp_silence_files:
            if os.path.exists(sf):
                try:
                    os.remove(sf)
                except OSError:
                    pass


# ============================================================================
# Master Audio Loudness Normalization (-14.0 LUFS / -1.5 dBTP)
# ============================================================================

def normalize_narration_lufs(
    input_path: str | os.PathLike | None = None,
    output_path: str | os.PathLike | None = None,
    target_lufs: float = -14.0,
    max_tp: float = -1.5,
    apply_lowpass: bool = True,
    lowpass_freq: float = 12000.0,
) -> str:
    """EBU R128 loudness normalization (loudnorm: I=-14.0, TP=-1.5, LRA=11) with optional lowpass."""
    if not _looks_like_real_input(input_path):
        return str(input_path) if input_path else ""
    out_target = str(output_path or input_path)
    Path(out_target).parent.mkdir(parents=True, exist_ok=True)

    use_tmp = False
    try:
        if Path(input_path).resolve() == Path(out_target).resolve():
            use_tmp = True
    except Exception:
        use_tmp = (str(input_path) == str(out_target))

    out_cmd = out_target + ".tmp.norm.wav" if use_tmp else out_target

    filters = []
    if apply_lowpass and lowpass_freq and lowpass_freq > 0:
        filters.append(f"lowpass=f={lowpass_freq}")
    filters.append(f"loudnorm=I={target_lufs}:TP={max_tp}:LRA=11")
    filters.append("apad=pad_dur=1.0")
    try:
        try:
            _ffmpeg_run(
                ["ffmpeg", "-y", "-i", str(input_path), "-af", ",".join(filters),
                 "-ar", "48000", "-ac", "2", out_cmd],
                check=True,
            )
        except Exception as exc:
            logger.warning("Primary loudnorm FFmpeg failed: %s; attempting fallback copy", exc, exc_info=True)
            try:
                _ffmpeg_run(["ffmpeg", "-y", "-i", str(input_path), "-c", "copy", out_cmd], check=True)
            except Exception as copy_exc:
                logger.error("Fallback FFmpeg copy failed: %s", copy_exc, exc_info=True)
                raise FFmpegExecutionError(
                    f"Audio loudness normalization failed for input '{input_path}': primary ({exc}), fallback ({copy_exc})"
                ) from copy_exc

        if not _looks_like_real_input(out_cmd):
            logger.error("Output audio artifact %s is missing or 0 bytes after normalization", out_cmd)
            raise AudioProcessingError(f"Output audio artifact {out_cmd} is missing or empty after normalization")

        if use_tmp:
            os.replace(out_cmd, out_target)
    finally:
        if use_tmp and os.path.exists(out_cmd):
            try:
                os.remove(out_cmd)
            except OSError:
                pass

    return out_target


# ============================================================================
# Sidechain Ducking Filter Graph
# ============================================================================

def apply_sidechain_ducking(
    narration_path: str | os.PathLike | None = None,
    music_path: str | os.PathLike | None = None,
    output_path: str | os.PathLike | None = None,
    ducking_db: float = -18.0,
) -> str:
    """Duck background music below narration using sidechain compression (-18dB, 350ms release)."""
    if not _looks_like_real_input(narration_path):
        return str(output_path) if output_path and Path(output_path).exists() else str(narration_path or "")
    if not _looks_like_real_input(music_path):
        return str(narration_path)
    out_target = str(output_path or narration_path)
    Path(out_target).parent.mkdir(parents=True, exist_ok=True)

    use_tmp = False
    try:
        out_res = Path(out_target).resolve()
        if Path(narration_path).resolve() == out_res or Path(music_path).resolve() == out_res:
            use_tmp = True
    except Exception:
        use_tmp = (str(narration_path) == str(out_target) or str(music_path) == str(out_target))

    out_cmd = out_target + ".tmp.duck.wav" if use_tmp else out_target

    # threshold derived from ducking_db (linear gain target)
    threshold = max(0.001, 10 ** (max(ducking_db, -60) / 20))
    filtergraph = (
        "[1:a]aresample=48000,volume=1[music_in];"
        "[0:a]aresample=48000[speech];"
        f"[music_in][speech]sidechaincompress=threshold={threshold:.4f}:ratio=8:attack=20:release=350:makeup=1[ducked];"
        "[speech][ducked]amix=inputs=2:duration=first:normalize=0[aout]"
    )
    try:
        try:
            _ffmpeg_run(
                ["ffmpeg", "-y", "-i", str(narration_path), "-stream_loop", "-1", "-i", str(music_path),
                 "-filter_complex", filtergraph, "-map", "[aout]", "-ar", "48000", "-ac", "2", out_cmd],
                check=True,
            )
        except Exception as exc:
            logger.error("FFmpeg sidechain ducking failed: %s", exc, exc_info=True)
            raise FFmpegExecutionError(
                f"Sidechain ducking failed for narration '{narration_path}' and music '{music_path}': {exc}"
            ) from exc

        if not _looks_like_real_input(out_cmd):
            logger.error("Output audio artifact %s missing or empty after ducking", out_cmd)
            raise AudioProcessingError(f"Output audio artifact {out_cmd} is missing or empty after sidechain ducking")

        if use_tmp:
            os.replace(out_cmd, out_target)
    finally:
        if use_tmp and os.path.exists(out_cmd):
            try:
                os.remove(out_cmd)
            except OSError:
                pass

    return out_target


def master_audio_track(
    narration_path: str | os.PathLike | None = None,
    music_path: str | os.PathLike | None = None,
    output_path: str | os.PathLike | None = None,
    target_lufs: float = -14.0,
    ducking_db: float = -18.0,
    lowpass_freq: float = 12000.0,
) -> str:
    """Full mastering chain: duck music under narration, then loudness normalize to -14 LUFS."""
    if not _looks_like_real_input(narration_path):
        return str(output_path or narration_path or "")
    out = str(output_path or narration_path)
    ducked = apply_sidechain_ducking(
        narration_path=narration_path,
        music_path=music_path,
        output_path=out,
        ducking_db=ducking_db,
    )
    if ducked and Path(ducked).exists():
        return normalize_narration_lufs(
            input_path=ducked,
            output_path=out,
            target_lufs=target_lufs,
            apply_lowpass=bool(lowpass_freq and lowpass_freq > 0),
            lowpass_freq=lowpass_freq or 12000.0,
        )
    return out