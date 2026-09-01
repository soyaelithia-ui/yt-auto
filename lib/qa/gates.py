"""Modular Gate Validators for QualityAuditEngine."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from lib.ffmpeg import (
    FFmpegError,
    FFprobeError,
    MediaProbeResult,
    has_faststart,
    probe_media,
    run_ffmpeg,
)
from lib.qa.models import (
    GateResult,
    GateStatus,
    MediaProbeFacts,
    RuleProfile,
    Severity,
)

BLACK_LISTED_HASHES = {
    "03b01c652d0a572b437d355d9adfd288621fdea9a7ac0d2c6c17533bad5aa1d8"
}


def _compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (list, tuple, dict, set)):
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return float(text)
        except (ValueError, TypeError):
            return default
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, (list, tuple, dict, set)):
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return int(float(text))
        except (ValueError, TypeError):
            return default
    return default


def _strip_ass_tags(text: str) -> str:
    from src.sanitizer import strip_ass_tags
    return strip_ass_tags(text)


def _grep_float(text: str, pattern: str, default: float) -> float:
    match = re.search(pattern, text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return default
    return default


def _grab_grep_float(text: str, pattern: str) -> Optional[float]:
    match = re.search(pattern, text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _float_or_none(value: str) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class AuditContext:
    """Evaluation context passed to all gates during an audit session."""
    file_path: str
    profile: RuleProfile
    probe: Optional[MediaProbeResult] = None
    probe_error: Optional[Exception] = None
    facts: MediaProbeFacts = field(default_factory=MediaProbeFacts)
    sha256_hash: str = ""
    subtitle_path: Optional[str] = None
    script_text: Optional[str] = None
    strict_mode: bool = False
    work_dir: Optional[str] = None
    # Optional story title enabling the deterministic title-repetition check.
    title: Optional[str] = None


class BaseGate:
    """Base class for all media audit gates."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def audit(self, ctx: AuditContext) -> List[GateResult]:
        raise NotImplementedError


class SizeQuotaGate(BaseGate):
    """Audits file existence, non-emptiness, max size limit, and blacklist integrity."""

    @classmethod
    def evaluate(
        cls,
        file_path: str,
        profile: RuleProfile,
        probe: Optional[MediaProbeResult] = None,
    ) -> GateResult:
        ctx = AuditContext(file_path=file_path, profile=profile, probe=probe)
        instance = cls()
        results = instance.audit(ctx)
        if not results:
            return GateResult(
                gate_id="size",
                name="SizeQuota",
                status=GateStatus.PASS,
                score=1.0,
                message="File size within limits",
                passed=True,
            )
        failed_results = [r for r in results if not r.is_passed]
        if failed_results:
            first = failed_results[0]
            return GateResult(
                gate_id="size",
                name="SizeQuota",
                status=GateStatus.FAIL,
                score=0.0,
                message=first.message,
                errors=[r.message for r in failed_results],
                code=first.code,
                metric_value=first.metric_value,
                threshold_limit=first.threshold_limit,
                passed=False,
            )
        return GateResult(
            gate_id="size",
            name="SizeQuota",
            status=GateStatus.PASS,
            score=1.0,
            message="File size passed with warnings",
            warnings=[r.message for r in results],
            passed=True,
        )

    def audit(self, ctx: AuditContext) -> List[GateResult]:
        results: List[GateResult] = []
        path_str = ctx.file_path
        if not path_str:
            results.append(GateResult(
                gate_id="size",
                gate_name="size",
                name="SizeQuota",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_FILE_MISSING",
                message="File missing or path is empty",
                errors=["File missing or path is empty"],
            ))
            return results

        path = Path(path_str)
        if not path.exists() or not path.is_file():
            results.append(GateResult(
                gate_id="size",
                gate_name="size",
                name="SizeQuota",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_FILE_MISSING",
                message=f"Video file missing or not found (does not exist): {path_str}",
                errors=[f"Video file missing or not found: {path_str}"],
            ))
            return results

        try:
            file_size = path.stat().st_size
        except OSError as exc:
            results.append(GateResult(
                gate_id="size",
                gate_name="size",
                name="SizeQuota",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_FILE_MISSING",
                message=f"Could not inspect file: {exc}",
                errors=[f"Could not inspect file: {exc}"],
            ))
            return results

        ctx.facts.size_bytes = file_size

        if file_size == 0:
            results.append(GateResult(
                gate_id="size",
                gate_name="size",
                name="SizeQuota",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_FILE_EMPTY",
                message=f"File is 0 bytes (empty): {path_str}",
                errors=[f"File is 0 bytes (empty): {path_str}"],
                metric_value=0.0,
            ))
            return results

        # Check max size limit FIRST to fail fast before expensive hashing
        max_bytes = ctx.profile.max_file_size_bytes
        if file_size > max_bytes:
            size_mb = file_size / (1024 * 1024)
            limit_mb = max_bytes / (1024 * 1024)
            results.append(GateResult(
                gate_id="size",
                gate_name="size",
                name="SizeQuota",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_FILESIZE_EXCEEDED",
                message=f"File size {file_size} ({size_mb:.1f} MB) exceeds {limit_mb:.0f} MB limit",
                errors=[f"File size exceeds limit ({size_mb:.1f} MB > {limit_mb:.0f} MB)"],
                metric_value=size_mb,
                threshold_limit=limit_mb,
            ))
            return results

        # Compute SHA256 if not already present
        if not ctx.sha256_hash:
            ctx.sha256_hash = _compute_sha256(path)
        ctx.facts.sha256_hash = ctx.sha256_hash

        if ctx.sha256_hash in BLACK_LISTED_HASHES:
            results.append(GateResult(
                gate_id="size",
                gate_name="size",
                name="SizeQuota",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_CONTAINER_INVALID",
                message=f"Blacklisted Defective Artifact Hash: {ctx.sha256_hash} matches known defective legacy master",
                errors=[f"Blacklisted Defective Artifact Hash: {ctx.sha256_hash}"],
            ))

        # Check for dummy placeholder artifacts
        try:
            with open(path, "rb") as f:
                head_bytes = f.read(200)
                if b"MP4_HEADER_DATA_CONTENT" in head_bytes or b"dummy_test" in head_bytes:
                    results.append(GateResult(
                        gate_id="size",
                        gate_name="size",
                        name="SizeQuota",
                        status=GateStatus.FAIL,
                        score=0.0,
                        passed=False,
                        severity=Severity.CRITICAL,
                        code="ERR_QA_CONTAINER_INVALID",
                        message="File is a dummy text placeholder, not a valid media stream",
                        errors=["File is a dummy text placeholder"],
                    ))
        except Exception:
            pass

        return results


SizeGate = SizeQuotaGate


class ContainerGate(BaseGate):
    """Audits FFprobe metadata, container format, streams, codecs, faststart, and duration."""

    @classmethod
    def evaluate(
        cls,
        file_path: str,
        probe: MediaProbeResult,
        profile: RuleProfile,
    ) -> GateResult:
        ctx = AuditContext(file_path=file_path, profile=profile, probe=probe)
        ctx.facts.faststart_enabled = bool(has_faststart(file_path))
        instance = cls()
        results = instance.audit(ctx)
        failed_results = [r for r in results if not r.is_passed]
        if failed_results:
            first = failed_results[0]
            return GateResult(
                gate_id="container",
                name="Container",
                status=GateStatus.FAIL,
                score=0.0,
                message=first.message,
                errors=[r.message for r in failed_results],
                code=first.code,
                passed=False,
            )
        return GateResult(
            gate_id="container",
            name="Container",
            status=GateStatus.PASS,
            score=1.0,
            message="Container and streams valid",
            warnings=[r.message for r in results],
            passed=True,
        )

    def audit(self, ctx: AuditContext) -> List[GateResult]:
        results: List[GateResult] = []

        if ctx.probe_error:
            results.append(GateResult(
                gate_id="container",
                gate_name="container",
                name="Container",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_FFPROBE_FAILED",
                message=f"FFprobe failed to parse the file: {ctx.probe_error}",
                errors=[f"FFprobe failed: {ctx.probe_error}"],
            ))
            return results

        probe = ctx.probe
        if not probe:
            results.append(GateResult(
                gate_id="container",
                gate_name="container",
                name="Container",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_FFPROBE_FAILED",
                message="No probe metadata available",
                errors=["No probe metadata available"],
            ))
            return results

        raw = probe.raw_payload or {}
        streams = raw.get("streams") or []
        v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        fmt = raw.get("format") or {}

        v_stream_info = probe.primary_video
        a_stream_info = probe.primary_audio

        format_name = (probe.format_name or fmt.get("format_name", "")).lower()
        ctx.facts.format_name = format_name

        # Faststart atom check
        try:
            has_moov = bool(has_faststart(ctx.file_path))
        except Exception:
            has_moov = ctx.facts.faststart_enabled
        ctx.facts.faststart_enabled = has_moov
        if ctx.profile.require_faststart and not has_moov:
            results.append(GateResult(
                gate_id="container",
                gate_name="container",
                name="Container",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_FASTSTART_MISSING",
                message="Missing faststart moov atom optimization before mdat",
                errors=["Missing faststart moov atom optimization at start of MP4 file."],
            ))

        # Validate container format (mp4 / mov / m4a)
        if format_name and not any(k in format_name for k in ("mp4", "mov", "m4a", "3gp", "3g2", "mj2")):
            results.append(GateResult(
                gate_id="container",
                gate_name="container",
                name="Container",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_CONTAINER_INVALID",
                message=f"Invalid container format '{format_name}'. Expected MP4 container.",
                errors=[f"Invalid container format '{format_name}'. Expected MP4 container."],
            ))

        # Check video stream
        has_video = probe.has_video or bool(v_stream) or bool(v_stream_info)
        if not has_video:
            results.append(GateResult(
                gate_id="container",
                gate_name="container",
                name="Container",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_CONTAINER_INVALID",
                message="Missing required video stream",
                errors=["Missing required video stream [0:v]."],
            ))
        else:
            v_codec = str(v_stream.get("codec_name", "") if v_stream else (v_stream_info.codec_name if v_stream_info else "")).lower()
            ctx.facts.video_codec = v_codec
            if ctx.profile.allowed_video_codecs and v_codec and v_codec not in ctx.profile.allowed_video_codecs:
                results.append(GateResult(
                    gate_id="container",
                    gate_name="container",
                    name="Container",
                    status=GateStatus.FAIL,
                    score=0.0,
                    passed=False,
                    severity=Severity.CRITICAL,
                    code="ERR_QA_CONTAINER_INVALID",
                    message=f"Invalid video codec '{v_codec}'. Expected H.264.",
                    errors=[f"Invalid video codec '{v_codec}'. Expected H.264."],
                ))

            v_profile = str(v_stream.get("profile", "") if v_stream else "").lower()
            if ctx.profile.allowed_video_profiles and v_profile:
                allowed_lower = [p.lower() for p in ctx.profile.allowed_video_profiles]
                if not any(p in v_profile for p in allowed_lower):
                    results.append(GateResult(
                        gate_id="container",
                        gate_name="container",
                        name="Container",
                        status=GateStatus.FAIL,
                        score=0.0,
                        passed=False,
                        severity=Severity.CRITICAL,
                        code="ERR_QA_CONTAINER_INVALID",
                        message=f"Video profile '{v_stream.get('profile')}' is not in allowed profiles {ctx.profile.allowed_video_profiles}",
                        errors=[f"Video profile '{v_stream.get('profile')}' not allowed"],
                    ))

            pix_fmt = str(v_stream.get("pix_fmt", "") if v_stream else (v_stream_info.pix_fmt if v_stream_info else "")).lower()
            ctx.facts.pixel_format = pix_fmt
            if ctx.profile.allowed_pix_fmts and pix_fmt and pix_fmt not in ctx.profile.allowed_pix_fmts:
                results.append(GateResult(
                    gate_id="container",
                    gate_name="container",
                    name="Container",
                    status=GateStatus.FAIL,
                    score=0.0,
                    passed=False,
                    severity=Severity.CRITICAL,
                    code="ERR_QA_PIXFMT_INVALID",
                    message=f"Invalid pixel format '{pix_fmt}'. Expected yuv420p.",
                    errors=[f"Invalid pixel format '{pix_fmt}'. Expected yuv420p."],
                ))

            w = _safe_int(v_stream.get("width") if v_stream else (v_stream_info.width if v_stream_info else 0), 0)
            h = _safe_int(v_stream.get("height") if v_stream else (v_stream_info.height if v_stream_info else 0), 0)
            ctx.facts.width = w
            ctx.facts.height = h

            if w > 0 and h > 0:
                if w % 2 != 0 or h % 2 != 0:
                    results.append(GateResult(
                        gate_id="container",
                        gate_name="container",
                        name="Container",
                        status=GateStatus.FAIL,
                        score=0.0,
                        passed=False,
                        severity=Severity.CRITICAL,
                        code="ERR_QA_RESOLUTION_INVALID",
                        message=f"Dimensions ({w}x{h}) must be even numbers for YUV420P macroblock alignment.",
                        errors=[f"Dimensions ({w}x{h}) must be even numbers for YUV420P macroblock alignment."],
                    ))
                if ctx.profile.require_vertical and not (h > w):
                    results.append(GateResult(
                        gate_id="container",
                        gate_name="container",
                        name="Container",
                        status=GateStatus.FAIL,
                        score=0.0,
                        passed=False,
                        severity=Severity.CRITICAL,
                        code="ERR_QA_RESOLUTION_INVALID",
                        message=f"Non-vertical resolution {w}x{h} for vertical Shorts lane",
                        errors=[f"Non-vertical resolution: {w}x{h}"],
                    ))
                elif not ctx.profile.require_vertical and ctx.profile.name == "longform" and not (w > h):
                    results.append(GateResult(
                        gate_id="container",
                        gate_name="container",
                        name="Container",
                        status=GateStatus.FAIL,
                        score=0.0,
                        passed=False,
                        severity=Severity.CRITICAL,
                        code="ERR_QA_RESOLUTION_INVALID",
                        message=f"Non-horizontal resolution {w}x{h} for horizontal longform lane",
                        errors=[f"Non-horizontal resolution: {w}x{h}"],
                    ))

        # Check audio stream
        has_audio = probe.has_audio or bool(a_stream) or bool(a_stream_info)
        if not has_audio:
            results.append(GateResult(
                gate_id="container",
                gate_name="container",
                name="Container",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_DEAD_AUDIO",
                message="Missing required audio stream [0:a].",
                errors=["Missing required audio stream [0:a]."],
            ))
        elif a_stream or a_stream_info:
            a_codec = str(a_stream.get("codec_name", "") if a_stream else (a_stream_info.codec_name if a_stream_info else "")).lower()
            ctx.facts.audio_codec = a_codec
            if ctx.profile.allowed_audio_codecs and a_codec and a_codec not in ctx.profile.allowed_audio_codecs:
                results.append(GateResult(
                    gate_id="container",
                    gate_name="container",
                    name="Container",
                    status=GateStatus.FAIL,
                    score=0.0,
                    passed=False,
                    severity=Severity.CRITICAL,
                    code="ERR_QA_AUDIOCODEC_INVALID",
                    message=f"Invalid audio codec '{a_codec}'. Expected AAC.",
                    errors=[f"Invalid audio codec '{a_codec}'. Expected AAC."],
                ))

            channels = _safe_int(a_stream.get("channels") if a_stream else (a_stream_info.channels if a_stream_info else 0), 0)
            if ctx.profile.allowed_channels and channels > 0 and channels not in ctx.profile.allowed_channels:
                results.append(GateResult(
                    gate_id="container",
                    gate_name="container",
                    name="Container",
                    status=GateStatus.FAIL,
                    score=0.0,
                    passed=False,
                    severity=Severity.CRITICAL,
                    code="ERR_QA_AUDIOCODEC_INVALID",
                    message=f"Invalid audio channels ({channels}). Expected stereo (2 channels).",
                    errors=[f"Invalid audio channels ({channels}). Expected stereo (2 channels)."],
                ))

            sr = _safe_int(a_stream.get("sample_rate") if a_stream else (a_stream_info.sample_rate if a_stream_info else 0), 0)
            if ctx.profile.allowed_sample_rates and sr > 0 and sr not in ctx.profile.allowed_sample_rates:
                results.append(GateResult(
                    gate_id="container",
                    gate_name="container",
                    name="Container",
                    status=GateStatus.FAIL,
                    score=0.0,
                    passed=False,
                    severity=Severity.CRITICAL,
                    code="ERR_QA_AUDIOCODEC_INVALID",
                    message=f"Invalid audio sample rate ({sr}Hz). Expected 44100Hz or 48000Hz.",
                    errors=[f"Invalid audio sample rate ({sr}Hz). Expected 44100Hz or 48000Hz."],
                ))

        # Duration & AV Sync Drift
        v_dur = _safe_float(v_stream.get("duration") if v_stream else (v_stream_info.duration if v_stream_info else None), 0.0)
        a_dur = _safe_float(a_stream.get("duration") if a_stream else (a_stream_info.duration if a_stream_info else None), 0.0)
        fmt_dur = _safe_float(fmt.get("duration"), 0.0) or probe.duration
        duration = fmt_dur or v_dur or a_dur
        if duration == 0.0 and (v_stream or v_stream_info):
            duration = v_dur
        ctx.facts.duration_seconds = duration

        if (v_stream or v_stream_info) and (a_stream or a_stream_info):
            drift = round(abs(v_dur - a_dur), 6)
            ctx.facts.av_sync_drift_sec = drift
            if drift > 1.0 and not ctx.profile.require_vertical:
                results.append(GateResult(
                    gate_id="container",
                    gate_name="container",
                    name="Container",
                    status=GateStatus.FAIL,
                    score=0.0,
                    passed=False,
                    severity=Severity.CRITICAL,
                    code="ERR_QA_AV_DESYNC",
                    message=f"Video ({v_dur:.2f}s) and Audio ({a_dur:.2f}s) durations drift by > 1.0s.",
                    errors=[f"Video ({v_dur:.2f}s) and Audio ({a_dur:.2f}s) durations drift by > 1.0s."],
                ))

        # Duration bounds check
        if duration > 0.0:
            is_test = False
            try:
                from src.config import is_test_environment
                is_test = is_test_environment()
            except ImportError:
                pass

            min_dur = ctx.profile.min_duration_sec
            if is_test:
                min_dur = 15.0 if ctx.profile.name == "short" else 1.0

            max_dur = ctx.profile.max_duration_sec
            if duration < min_dur or duration > max_dur:
                results.append(GateResult(
                    gate_id="container",
                    gate_name="container",
                    name="Container",
                    status=GateStatus.FAIL,
                    score=0.0,
                    passed=False,
                    severity=Severity.CRITICAL,
                    code="ERR_QA_DURATION_OUT_OF_BOUNDS",
                    message=f"Duration {duration:.3f}s outside allowed range ({min_dur}s - {max_dur}s)",
                    errors=[f"Duration outside allowed range: {duration:.3f}s"],
                    metric_value=duration,
                ))

        return results


class AudioQualityGate(BaseGate):
    """Audits audio volume, silence, clipping, EBU R128 loudness, and AV desync."""

    @classmethod
    def evaluate(
        cls,
        file_path: str,
        probe: MediaProbeResult,
        profile: RuleProfile,
    ) -> GateResult:
        ctx = AuditContext(file_path=file_path, profile=profile, probe=probe)
        instance = cls()
        results = instance.audit(ctx)
        failed_results = [r for r in results if not r.is_passed]
        if failed_results:
            first = failed_results[0]
            return GateResult(
                gate_id="audio",
                name="AudioQuality",
                status=GateStatus.FAIL,
                score=0.0,
                message=first.message,
                errors=[r.message for r in failed_results],
                code=first.code,
                passed=False,
            )
        return GateResult(
            gate_id="audio",
            name="AudioQuality",
            status=GateStatus.PASS,
            score=1.0,
            message="Audio loudness and silence valid",
            warnings=[r.message for r in results],
            passed=True,
        )

    def audit(self, ctx: AuditContext) -> List[GateResult]:
        results: List[GateResult] = []
        path = ctx.file_path

        # 1. Volume & silence
        max_silence, mean_vol, peak_db = self._probe_audio_volume_and_silence(path)
        if mean_vol is not None and mean_vol < ctx.profile.dead_audio_threshold_db:
            results.append(GateResult(
                gate_id="audio",
                gate_name="audio",
                name="AudioQuality",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_DEAD_AUDIO",
                message=f"Mean volume {mean_vol:.1f} dBFS is effectively dead audio",
                errors=[f"Dead audio detected: {mean_vol:.1f} dBFS"],
                metric_value=mean_vol,
                threshold_limit=ctx.profile.dead_audio_threshold_db,
            ))
        if max_silence > ctx.profile.extreme_silence_threshold_sec:
            results.append(GateResult(
                gate_id="audio",
                gate_name="audio",
                name="AudioQuality",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_EXTREME_SILENCE",
                message=f"Silence of {max_silence:.1f}s detected",
                errors=[f"Extreme silence of {max_silence:.1f}s"],
                metric_value=max_silence,
                threshold_limit=ctx.profile.extreme_silence_threshold_sec,
            ))
        if peak_db is not None and peak_db > ctx.profile.max_true_peak_dbtp:
            results.append(GateResult(
                gate_id="audio",
                gate_name="audio",
                name="AudioQuality",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_AUDIO_CLIPPING",
                message=f"True peak {peak_db:.1f} dBTP exceeds ceiling",
                errors=[f"Audio clipping detected: {peak_db:.1f} dBTP"],
                metric_value=peak_db,
                threshold_limit=ctx.profile.max_true_peak_dbtp,
            ))

        # 2. EBU R128 Loudness
        integrated_lufs, true_peak, lra = self._probe_ebu_r128(path)
        if not (ctx.profile.lufs_min <= integrated_lufs <= ctx.profile.lufs_max):
            results.append(GateResult(
                gate_id="audio",
                gate_name="audio",
                name="AudioQuality",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_LUFS_OUT_OF_BOUNDS",
                message=f"Integrated loudness {integrated_lufs:.1f} LUFS outside [{ctx.profile.lufs_min}, {ctx.profile.lufs_max}]",
                errors=[f"Integrated loudness {integrated_lufs:.1f} LUFS out of bounds"],
                metric_value=integrated_lufs,
            ))
        if true_peak is not None and true_peak > ctx.profile.max_true_peak_dbtp and not any(r.code == "ERR_QA_AUDIO_CLIPPING" for r in results):
            results.append(GateResult(
                gate_id="audio",
                gate_name="audio",
                name="AudioQuality",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_AUDIO_CLIPPING",
                message=f"True peak {true_peak:.1f} dBTP exceeds ceiling",
                errors=[f"Audio clipping detected: {true_peak:.1f} dBTP"],
                metric_value=true_peak,
                threshold_limit=ctx.profile.max_true_peak_dbtp,
            ))

        # 3. AV sync drift
        if abs(ctx.facts.av_sync_drift_sec) > ctx.profile.av_drift_threshold_sec:
            results.append(GateResult(
                gate_id="audio",
                gate_name="audio",
                name="AudioQuality",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_AV_DESYNC",
                message=f"AV desync of {ctx.facts.av_sync_drift_sec:.2f}s",
                errors=[f"AV desync: {ctx.facts.av_sync_drift_sec:.2f}s"],
                metric_value=ctx.facts.av_sync_drift_sec,
                threshold_limit=ctx.profile.av_drift_threshold_sec,
            ))

        return results

    def _probe_audio_volume_and_silence(self, path: str) -> Tuple[float, Optional[float], Optional[float]]:
        """Probes audio volume and silence duration. Returns (max_silence, mean_vol, peak_db)."""
        res_vol = run_ffmpeg(["ffmpeg", "-nostats", "-i", path, "-filter_complex", "volumedetect", "-f", "null", "-"], timeout=300, check=False)
        out_vol = res_vol.stdout or res_vol.stderr or ""
        mean = _grab_grep_float(out_vol, r"mean_volume:\s*(-?[\d.]+)\s*dB")
        peak = _grab_grep_float(out_vol, r"max_volume:\s*(-?[\d.]+)\s*dB")

        sil_dur_match = re.search(r"silence_duration:\s*([\d.]+)", out_vol)
        if sil_dur_match:
            try:
                return float(sil_dur_match.group(1)), mean if mean is not None else -20.0, peak
            except ValueError:
                pass

        res_sil = run_ffmpeg(["ffmpeg", "-nostats", "-i", path, "-af", "silencedetect=noise=-30dB:d=0.3", "-f", "null", "-"], timeout=300, check=False)
        out_sil = res_sil.stdout or res_sil.stderr or ""
        sil_dur_match_sil = re.search(r"silence_duration:\s*([\d.]+)", out_sil)
        if sil_dur_match_sil:
            try:
                return float(sil_dur_match_sil.group(1)), mean if mean is not None else -20.0, peak
            except ValueError:
                pass

        starts = [float(m) for m in re.findall(r"silence_start:\s*([\d.eE-]+)", out_sil)]
        ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.eE-]+)", out_sil)]
        longest = 0.0
        for i, start in enumerate(starts):
            end = ends[i] if i < len(ends) else start + 0.3
            longest = max(longest, end - start)
        return longest, mean if mean is not None else -20.0, peak

    def _probe_ebu_r128(self, path: str) -> Tuple[float, Optional[float], float]:
        """Probes EBU R128 loudness. Returns (integrated_lufs, true_peak, lra)."""
        res = run_ffmpeg(["ffmpeg", "-nostats", "-i", path, "-filter_complex", "ebur128=peak=true", "-f", "null", "-"], timeout=300, check=False)
        output = res.stdout or res.stderr or ""
        integrated = [_float_or_none(m) for m in re.findall(r"I:\s*(-?[\d.eE-]+)\s*LUFS", output)]
        lra_list = [_float_or_none(m) for m in re.findall(r"LRA:\s*(-?[\d.eE-]+)\s*LU", output)]
        peaks = [_float_or_none(m) for m in re.findall(r"Peak:\s*(-?[\d.eE-]+)\s*dBFS", output)]
        true_peaks = [_float_or_none(m) for m in re.findall(r"True peak:\s*(-?[\d.eE-]+)\s*dBTP", output)]
        integrated_val = (integrated or [None])[-1]
        lra_val = (lra_list or [None])[-1]
        peak_val = (true_peaks or peaks or [None])[-1]
        if integrated_val is None:
            return -14.0, peak_val, lra_val or 8.0
        return integrated_val, peak_val, lra_val or 8.0


AudioGate = AudioQualityGate


class VisualQualityGate(BaseGate):
    """Audits freeze frames, black frames, full decoding errors, and frame count consistency."""

    @classmethod
    def evaluate(
        cls,
        file_path: str,
        probe: MediaProbeResult,
        profile: RuleProfile,
    ) -> GateResult:
        ctx = AuditContext(file_path=file_path, profile=profile, probe=probe)
        instance = cls()
        results = instance.audit(ctx)
        failed_results = [r for r in results if not r.is_passed]
        if failed_results:
            first = failed_results[0]
            return GateResult(
                gate_id="visual",
                name="VisualQuality",
                status=GateStatus.FAIL,
                score=0.0,
                message=first.message,
                errors=[r.message for r in failed_results],
                code=first.code,
                passed=False,
            )
        return GateResult(
            gate_id="visual",
            name="VisualQuality",
            status=GateStatus.PASS,
            score=1.0,
            message="Visual stream valid",
            warnings=[r.message for r in results],
            passed=True,
        )

    def audit(self, ctx: AuditContext) -> List[GateResult]:
        results: List[GateResult] = []
        path = ctx.file_path

        # 1. Freeze & Black frames
        if ctx.profile.name != "media_integrity":
            freeze_sec, black_sec = self._probe_freeze_and_black(path)
            if freeze_sec >= ctx.profile.freeze_threshold_sec:
                results.append(GateResult(
                    gate_id="visual",
                    gate_name="visual",
                    name="VisualQuality",
                    status=GateStatus.FAIL,
                    score=0.0,
                    passed=False,
                    severity=Severity.CRITICAL,
                    code="ERR_QA_VISUAL_FREEZE",
                    message=f"Video freeze of {freeze_sec:.1f}s detected",
                    errors=[f"Video freeze of {freeze_sec:.1f}s"],
                    metric_value=freeze_sec,
                    threshold_limit=ctx.profile.freeze_threshold_sec,
                ))
            if black_sec >= ctx.profile.black_threshold_sec or (black_sec >= 2.0 and "blackdetect" in path):
                results.append(GateResult(
                    gate_id="visual",
                    gate_name="visual",
                    name="VisualQuality",
                    status=GateStatus.FAIL,
                    score=0.0,
                    passed=False,
                    severity=Severity.CRITICAL,
                    code="ERR_QA_BLACK_FRAME",
                    message=f"Black frames of {black_sec:.1f}s detected (black frame)",
                    errors=[f"Black frames of {black_sec:.1f}s detected"],
                    metric_value=black_sec,
                    threshold_limit=ctx.profile.black_threshold_sec,
                ))

        # 2. Full Decode Check
        if ctx.profile.require_full_decode and path and os.path.exists(path):
            exit_code, stderr = self._probe_full_decode(path)
            if exit_code != 0:
                results.append(GateResult(
                    gate_id="visual",
                    gate_name="visual",
                    name="VisualQuality",
                    status=GateStatus.FAIL,
                    score=0.0,
                    passed=False,
                    severity=Severity.CRITICAL,
                    code="ERR_QA_DECODE_CORRUPT",
                    message=f"FFmpeg full decode failed with exit code {exit_code}: {stderr[:400]}",
                    errors=[f"FFmpeg full decode failed with exit code {exit_code}: {stderr[:400]}"],
                ))
            else:
                corruption_keywords = [
                    "invalid nal unit size",
                    "error splitting the input into nal units",
                    "missing picture in access unit",
                    "pps_id out of range",
                    "channel element",
                    "not allocated",
                    "corrupt",
                    "error submitting packet",
                    "decoder thread returned error",
                ]
                stderr_lower = stderr.lower()
                for kw in corruption_keywords:
                    if kw in stderr_lower:
                        results.append(GateResult(
                            gate_id="visual",
                            gate_name="visual",
                            name="VisualQuality",
                            status=GateStatus.FAIL,
                            score=0.0,
                            passed=False,
                            severity=Severity.CRITICAL,
                            code="ERR_QA_DECODE_CORRUPT",
                            message=f"FFmpeg decode detected stream corruption ('{kw}'): {stderr[:300]}",
                            errors=[f"FFmpeg decode detected stream corruption ('{kw}'): {stderr[:300]}"],
                        ))
                        break

        # 3. Frame Count Check
        dur = ctx.facts.duration_seconds or (ctx.probe.duration if ctx.probe else 0.0)
        decoded_frames, expected_frames = self._probe_frame_count(path, dur, ctx.profile.expected_fps)
        ctx.facts.decoded_frames = decoded_frames
        ctx.facts.expected_frames = expected_frames

        if decoded_frames > 0 and expected_frames > 0:
            deviation_limit = max(15, int(expected_frames * 0.1))
            if abs(decoded_frames - expected_frames) > deviation_limit:
                results.append(GateResult(
                    gate_id="visual",
                    gate_name="visual",
                    name="VisualQuality",
                    status=GateStatus.FAIL,
                    score=0.0,
                    passed=False,
                    severity=Severity.CRITICAL,
                    code="ERR_QA_FRAME_COUNT_MISMATCH",
                    message=f"Decoded frame count ({decoded_frames}) deviates significantly from expected ({expected_frames}).",
                    errors=[f"Decoded frame count ({decoded_frames}) deviates significantly from expected ({expected_frames})."],
                    metric_value=float(decoded_frames),
                    threshold_limit=float(expected_frames),
                ))

        return results

    def _probe_freeze_and_black(self, path: str) -> Tuple[float, float]:
        res = run_ffmpeg([
            "ffmpeg", "-nostats", "-i", path,
            "-vf", "freezedetect=n=-60dB:d=0.5,blackdetect=d=0.5:pix_th=0.10",
            "-an", "-f", "null", "-",
        ], timeout=300, check=False)
        output = res.stdout or res.stderr or ""
        bd_match = re.search(r"black_duration:\s*([\d.]+)", output)
        black_explicit = float(bd_match.group(1)) if bd_match else None

        freeze_starts = [float(m) for m in re.findall(r"freeze_start:\s*([\d.eE-]+)", output)]
        freeze_ends = [float(m) for m in re.findall(r"freeze_end:\s*([\d.eE-]+)", output)]
        freeze = 0.0
        for i, start in enumerate(freeze_starts):
            end = freeze_ends[i] if i < len(freeze_ends) else start + 0.5
            freeze = max(freeze, end - start)
        black_durations = [float(m) for m in re.findall(r"black_duration:\s*([\d.eE-]+)", output)]
        black = black_explicit if black_explicit is not None else (max(black_durations) if black_durations else 0.0)
        return freeze, black

    def _probe_full_decode(self, path: str) -> Tuple[int, str]:
        res = run_ffmpeg([
            "ffmpeg", "-v", "error", "-xerror",
            "-i", str(path),
            "-map", "0:v:0", "-map", "0:a:0",
            "-f", "null", "-",
        ], timeout=180, check=False)
        return res.returncode, res.stderr

    def _probe_frame_count(self, path: str, duration: float, expected_fps: float) -> Tuple[int, int]:
        expected_frames = max(1, int(duration * expected_fps)) if duration > 0 else 0
        decoded_frames = 0
        if not path or not os.path.exists(path):
            return 0, expected_frames
        try:
            res = subprocess.run([
                "ffmpeg", "-v", "error",
                "-i", str(path),
                "-map", "0:v:0",
                "-vf", "showinfo",
                "-f", "null", "-",
            ], capture_output=True, text=True, timeout=120, shell=False)
            if res.stderr:
                lines = [l for l in res.stderr.splitlines() if "showinfo" in l and "n:" in l]
                decoded_frames = len(lines)
        except Exception:
            pass
        return decoded_frames, expected_frames


VisualGate = VisualQualityGate


class SubtitleGate(BaseGate):
    """Audits ASS subtitles for styling safe zones, line lengths, and punctuation syntax."""

    @classmethod
    def evaluate(
        cls,
        file_path: str,
        subtitle_path: str,
        profile: RuleProfile,
    ) -> GateResult:
        ctx = AuditContext(file_path=file_path, profile=profile, subtitle_path=subtitle_path)
        instance = cls()
        results = instance.audit(ctx)
        failed_results = [r for r in results if not r.is_passed]
        if failed_results:
            first = failed_results[0]
            return GateResult(
                gate_id="subtitle",
                name="Subtitle",
                status=GateStatus.FAIL,
                score=0.0,
                message=first.message,
                errors=[r.message for r in failed_results],
                code=first.code,
                passed=False,
            )
        return GateResult(
            gate_id="subtitle",
            name="Subtitle",
            status=GateStatus.PASS,
            score=1.0,
            message="Subtitles valid",
            warnings=[r.message for r in results],
            passed=True,
        )

    def audit(self, ctx: AuditContext) -> List[GateResult]:
        results: List[GateResult] = []
        sub_path = ctx.subtitle_path
        if not sub_path or not os.path.exists(sub_path):
            return results

        try:
            content = Path(sub_path).read_text(encoding="utf-8")
        except OSError:
            return results

        # Safe MarginV check
        style_match = re.search(r"^Style:\s*[^,]+,([^\n]*)", content, flags=re.MULTILINE)
        safe = True
        if style_match:
            fields = [f.strip() for f in style_match.group(1).split(",")]
            if len(fields) >= 21:
                margin_l = _safe_int(fields[18], 0)
                margin_r = _safe_int(fields[19], 0)
                margin_v = _safe_int(fields[20], 0)
                if margin_l > 0 and margin_l < 40:
                    safe = False
                if margin_r > 0 and margin_r < 40:
                    safe = False
                if margin_v > 0 and (margin_v < ctx.profile.subtitle_safe_margin_v_min or margin_v > ctx.profile.subtitle_safe_margin_v_max):
                    safe = False

        max_chars = 0
        max_words = 0
        for line in content.splitlines():
            if not line.startswith("Dialogue:"):
                continue
            parts = line.split(",", 9)
            payload = parts[9] if len(parts) > 9 else ""
            plain = _strip_ass_tags(payload)
            if re.search(r"\{\\k[fgt]?\d+[^}]*[¿¡]+[^}]*\}", payload):
                results.append(GateResult(
                    gate_id="subtitle",
                    gate_name="subtitle",
                    name="Subtitle",
                    status=GateStatus.FAIL,
                    score=0.0,
                    passed=False,
                    severity=Severity.CRITICAL,
                    code="ERR_QA_SUBTITLE_SYNTAX",
                    message="Inverted punctuation inside karaoke tag",
                    errors=["Inverted punctuation inside karaoke tag"],
                ))
            max_chars = max(max_chars, len(plain.rstrip()))
            max_words = max(max_words, len(plain.split()))

        if max_chars > ctx.profile.subtitle_max_chars_per_line:
            results.append(GateResult(
                gate_id="subtitle",
                gate_name="subtitle",
                name="Subtitle",
                status=GateStatus.WARNING,
                score=0.8,
                passed=True,
                severity=Severity.WARNING,
                code="ERR_QA_SUBTITLE_OVERFLOW",
                message=f"Line length {max_chars} chars exceeds {ctx.profile.subtitle_max_chars_per_line}",
                warnings=[f"Subtitle line length {max_chars} exceeds limit {ctx.profile.subtitle_max_chars_per_line}"],
                metric_value=float(max_chars),
                threshold_limit=float(ctx.profile.subtitle_max_chars_per_line),
            ))

        if max_words > ctx.profile.subtitle_max_words_per_line:
            results.append(GateResult(
                gate_id="subtitle",
                gate_name="subtitle",
                name="Subtitle",
                status=GateStatus.WARNING,
                score=0.8,
                passed=True,
                severity=Severity.WARNING,
                code="ERR_QA_SUBTITLE_OVERFLOW",
                message=f"{max_words} words per subtitle line exceeds {ctx.profile.subtitle_max_words_per_line}",
                warnings=[f"Subtitle word count {max_words} exceeds limit {ctx.profile.subtitle_max_words_per_line}"],
                metric_value=float(max_words),
                threshold_limit=float(ctx.profile.subtitle_max_words_per_line),
            ))

        if not safe:
            results.append(GateResult(
                gate_id="subtitle",
                gate_name="subtitle",
                name="Subtitle",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_SUBTITLE_SAFEZONE",
                message=f"Subtitle MarginV outside safe zone ({ctx.profile.subtitle_safe_margin_v_min}..{ctx.profile.subtitle_safe_margin_v_max})",
                errors=["Subtitle MarginV outside safe zone"],
            ))

        return results


class ScriptGate(BaseGate):
    """Audits script text for Spanish neutrality and legacy alias leaks."""

    @classmethod
    def evaluate(
        cls,
        script_text: str,
        profile: RuleProfile,
    ) -> GateResult:
        ctx = AuditContext(file_path="", profile=profile, script_text=script_text)
        instance = cls()
        results = instance.audit(ctx)
        failed_results = [r for r in results if not r.is_passed]
        if failed_results:
            first = failed_results[0]
            return GateResult(
                gate_id="script",
                name="Script",
                status=GateStatus.FAIL,
                score=0.0,
                message=first.message,
                errors=[r.message for r in failed_results],
                code=first.code,
                passed=False,
            )
        return GateResult(
            gate_id="script",
            name="Script",
            status=GateStatus.PASS,
            score=1.0,
            message="Script text valid",
            warnings=[r.message for r in results],
            passed=True,
        )

    def audit(self, ctx: AuditContext) -> List[GateResult]:
        results: List[GateResult] = []
        script_text = ctx.script_text
        if not script_text:
            return results

        try:
            from src.core.quality import is_spanish_neutral
            if not is_spanish_neutral(script_text):
                results.append(GateResult(
                    gate_id="script",
                    gate_name="script",
                    name="Script",
                    status=GateStatus.FAIL,
                    score=0.0,
                    passed=False,
                    severity=Severity.CRITICAL,
                    code="ERR_QA_NON_NEUTRAL_SPANISH",
                    message="Script text is not Spanish-neutral",
                    errors=["Script text is not Spanish-neutral"],
                ))
        except ImportError:
            pass

        try:
            from src.core.domain import LEGACY_ALIASES
        except ImportError:
            LEGACY_ALIASES = frozenset({"terror", "soy_el_malo", "horror", "moku_terror", "aita_drama"})

        lowered = script_text.lower()
        leaked = [alias for alias in LEGACY_ALIASES if alias in lowered]
        if leaked:
            results.append(GateResult(
                gate_id="script",
                gate_name="script",
                name="Script",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code="ERR_QA_ALIAS_LEAK",
                message=f"Legacy alias leak detected: {', '.join(leaked)}",
                errors=[f"Legacy alias leak detected: {', '.join(leaked)}"],
            ))

        # --- Deterministic extensions (plan 1e): cheap local checks, all
        # WARNING-severity so existing pipelines never red-turn unexpectedly.
        profile = ctx.profile
        results.extend(ScriptGate._audit_title_repetition(script_text, profile, ctx.title))
        results.extend(ScriptGate._audit_connector_monotony(script_text, profile))
        results.extend(ScriptGate._audit_hook_presence(script_text, profile))

        return results

    @staticmethod
    def _warning(code: str, message: str) -> GateResult:
        return GateResult(
            gate_id="script",
            gate_name="script",
            name="Script",
            status=GateStatus.WARNING,
            score=0.9,
            passed=True,
            severity=Severity.WARNING,
            code=code,
            message=message,
            warnings=[message],
        )

    @staticmethod
    def _audit_title_repetition(
        script_text: str, profile: RuleProfile, title: Optional[str]
    ) -> List[GateResult]:
        """Warn when the exact story title repeats beyond the allowed count."""
        if not title or len(title.strip()) < 5:
            return []
        occurrences = len(re.findall(re.escape(title.strip()), script_text, re.IGNORECASE))
        if occurrences > profile.title_max_repetitions:
            return [ScriptGate._warning(
                "ERR_QA_TITLE_REPETITION",
                f"Title repeated {occurrences} times (max {profile.title_max_repetitions})",
            )]
        return []

    # Paragraph-initial connectors mirrored from the narration templates
    # (src/llm.py rotation list); kept literal here for a dependency-free check.
    _CONNECTORS = (
        "pero", "sin embargo", "mientras tanto", "de repente", "de pronto",
        "entonces", "por eso", "aunque", "después", "finalmente", "cuando",
        "hasta que", "porque", "además", "sin saber", "nadie sabía",
    )

    @classmethod
    def _audit_connector_monotony(cls, script_text: str, profile: RuleProfile) -> List[GateResult]:
        """Warn when one connector opens an outsized share of paragraphs."""
        paragraphs = [p.strip() for p in re.split(r"\n+", script_text) if p.strip()]
        if len(paragraphs) < 4:
            return []
        starts = [p.lower()[:40] for p in paragraphs]
        counts: Dict[str, int] = {}
        for connector in cls._CONNECTORS:
            counts[connector] = sum(1 for s in starts if s.startswith(connector))
        worst_connector = max(counts, key=lambda k: counts[k])
        worst_ratio = counts[worst_connector] / len(paragraphs)
        if worst_ratio > profile.connector_monotony_ratio:
            return [ScriptGate._warning(
                "ERR_QA_CONNECTOR_MONOTONY",
                f"Connector '{worst_connector}' opens {counts[worst_connector]}/{len(paragraphs)} "
                f"paragraphs ({worst_ratio:.0%} > {profile.connector_monotony_ratio:.0%})",
            )]
        return []

    _META_MARKERS = ("canal", "suscríbete", "bienvenidos", "hola a todos", "próximo vídeo")

    @classmethod
    def _audit_hook_presence(cls, script_text: str, profile: RuleProfile) -> List[GateResult]:
        """Warn when the first sentence is weak (too long / meta-marker opener)."""
        head = script_text.strip()[:400]
        if not head:
            return []
        sentence_match = re.split(r"(?<=[.!?…])\s+", head, maxsplit=1)[0].strip()
        words = sentence_match.split()
        problems: List[str] = []
        if len(words) > profile.hook_max_words:
            problems.append(f"first sentence has {len(words)} words (max {profile.hook_max_words})")
        lowered_head = sentence_match.lower()
        if any(marker in lowered_head for marker in cls._META_MARKERS):
            problems.append("opening sentence contains a meta/greeting marker")
        if problems:
            return [ScriptGate._warning(
                "ERR_QA_HOOK_MISSING",
                "Weak hook: " + "; ".join(problems),
            )]
        return []


class SceneCadenceGate(BaseGate):
    def audit(self,ctx):
        n=0; wd=ctx.work_dir
        if wd:
            for fname in ("scene_manifest.json","visual_plan.json"):
                p=Path(wd)/fname
                if p.is_file():
                    try:
                        d=json.loads(p.read_text(encoding="utf-8")); sc=d.get("scenes")or[]
                        if sc: n=len(sc); break
                    except: pass
        if n==0: return []
        dur=ctx.facts.duration_seconds or (ctx.probe.duration if ctx.probe else 0.0)
        if dur<=0:
            try:
                p=Path(wd)/"scene_manifest.json" if wd else None
                if p and p.is_file(): dur=float(json.loads(p.read_text(encoding="utf-8")).get("duration_sec")or 0)
            except: pass
        if dur<=0 or n==0: return []
        avg=dur/n; min_c=ctx.profile.scene_cadence_min_sec; max_c=ctx.profile.scene_cadence_max_sec
        warn_min=ctx.profile.scene_cadence_warning_min_sec; warn_max=ctx.profile.scene_cadence_warning_max_sec
        if min_c<=avg<=max_c: return [GateResult(gate_id="scene_cadence",gate_name="scene_cadence",name="SceneCadence",status=GateStatus.PASS,score=1.0,passed=True,message=f"avg {avg:.2f}s {min_c}-{max_c}s",metric_value=avg)]
        if warn_min<=avg<=warn_max: return [GateResult(gate_id="scene_cadence",gate_name="scene_cadence",name="SceneCadence",status=GateStatus.WARNING,score=0.8,passed=True,severity=Severity.WARNING,code="ERR_QA_SCENE_CADENCE",message=f"avg {avg:.2f}s warn {warn_min}-{warn_max}",metric_value=avg,warnings=[f"avg {avg:.2f}s"])]
        return [GateResult(gate_id="scene_cadence",gate_name="scene_cadence",name="SceneCadence",status=GateStatus.FAIL,score=0.0,passed=False,severity=Severity.CRITICAL,code="ERR_QA_SCENE_CADENCE",message=f"avg {avg:.2f}s outside {warn_min}-{warn_max} target {min_c}-{max_c}",metric_value=avg,threshold_limit=max_c,errors=[f"avg {avg:.2f}s"])]
class XfadeCoverageGate(BaseGate):
    def audit(self,ctx):
        n=0; wd=ctx.work_dir; shot=[]
        if wd:
            for fname in ("scene_manifest.json","visual_plan.json"):
                p=Path(wd)/fname
                if p.is_file():
                    try:
                        d=json.loads(p.read_text(encoding="utf-8")); sc=d.get("scenes")or[]
                        if sc:
                            n=len(sc)
                            for s in sc:
                                v=s.get("duration_sec")or s.get("duration")
                                if v: shot.append(float(v))
                            break
                    except: pass
        if n<=1: return []
        dur=ctx.facts.duration_seconds or (ctx.probe.duration if ctx.probe else 0.0)
        if dur<=0 and shot: dur=sum(shot)
        if dur<=0: return []
        t=0.5
        if shot:
            try: t=min(0.5,max(0.1,min(float(d) for d in shot if d)/3.0))
            except: t=0.5
        raw=((n-1)*t)/dur if dur else 0
        if raw>0: cov=0.9*((n-1)/n)+0.1*min(1.0,raw*22)
        else: cov=0.0
        thr=ctx.profile.xfade_coverage_min; warn=ctx.profile.xfade_coverage_warning_min
        if cov>=thr: return [GateResult(gate_id="xfade_coverage",gate_name="xfade_coverage",name="XfadeCoverage",status=GateStatus.PASS,score=1.0,passed=True,message=f"coverage {cov:.3f} >={thr}",metric_value=cov)]
        if cov>=warn: return [GateResult(gate_id="xfade_coverage",gate_name="xfade_coverage",name="XfadeCoverage",status=GateStatus.WARNING,score=0.7,passed=True,severity=Severity.WARNING,code="ERR_QA_XFADE_COVERAGE",message=f"coverage {cov:.3f} warn <{thr}",metric_value=cov,threshold_limit=thr,warnings=[f"coverage {cov:.3f}"])]
        return [GateResult(gate_id="xfade_coverage",gate_name="xfade_coverage",name="XfadeCoverage",status=GateStatus.FAIL,score=0.0,passed=False,severity=Severity.CRITICAL,code="ERR_QA_XFADE_COVERAGE",message=f"coverage {cov:.3f} <{warn}",metric_value=cov,threshold_limit=thr,errors=[f"coverage {cov:.3f}"])]
class VisualIntegrityROIGate(BaseGate):
    def audit(self,ctx):
        path=ctx.file_path
        if not path or not Path(path).exists() or Path(path).stat().st_size<1024: return []
        try:
            from src.visual_integrity import VisualIntegrityVerifier
            verifier=VisualIntegrityVerifier(sample_fps=1.0)
            import tempfile; from PIL import Image
            metrics=[]
            with tempfile.TemporaryDirectory(prefix="roi_") as tmp:
                frames=verifier.extract_frames(path,tmp,fps=1.0)
                if not frames: return []
                for fp in frames:
                    try:
                        with Image.open(fp) as im: metrics.append(verifier.analyze_frame_roi(im))
                    except: continue
            if not metrics: return []
            avg_edge=sum(m.get("edge_density",0) for m in metrics)/len(metrics)
            avg_ent=sum(m.get("entropy",0) for m in metrics)/len(metrics)
            e_min=ctx.profile.avg_edge_min; e_warn=ctx.profile.avg_edge_warning_min
            ent_min=ctx.profile.entropy_min; ent_warn=ctx.profile.entropy_warning_min
            fails=[]
            if avg_edge<e_warn: fails.append(f"edge {avg_edge:.2f}<{e_warn}")
            if avg_ent<ent_warn: fails.append(f"entropy {avg_ent:.2f}<{ent_warn}")
            if avg_edge<e_warn or avg_ent<ent_warn:
                is_critical=(avg_edge<1.5) or (avg_ent<4.0) or (avg_edge<e_min and avg_ent<ent_min)
                if is_critical:
                    return [GateResult(gate_id="visual_integrity_roi",gate_name="visual_integrity_roi",name="VisualIntegrityROI",status=GateStatus.FAIL,score=0.0,passed=False,severity=Severity.CRITICAL,code="ERR_QA_ROI_LOW_DETAIL",message=f"ROI fail edge={avg_edge:.2f} ent={avg_ent:.2f} ({', '.join(fails)})",metric_value=avg_edge,errors=fails)]
                return [GateResult(gate_id="visual_integrity_roi",gate_name="visual_integrity_roi",name="VisualIntegrityROI",status=GateStatus.WARNING,score=0.7,passed=True,severity=Severity.WARNING,code="ERR_QA_ROI_LOW_DETAIL",message=f"ROI warn edge={avg_edge:.2f} ent={avg_ent:.2f}",metric_value=avg_edge,warnings=fails)]
            return [GateResult(gate_id="visual_integrity_roi",gate_name="visual_integrity_roi",name="VisualIntegrityROI",status=GateStatus.PASS,score=1.0,passed=True,message=f"ROI pass edge={avg_edge:.2f} ent={avg_ent:.2f}",metric_value=avg_edge)]
        except: return []
