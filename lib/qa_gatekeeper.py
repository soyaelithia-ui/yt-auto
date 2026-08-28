"""Automated QA Gatekeeper for rendered video artifacts (shared core)."""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lib.ffmpeg import (
    FFprobeError,
    has_faststart as ffmpeg_has_faststart,
    probe_media,
    run_ffmpeg,
)

_CRITICAL = "CRITICAL"
_WARNING = "WARNING"
_INFO = "INFO"

_MAX_FILESIZE_BYTES = 50 * 1024 * 1024  # 50 MB
_LUFS_MIN = -15.5
_LUFS_MAX = -12.5
_MAX_TRUE_PEAK_DBTP = -1.5
_DEAD_AUDIO_THRESHOLD_DB = -30.0
_EXTREME_SILENCE_THRESHOLD_SEC = 1.0
_FREEZE_THRESHOLD_SEC = 2.5
_BLACK_THRESHOLD_SEC = 3.0
_AV_DRIFT_THRESHOLD_SEC = 0.30
_SAFE_MARGIN_V_MIN = 180
_SAFE_MARGIN_V_MAX = 280
_MAX_CHARS_PER_LINE = 22
_MAX_WORDS_PER_LINE = 3


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


@dataclass
class QualityReportFact:
    pass


@dataclass
class QualityReportIssue:
    code: str
    message: str
    severity: str = _CRITICAL
    metric_value: Optional[float] = None
    threshold_limit: Optional[float] = None


@dataclass
class QualityReportFacts:
    faststart_enabled: bool = False
    video_codec: str = ""
    pixel_format: str = ""
    audio_codec: str = ""
    duration_seconds: float = 0.0
    av_sync_drift_sec: float = 0.0
    width: int = 0
    height: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "faststart_enabled": bool(self.faststart_enabled),
            "video_codec": str(self.video_codec),
            "pixel_format": str(self.pixel_format),
            "audio_codec": str(self.audio_codec),
            "duration_seconds": float(self.duration_seconds),
            "av_sync_drift_sec": float(self.av_sync_drift_sec),
            "width": int(self.width),
            "height": int(self.height),
        }


@dataclass
class QualityReportDTO:
    run_id: str
    channel: str
    timestamp_utc: str
    passed: bool
    strict_mode: bool
    issues: List[QualityReportIssue] = field(default_factory=list)
    facts: QualityReportFacts = field(default_factory=QualityReportFacts)

    def model_dump(self) -> Dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "channel": str(self.channel),
            "timestamp_utc": str(self.timestamp_utc),
            "passed": bool(self.passed),
            "strict_mode": bool(self.strict_mode),
            "issues": [
                {
                    "code": issue.code,
                    "message": issue.message,
                    "severity": issue.severity,
                    "metric_value": issue.metric_value,
                    "threshold_limit": issue.threshold_limit,
                }
                for issue in self.issues
            ],
            "facts": self.facts.to_dict(),
        }


def ffprobe(path: str) -> Dict[str, Any]:
    """Probe media JSON; raises RuntimeError when ffprobe fails."""
    try:
        probe = probe_media(path)
        return probe.raw_payload
    except FFprobeError as exc:
        raise RuntimeError(f"FFprobe binary crashed on corrupted file: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"FFprobe produced invalid JSON: {exc}") from exc


def has_faststart(path: str) -> bool:
    """True when the moov atom is laid out before mdat (streaming faststart)."""
    return ffmpeg_has_faststart(path)


class QAGatekeeper:
    """Validates rendered videos against the QA-1..QA-7 automated gates."""

    def __init__(self, strict_mode: bool = False) -> None:
        self.strict_mode = bool(strict_mode)

    # ------------------------------------------------------------------
    # Primary audit entry point
    # ------------------------------------------------------------------

    def audit_video(
        self,
        video_path: str,
        run_id: str | None = None,
        channel: str = "moku",
        subtitle_path: str | None = None,
        script_text: str | None = None,
        output_report_path: str | None = None,
        video_mode: str = "short",
        ass_path: str | None = None,
        **kwargs: Any,
    ) -> QualityReportDTO:
        issues: List[QualityReportIssue] = []
        report = QualityReportDTO(
            run_id=run_id or "manual",
            channel=channel,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            passed=True,
            strict_mode=self.strict_mode,
            issues=issues,
            facts=QualityReportFacts(),
        )
        subtitle_src = ass_path or subtitle_path

        if not video_path or not os.path.exists(video_path):
            issues.append(QualityReportIssue(
                code="ERR_QA_FILE_MISSING",
                message="Video file missing or does not exist",
                severity=_CRITICAL,
            ))
            report.passed = False
            self._finish(report, output_report_path)
            return report

        try:
            probe = ffprobe(video_path)
        except RuntimeError as exc:
            issues.append(QualityReportIssue(
                code="ERR_QA_FFPROBE_FAILED",
                message=f"FFprobe failed to parse the file: {exc}",
                severity=_CRITICAL,
            ))
            report.passed = False
            self._finish(report, output_report_path)
            return report

        streams = probe.get("streams") or []
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        fmt = probe.get("format") or {}

        facts = report.facts
        facts.faststart_enabled = bool(has_faststart(video_path))
        facts.video_codec = str(video_stream.get("codec_name", "")) if video_stream else ""
        facts.pixel_format = str(video_stream.get("pix_fmt", "")) if video_stream else ""
        facts.audio_codec = str(audio_stream.get("codec_name", "")) if audio_stream else ""
        video_duration_raw = video_stream.get("duration") if video_stream else None
        duration = _safe_float(fmt.get("duration") or video_duration_raw)
        if duration == 0.0 and video_stream:
            duration = _safe_float(video_stream.get("duration"))
        facts.duration_seconds = duration
        facts.width = _safe_int(video_stream.get("width"), 0) if video_stream else 0
        facts.height = _safe_int(video_stream.get("height"), 0) if video_stream else 0
        video_dur = _safe_float(video_stream.get("duration")) if video_stream else duration
        audio_dur = _safe_float(audio_stream.get("duration")) if audio_stream else duration
        facts.av_sync_drift_sec = round(abs(video_dur - audio_dur), 6)

        # ---------------- size gate ----------------
        max_size = 500 * 1024 * 1024 if video_mode in ("long", "longform") else _MAX_FILESIZE_BYTES
        try:
            size = Path(video_path).stat().st_size
        except OSError:
            size = 0
        if size > max_size:
            limit_mb = max_size / (1024 * 1024)
            self._issue(issues, "ERR_QA_FILESIZE_EXCEEDED",
                        f"File size {size} exceeds {limit_mb:.0f} MB limit",
                        metric=size / (1024 * 1024), threshold=limit_mb)

        # ---------------- container / codec gates ----------------
        if not video_stream or video_stream.get("codec_name") != "h264":
            self._issue(issues, "ERR_QA_CONTAINER_INVALID",
                        f"Invalid video codec '{video_stream.get('codec_name') if video_stream else 'none'}' (h264 required)")
        elif str(video_stream.get("profile", "")).lower() != "main":
            self._issue(issues, "ERR_QA_CONTAINER_INVALID",
                        f"Video profile '{video_stream.get('profile')}' is not Main")

        if video_stream and str(video_stream.get("pix_fmt", "")) != "yuv420p":
            self._issue(issues, "ERR_QA_PIXFMT_INVALID",
                        "Pixel format must be yuv420p")

        if not audio_stream:
            self._issue(issues, "ERR_QA_DEAD_AUDIO", "Missing audio stream")
        elif audio_stream.get("codec_name") != "aac":
            self._issue(issues, "ERR_QA_AUDIOCODEC_INVALID",
                        "Audio codec must be aac")

        if not facts.faststart_enabled:
            self._issue(issues, "ERR_QA_FASTSTART_MISSING",
                        "faststart moov atom not present before mdat")

        # ---------------- resolution & duration ----------------
        if video_stream:
            short = video_mode == "short"
            if short and not (facts.height > facts.width):
                self._issue(issues, "ERR_QA_RESOLUTION_INVALID",
                            f"Non-vertical resolution {facts.width}x{facts.height}")
            from src.config import is_test_environment
            min_dur = (15.0 if is_test_environment() else 80.0) if short else (10.0 if is_test_environment() else 600.0)
            max_dur = 180.0 if short else 3600.0
            if facts.duration_seconds < min_dur or facts.duration_seconds > max_dur:
                self._issue(issues, "ERR_QA_DURATION_OUT_OF_BOUNDS",
                            f"Duration {facts.duration_seconds:.3f}s outside allowed range",
                            metric=facts.duration_seconds)

        # ---------------- audiovisual gates ----------------
        silence_sec, mean_volume, peak_db = self._audit_audio_silence_and_volume(video_path)
        if mean_volume < _DEAD_AUDIO_THRESHOLD_DB:
            self._issue(issues, "ERR_QA_DEAD_AUDIO",
                        f"Mean volume {mean_volume:.1f} dBFS is effectively dead audio",
                        metric=mean_volume, threshold=_DEAD_AUDIO_THRESHOLD_DB)
        if silence_sec > _EXTREME_SILENCE_THRESHOLD_SEC:
            self._issue(issues, "ERR_QA_EXTREME_SILENCE",
                        f"Silence of {silence_sec:.1f}s detected")
        if peak_db > _MAX_TRUE_PEAK_DBTP:
            self._issue(issues, "ERR_QA_AUDIO_CLIPPING",
                        f"True peak {peak_db:.1f} dBTP exceeds ceiling",
                        metric=peak_db)

        freeze_sec, black_sec = self._audit_freeze_and_black_frames(video_path)
        if freeze_sec >= _FREEZE_THRESHOLD_SEC:
            self._issue(issues, "ERR_QA_VISUAL_FREEZE",
                        f"Video freeze of {freeze_sec:.1f}s detected",
                        metric=freeze_sec, threshold=_FREEZE_THRESHOLD_SEC)
        if black_sec >= _BLACK_THRESHOLD_SEC:
            self._issue(issues, "ERR_QA_BLACK_FRAME",
                        f"Black frames of {black_sec:.1f}s detected",
                        metric=black_sec, threshold=_BLACK_THRESHOLD_SEC)

        integrated_lufs, true_peak, lra = self._audit_ebu_r128_loudness(video_path)
        if not (_LUFS_MIN <= integrated_lufs <= _LUFS_MAX):
            self._issue(issues, "ERR_QA_LUFS_OUT_OF_BOUNDS",
                        f"Integrated loudness {integrated_lufs:.1f} LUFS outside [{_LUFS_MIN}, {_LUFS_MAX}]",
                        metric=integrated_lufs)
        if true_peak > _MAX_TRUE_PEAK_DBTP:
            self._issue(issues, "ERR_QA_AUDIO_CLIPPING",
                        f"True peak {true_peak:.1f} dBTP exceeds ceiling",
                        metric=true_peak)

        if abs(facts.av_sync_drift_sec) > _AV_DRIFT_THRESHOLD_SEC:
            self._issue(issues, "ERR_QA_AV_DESYNC",
                        f"AV desync of {facts.av_sync_drift_sec:.2f}s",
                        metric=facts.av_sync_drift_sec)

        # ---------------- subtitles ----------------
        if subtitle_src and os.path.exists(subtitle_src):
            sub_issues, _, _, _ = self._audit_subtitles(subtitle_src)
            issues.extend(sub_issues)

        # ---------------- script text ----------------
        if script_text:
            self._audit_script_text(script_text, issues)

        if self.strict_mode:
            report.passed = not issues
        else:
            report.passed = not any(i.severity == _CRITICAL for i in issues)
        self._finish(report, output_report_path)
        return report

    # ------------------------------------------------------------------

    def _finish(self, report: QualityReportDTO, output_report_path: str | None) -> None:
        if output_report_path:
            target = Path(output_report_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(report.model_dump(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def _issue(
        self, issues: List[QualityReportIssue], code: str, message: str,
        metric: float | None = None, threshold: float | None = None,
        severity: str = _CRITICAL,
    ) -> None:
        issues.append(QualityReportIssue(
            code=code, message=message, severity=severity,
            metric_value=metric, threshold_limit=threshold,
        ))

    def _audit_script_text(self, script_text: str, issues: List[QualityReportIssue]) -> None:
        try:
            from src.core.quality import is_spanish_neutral  # lazy: avoid import cycle
        except ImportError:
            return
        if not is_spanish_neutral(script_text):
            self._issue(issues, "ERR_QA_NON_NEUTRAL_SPANISH",
                        "Script text is not Spanish-neutral")
        try:
            from src.core.domain import LEGACY_ALIASES
        except ImportError:
            LEGACY_ALIASES = frozenset({"terror", "soy_el_malo", "horror",
                                        "moku_terror", "aita_drama"})
        lowered = script_text.lower()
        leaked = [alias for alias in LEGACY_ALIASES if alias in lowered]
        if leaked:
            self._issue(issues, "ERR_QA_ALIAS_LEAK",
                        f"Legacy alias leak detected: {', '.join(leaked)}")
        # Deterministic extensions (plan 1e): mirrored from ScriptGate as
        # warnings so both QA engines stay consistent (never critical here).
        try:
            from lib.qa.gates import ScriptGate
            from lib.qa.models import RuleProfile

            profile = RuleProfile()
            for check, args in (
                (ScriptGate._audit_connector_monotony, (script_text, profile)),
                (ScriptGate._audit_hook_presence, (script_text, profile)),
            ):
                for result in check(*args):
                    self._issue(issues, result.code, result.message,
                                severity=_WARNING)
        except ImportError:
            pass

    # ------------------------------------------------------------------
    # Low-level audio inspectors
    # ------------------------------------------------------------------

    def _audit_audio_silence_and_volume(self, path: str) -> Tuple[float, float, float]:
        """Return (max_silence_sec, mean_volume_dBFS, max_peak_dB)."""
        volume = _ffmpeg_probe_volume(path)
        silence = _ffmpeg_probe_silence(path)
        return silence, volume[0], volume[1]

    def _audit_freeze_and_black_frames(self, path: str) -> Tuple[float, float]:
        """Return (freeze_sec, black_sec)."""
        return _ffmpeg_probe_freeze_black(path)

    def _audit_ebu_r128_loudness(self, path: str) -> Tuple[float, float, float]:
        """Return (integrated_lufs, true_peak_dbtp, loudness_range)."""
        return _ffmpeg_ebu_r128(path)

    # ------------------------------------------------------------------
    # Subtitle inspector
    # ------------------------------------------------------------------

    def _audit_subtitles(self, path: str) -> Tuple[List[QualityReportIssue], int, int, bool]:
        """Return (issues, max_chars_per_line, max_words_per_line, safe_zone_compliant)."""
        issues: List[QualityReportIssue] = []
        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError:
            return [], 0, 0, False
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
                if margin_v > 0 and (margin_v < _SAFE_MARGIN_V_MIN or margin_v > _SAFE_MARGIN_V_MAX):
                    safe = False
        max_chars = 0
        max_words = 0
        for line in content.splitlines():
            if not line.startswith("Dialogue:"):
                continue
            parts = line.split(",", 9)
            payload = parts[9] if len(parts) > 9 else ""
            plain = _strip_ass_tags(payload)
            if re.search(r"\{\\k[fgt]?\d+[^}]*[¿¡]+\}", payload):
                self._issue(issues, "ERR_QA_SUBTITLE_SYNTAX",
                            "Inverted punctuation inside karaoke tag")
            max_chars = max(max_chars, len(plain.rstrip()))
            max_words = max(max_words, len(plain.split()))
        if max_chars > _MAX_CHARS_PER_LINE:
            issues.append(QualityReportIssue(
                code="ERR_QA_SUBTITLE_OVERFLOW",
                message=f"Line length {max_chars} chars exceeds {_MAX_CHARS_PER_LINE}",
                severity=_WARNING,
            ))
        if max_words > _MAX_WORDS_PER_LINE:
            issues.append(QualityReportIssue(
                code="ERR_QA_SUBTITLE_OVERFLOW",
                message=f"{max_words} words per subtitle line exceeds {_MAX_WORDS_PER_LINE}",
                severity=_WARNING,
            ))
        if not safe:
            issues.append(QualityReportIssue(
                code="ERR_QA_SUBTITLE_SAFEZONE",
                message=f"Subtitle MarginV outside safe zone ({_SAFE_MARGIN_V_MIN}..{_SAFE_MARGIN_V_MAX})",
                severity=_CRITICAL,
            ))
        return issues, max_chars, max_words, safe


def _strip_ass_tags(text: str) -> str:
    return re.sub(r"\{\\[^}]*\}", "", text)


def _ffmpeg_run(cmd: List[str], timeout: int = 300) -> subprocess.CompletedProcess:
    try:
        res = run_ffmpeg(cmd, timeout=timeout, check=False)
        return subprocess.CompletedProcess(res.command, res.returncode, res.stdout, res.stderr)
    except Exception:
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")



def _ffmpeg_probe_audio(path: str) -> Tuple[float, float]:
    """Return (mean_volume_dBFS, max_peak_dB) via volumedetect."""
    result = _ffmpeg_run(["ffmpeg", "-nostats", "-i", path,
                          "-filter_complex", "volumedetect", "-f", "null", "-"])
    output = result.stdout or result.stderr or ""
    mean = _grep_float(output, r"mean_volume:\s*(-?[\d.]+)\s*dB", -20.0)
    peak = _grep_float(output, r"max_volume:\s*(-?[\d.]+)\s*dB", 0.0)
    return mean, peak


_ffmpeg_probe_volume = _ffmpeg_probe_audio


def _ffmpeg_probe_silence(path: str) -> float:
    result = _ffmpeg_run(["ffmpeg", "-nostats", "-i", path,
                          "-af", "silencedetect=noise=-30dB:d=0.3",
                          "-f", "null", "-"])
    output = result.stdout or result.stderr or ""
    starts = [float(m) for m in re.findall(r"silence_start:\s*([\d.eE-]+)", output)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.eE-]+)", output)]
    longest = 0.0
    for i, start in enumerate(starts):
        end = ends[i] if i < len(ends) else start + 0.3
        longest = max(longest, end - start)
    return longest


def _ffmpeg_probe_freeze_black(path: str) -> Tuple[float, float]:
    result = _ffmpeg_run([
        "ffmpeg", "-nostats", "-i", path,
        "-vf", "freezedetect=n=-60dB:d=0.5,blackdetect=d=0.5:pix_th=0.10",
        "-an", "-f", "null", "-",
    ])
    output = result.stdout or result.stderr or ""
    freeze_starts = [float(m) for m in re.findall(r"freeze_start:\s*([\d.eE-]+)", output)]
    freeze_ends = [float(m) for m in re.findall(r"freeze_end:\s*([\d.eE-]+)", output)]
    freeze = 0.0
    for i, start in enumerate(freeze_starts):
        end = freeze_ends[i] if i < len(freeze_ends) else start + 0.5
        freeze = max(freeze, end - start)
    black_durations = [float(m) for m in re.findall(r"black_duration:\s*([\d.eE-]+)", output)]
    black = max(black_durations) if black_durations else 0.0
    return freeze, black


def _ffmpeg_ebu_r128(path: str) -> Tuple[float, float, float]:
    """Return (integrated_lufs, true_peak_dbtp, lra)."""
    result = _ffmpeg_run([
        "ffmpeg", "-nostats", "-i", path,
        "-filter_complex", "ebur128=peak=true", "-f", "null", "-",
    ])
    output = result.stdout or result.stderr or ""
    integrated = [_float_or_none(m) for m in re.findall(r"I:\s*(-?[\d.eE-]+)\s*LUFS", output)]
    lra_list = [_float_or_none(m) for m in re.findall(r"LRA:\s*(-?[\d.eE-]+)\s*LU", output)]
    peaks = [_float_or_none(m) for m in re.findall(r"Peak:\s*(-?[\d.eE-]+)\s*dBFS", output)]
    true_peaks = [_float_or_none(m) for m in re.findall(r"True peak:\s*(-?[\d.eE-]+)\s*dBTP", output)]
    integrated_val = (integrated or [None])[-1]
    lra_val = (lra_list or [None])[-1]
    peak_val = (true_peaks or peaks or [None])[-1]
    if integrated_val is None:
        return -14.0, peak_val if peak_val is not None else -2.0, lra_val or 8.0
    return integrated_val, (peak_val if peak_val is not None else -2.0), lra_val or 8.0


def _float_or_none(value: str) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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