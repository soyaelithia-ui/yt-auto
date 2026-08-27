"""Typed domain models and threshold profiles for QualityAuditEngine."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


class Severity:
    """Severity levels for audit gate results."""
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class GateStatus:
    """Evaluation status for audit gates."""
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    WARN = "WARNING"
    SKIP = "SKIP"


@dataclass
class GateResult:
    """Structured result from an individual gate audit."""
    gate_id: str = ""
    name: str = ""
    status: Union[GateStatus, str] = GateStatus.PASS
    score: float = 1.0
    gate_name: str = ""
    passed: Optional[bool] = None
    severity: str = Severity.CRITICAL
    code: str = ""
    message: str = ""
    metric_value: Optional[float] = None
    threshold_limit: Optional[float] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.gate_name and self.name:
            self.gate_name = self.name.lower()
        if not self.name and self.gate_name:
            self.name = self.gate_name
        if not self.gate_id:
            self.gate_id = self.gate_name or self.name or "gate"
        if self.passed is None:
            if self.errors or self.status == GateStatus.FAIL or self.status == "FAIL":
                self.passed = False
            else:
                self.passed = True

    @property
    def is_passed(self) -> bool:
        if self.passed is not None and not self.passed:
            return False
        if self.errors:
            return False
        return self.status in (GateStatus.PASS, GateStatus.WARNING, "PASS", "WARNING")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate_id": str(self.gate_id),
            "gate_name": str(self.gate_name or self.name),
            "name": str(self.name),
            "status": str(self.status),
            "score": float(self.score),
            "passed": bool(self.is_passed),
            "severity": str(self.severity),
            "code": str(self.code),
            "message": str(self.message),
            "metric_value": self.metric_value,
            "threshold_limit": self.threshold_limit,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "details": dict(self.details),
        }


@dataclass
class MediaProbeFacts:
    """Container and stream facts extracted during media probing."""
    faststart_enabled: bool = False
    video_codec: str = ""
    pixel_format: str = ""
    audio_codec: str = ""
    duration_seconds: float = 0.0
    av_sync_drift_sec: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    size_bytes: int = 0
    sha256_hash: str = ""
    format_name: str = ""
    decoded_frames: int = 0
    expected_frames: int = 0

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
            "fps": float(self.fps),
            "size_bytes": int(self.size_bytes),
            "sha256_hash": str(self.sha256_hash),
            "format_name": str(self.format_name),
            "decoded_frames": int(self.decoded_frames),
            "expected_frames": int(self.expected_frames),
        }


@dataclass
class RuleProfile:
    """Thresholds and validation rules for media quality auditing."""
    name: str = "short"
    max_file_size_mb: float = 50.0
    min_duration_sec: float = 15.0
    max_duration_sec: float = 180.0
    expected_fps: float = 30.0
    require_vertical: bool = True
    min_width: int = 0
    min_height: int = 0
    allowed_video_codecs: List[str] = field(default_factory=lambda: ["h264", "libx264"])
    allowed_video_profiles: List[str] = field(default_factory=lambda: ["main", "high", "baseline"])
    allowed_pix_fmts: List[str] = field(default_factory=lambda: ["yuv420p", "yuvj420p"])
    allowed_audio_codecs: List[str] = field(default_factory=lambda: ["aac"])
    allowed_sample_rates: List[int] = field(default_factory=lambda: [44100, 48000])
    allowed_channels: List[int] = field(default_factory=lambda: [2])
    require_faststart: bool = True
    require_full_decode: bool = True
    lufs_min: float = -15.5
    lufs_max: float = -12.5
    max_true_peak_dbtp: float = -1.5
    dead_audio_threshold_db: float = -30.0
    extreme_silence_threshold_sec: float = 1.0
    freeze_threshold_sec: float = 2.5
    black_threshold_sec: float = 3.0
    av_drift_threshold_sec: float = 0.30
    subtitle_safe_margin_v_min: int = 180
    subtitle_safe_margin_v_max: int = 280
    subtitle_max_chars_per_line: int = 22
    subtitle_max_words_per_line: int = 3
    # PR3 visual-director thresholds
    visual_diversity_min_ratio: float = 0.75
    visual_diversity_min_ratio_small_n: float = 0.60
    visual_diversity_min_hamming: int = 10
    scene_cadence_min_sec: float = 8.0
    scene_cadence_max_sec: float = 12.0
    scene_cadence_warning_min_sec: float = 6.0
    scene_cadence_warning_max_sec: float = 15.0
    xfade_coverage_min: float = 0.90
    xfade_coverage_warning_min: float = 0.70
    avg_edge_min: float = 2.0
    avg_edge_warning_min: float = 1.5
    entropy_min: float = 4.5
    entropy_warning_min: float = 4.0
    # Deterministic script-gate extensions (plan 1e) — warnings by default.
    title_max_repetitions: int = 2
    hook_max_words: int = 25
    connector_monotony_ratio: float = 0.40

    @property
    def max_file_size_bytes(self) -> int:
        return int(self.max_file_size_mb * 1024 * 1024)

    @max_file_size_bytes.setter
    def max_file_size_bytes(self, val: int) -> None:
        self.max_file_size_mb = float(val) / (1024.0 * 1024.0)

    @classmethod
    def get_preset(cls, name: str, **overrides: Any) -> RuleProfile:
        """Resolves a named preset rule profile."""
        key = name.lower().strip()
        if key in ("short", "shorts", "youtube_short"):
            return cls.preset_short(**overrides)
        if key in ("longform", "long_form", "video"):
            return cls.preset_longform(**overrides)
        if key in ("telegram", "telegram_canary", "tg"):
            return cls.preset_telegram(**overrides)
        if key in ("strict", "strict_master"):
            return cls.preset_strict_master(**overrides)
        return cls(name=name, **overrides)

    @classmethod
    def preset_short(cls, **overrides: Any) -> RuleProfile:
        """YouTube Shorts profile."""
        defaults: Dict[str, Any] = {
            "name": "short",
            "max_file_size_mb": 50.0,
            "min_duration_sec": 15.0,
            "max_duration_sec": 180.0,
            "require_vertical": True,
            "allowed_video_profiles": ["main"],
            "scene_cadence_max_sec": 15.0,
        }
        defaults.update(overrides)
        return cls(**defaults)

    @classmethod
    def preset_longform(cls, **overrides: Any) -> RuleProfile:
        """Long-form landscape video profile."""
        defaults: Dict[str, Any] = {
            "name": "longform",
            "max_file_size_mb": 2048.0,
            "min_duration_sec": 600.0,
            "max_duration_sec": 3600.0,
            "require_vertical": False,
            "allowed_video_profiles": ["main", "high"],
            "scene_cadence_max_sec": 12.0,
        }
        defaults.update(overrides)
        return cls(**defaults)

    @classmethod
    def preset_telegram(cls, **overrides: Any) -> RuleProfile:
        """Telegram preview & upload preflight profile."""
        defaults: Dict[str, Any] = {
            "name": "telegram_canary",
            "max_file_size_mb": 45.0,
            "min_duration_sec": 1.0,
            "max_duration_sec": 3600.0,
            "require_vertical": False,
            "require_faststart": True,
            "require_full_decode": False,
        }
        defaults.update(overrides)
        return cls(**defaults)

    @classmethod
    def preset_telegram_canary(cls, **overrides: Any) -> RuleProfile:
        """Telegram canary profile (alias for telegram)."""
        return cls.preset_telegram(**overrides)

    @classmethod
    def preset_strict_master(cls, **overrides: Any) -> RuleProfile:
        """Strict master release profile."""
        defaults: Dict[str, Any] = {
            "name": "strict_master",
            "max_file_size_mb": 50.0,
            "min_duration_sec": 15.0,
            "max_duration_sec": 180.0,
            "require_vertical": True,
            "require_faststart": True,
            "require_full_decode": True,
        }
        defaults.update(overrides)
        return cls(**defaults)


@dataclass
class QualityAuditReport:
    """Unified report containing gate evaluation results and media facts."""
    file_path: str = ""
    passed: bool = True
    overall_score: float = 1.0
    score: float = 100.0
    duration: float = 0.0
    gates: Dict[str, GateResult] = field(default_factory=dict)
    summary_reasons: List[str] = field(default_factory=list)
    gate_results: List[GateResult] = field(default_factory=list)
    facts: MediaProbeFacts = field(default_factory=MediaProbeFacts)
    run_id: str = ""
    channel: str = "moku"
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    strict_mode: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    decode_command: str = ""
    decode_exit_code: int = 0

    def __post_init__(self) -> None:
        if self.gate_results and not self.gates:
            for gr in self.gate_results:
                key = gr.gate_name or gr.name or gr.gate_id
                self.gates[key.lower()] = gr
        elif self.gates and not self.gate_results:
            self.gate_results = list(self.gates.values())
        if self.overall_score == 1.0 and self.score != 100.0:
            self.overall_score = self.score / 100.0
        elif self.score == 100.0 and self.overall_score != 1.0:
            self.score = self.overall_score * 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "file_path": str(self.file_path),
            "channel": str(self.channel),
            "timestamp_utc": str(self.timestamp_utc),
            "passed": bool(self.passed),
            "overall_score": float(self.overall_score),
            "score": float(self.score),
            "strict_mode": bool(self.strict_mode),
            "duration": float(self.duration or self.facts.duration_seconds),
            "gates": {k: v.to_dict() for k, v in self.gates.items()},
            "gate_results": [r.to_dict() for r in self.gate_results],
            "summary_reasons": list(self.summary_reasons),
            "facts": self.facts.to_dict(),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "decode_command": str(self.decode_command),
            "decode_exit_code": int(self.decode_exit_code),
        }

    def to_legacy_gatekeeper_tuple(self) -> Tuple[bool, str, List[str]]:
        """Returns legacy (passed, reason, all_reasons) tuple."""
        reason = "PASS" if self.passed else (self.summary_reasons[0] if self.summary_reasons else "FAIL")
        return self.passed, reason, self.summary_reasons

    def to_legacy_dto(self) -> Any:
        """Converts report to legacy QualityReportDTO."""
        from lib.qa_gatekeeper import (
            QualityReportDTO,
            QualityReportFacts,
            QualityReportIssue,
        )

        issues = [
            QualityReportIssue(
                code=r.code or f"ERR_QA_{r.gate_name.upper()}",
                message=r.message or (r.errors[0] if r.errors else ""),
                severity=r.severity,
                metric_value=r.metric_value,
                threshold_limit=r.threshold_limit,
            )
            for r in self.gate_results
            if not r.is_passed
        ]

        dto_facts = QualityReportFacts(
            faststart_enabled=self.facts.faststart_enabled,
            video_codec=self.facts.video_codec,
            pixel_format=self.facts.pixel_format,
            audio_codec=self.facts.audio_codec,
            duration_seconds=self.facts.duration_seconds or self.duration,
            av_sync_drift_sec=self.facts.av_sync_drift_sec,
            width=self.facts.width,
            height=self.facts.height,
        )

        return QualityReportDTO(
            run_id=self.run_id or "manual",
            channel=self.channel,
            timestamp_utc=self.timestamp_utc,
            passed=self.passed,
            strict_mode=self.strict_mode,
            issues=issues,
            facts=dto_facts,
        )

    def to_integrity_dict(self) -> Dict[str, Any]:
        """Converts report to dictionary compatible with media_integrity.py."""
        path_obj = Path(self.file_path) if self.file_path else Path("unknown.mp4")
        return {
            "file_path": str(self.file_path),
            "filename": path_obj.name,
            "size_bytes": self.facts.size_bytes or (path_obj.stat().st_size if path_obj.exists() else 0),
            "sha256_hash": self.facts.sha256_hash,
            "passed": self.passed,
            "decode_command": self.decode_command or f"ffmpeg -v error -xerror -i {self.file_path} -map 0:v:0 -map 0:a:0 -f null -",
            "decode_exit_code": self.decode_exit_code,
            "errors": self.errors or self.summary_reasons,
            "format_name": self.facts.format_name or "mp4",
            "duration_sec": round(self.facts.duration_seconds or self.duration, 2),
            "video_stream": {
                "codec": self.facts.video_codec or "h264",
                "profile": "main",
                "width": self.facts.width,
                "height": self.facts.height,
                "pix_fmt": self.facts.pixel_format or "yuv420p",
                "fps": self.facts.fps or 30.0,
                "duration_sec": round(self.facts.duration_seconds or self.duration, 2),
                "decoded_frames": self.facts.decoded_frames or self.facts.expected_frames,
                "expected_frames": self.facts.expected_frames,
            },
            "audio_stream": {
                "codec": self.facts.audio_codec or "aac",
                "sample_rate": 44100,
                "channels": 2,
                "duration_sec": round(self.facts.duration_seconds or self.duration, 2),
            },
            "faststart_optimized": self.facts.faststart_enabled,
        }
