"""Centralized Single-Pass Quality Audit Engine."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from lib.ffmpeg import (
    FFprobeError,
    probe_media,
)
from lib.qa.gates import (
    AuditContext,
    AudioQualityGate,
    BaseGate,
    ContainerGate,
    SceneCadenceGate,
    ScriptGate,
    SizeQuotaGate,
    SubtitleGate,
    VisualIntegrityROIGate,
    VisualQualityGate,
    XfadeCoverageGate,
)
from lib.qa.diversity_gate import LuminanceContrastGate, SceneDiversityGate
from lib.qa.models import (
    GateResult,
    GateStatus,
    MediaProbeFacts,
    QualityAuditReport,
    RuleProfile,
    Severity,
)

logger = logging.getLogger(__name__)


class QualityAuditEngine:
    """Centralized single-pass media verification and QA gate auditing engine."""

    def __init__(
        self,
        default_profile: Union[RuleProfile, str] = "short",
        strict_mode: bool = False,
        gates: Optional[List[BaseGate]] = None,
    ) -> None:
        if isinstance(default_profile, str):
            self.default_profile = RuleProfile.get_preset(default_profile)
        else:
            self.default_profile = default_profile
        self.strict_mode = strict_mode
        self.gates: List[BaseGate] = gates if gates is not None else [
            SizeQuotaGate(),
            ContainerGate(),
            AudioQualityGate(),
            VisualQualityGate(),
            SubtitleGate(),
            ScriptGate(),
            SceneCadenceGate(),
            XfadeCoverageGate(),
            VisualIntegrityROIGate(),
            SceneDiversityGate(),
            LuminanceContrastGate(),
        ]

    def audit_media(
        self,
        file_path: Union[str, Path],
        profile: Optional[Union[RuleProfile, str]] = None,
        *,
        run_id: Optional[str] = None,
        channel: str = "moku",
        subtitle_path: Optional[str] = None,
        script_text: Optional[str] = None,
        strict_mode: Optional[bool] = None,
        work_dir: Optional[Union[str, Path]] = None,
        output_report_path: Optional[Union[str, Path]] = None,
        **overrides: Any,
    ) -> QualityAuditReport:
        """
        Executes single-pass media quality auditing against configured rule profiles and gates.
        """
        path_str = str(file_path) if file_path else ""
        path_obj = Path(path_str) if path_str else None

        # 1. Resolve rule profile
        if profile is None:
            active_profile = self.default_profile
        elif isinstance(profile, str):
            active_profile = RuleProfile.get_preset(profile, **overrides)
        else:
            active_profile = profile

        if overrides and isinstance(profile, RuleProfile):
            prof_dict = {
                k: getattr(active_profile, k)
                for k in dir(active_profile)
                if not k.startswith("_") and not callable(getattr(active_profile, k))
            }
            prof_dict.update(overrides)
            active_profile = RuleProfile(**prof_dict)

        eff_strict = self.strict_mode if strict_mode is None else bool(strict_mode)

        # 2. Prepare Audit Context
        ctx = AuditContext(
            file_path=path_str,
            profile=active_profile,
            subtitle_path=subtitle_path,
            script_text=script_text,
            strict_mode=eff_strict,
            work_dir=str(work_dir) if work_dir else None,
        )

        # 3. Check fast exit for missing / empty file
        if not path_str or not path_obj or not path_obj.exists() or not path_obj.is_file():
            missing_result = GateResult(
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
            )
            report = QualityAuditReport(
                run_id=run_id or "manual",
                file_path=path_str,
                channel=channel,
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                passed=False,
                strict_mode=eff_strict,
                overall_score=0.0,
                score=0.0,
                gates={"size": missing_result},
                gate_results=[missing_result],
                summary_reasons=[missing_result.message],
                errors=[missing_result.message],
            )
            self._save_report(report, work_dir, output_report_path)
            return report

        # 4. Execute single-pass media probing
        try:
            ctx.probe = probe_media(path_obj, timeout=30.0)
            ctx.facts.duration_seconds = ctx.probe.duration
            ctx.facts.format_name = ctx.probe.format_name
            ctx.facts.size_bytes = ctx.probe.size_bytes or (path_obj.stat().st_size if path_obj.exists() else 0)
            if ctx.probe.primary_video:
                pv = ctx.probe.primary_video
                ctx.facts.video_codec = pv.codec_name
                ctx.facts.pixel_format = pv.pix_fmt
                ctx.facts.width = pv.width
                ctx.facts.height = pv.height
                ctx.facts.fps = pv.fps
            if ctx.probe.primary_audio:
                pa = ctx.probe.primary_audio
                ctx.facts.audio_codec = pa.codec_name
        except FFprobeError as exc:
            ctx.probe_error = exc
        except Exception as exc:
            ctx.probe_error = exc

        # 5. Run all modular gates
        all_results: List[GateResult] = []
        gates_dict: Dict[str, GateResult] = {}
        all_errors: List[str] = []
        all_warnings: List[str] = []
        summary_reasons: List[str] = []

        for gate in self.gates:
            gate_results = gate.audit(ctx)
            for gr in gate_results:
                all_results.append(gr)
                key = gr.gate_name or gr.name or gr.gate_id
                key_lower = key.lower()
                if key_lower not in gates_dict or not gr.is_passed:
                    gates_dict[key_lower] = gr

                if not gr.is_passed or gr.severity == Severity.CRITICAL:
                    msg = gr.message or (gr.errors[0] if gr.errors else f"{gr.name} failed")
                    all_errors.append(msg)
                    summary_reasons.append(msg)
                elif gr.severity == Severity.WARNING:
                    msg = gr.message or (gr.warnings[0] if gr.warnings else f"{gr.name} warning")
                    all_warnings.append(msg)
                    if eff_strict:
                        summary_reasons.append(msg)

        # 6. Synthesize Report
        passed = (len(all_errors) == 0 and len(all_warnings) == 0) if eff_strict else (len(all_errors) == 0)
        if passed:
            overall_score = max(0.0, 1.0 - (0.05 * len(all_warnings)))
        else:
            overall_score = 0.0

        report = QualityAuditReport(
            run_id=run_id or "manual",
            file_path=path_str,
            channel=channel,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            passed=passed,
            strict_mode=eff_strict,
            overall_score=overall_score,
            score=overall_score * 100.0,
            duration=ctx.facts.duration_seconds,
            gates=gates_dict,
            gate_results=all_results,
            summary_reasons=summary_reasons,
            facts=ctx.facts,
            errors=all_errors,
            warnings=all_warnings,
        )

        self._save_report(report, work_dir, output_report_path)
        return report

    def _save_report(
        self,
        report: QualityAuditReport,
        work_dir: Optional[Union[str, Path]],
        output_report_path: Optional[Union[str, Path]],
    ) -> None:
        target_path: Optional[Path] = None
        if output_report_path:
            target_path = Path(output_report_path)
        elif work_dir:
            target_path = Path(work_dir) / "quality_audit_report.json"

        if target_path:
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(
                    json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception as exc:
                logger.warning("Failed to write quality audit report to %s: %s", target_path, exc)


def audit_media(
    file_path: Union[str, Path],
    profile: Union[RuleProfile, str] = "short",
    **kwargs: Any,
) -> QualityAuditReport:
    """Convenience helper function for single-pass media quality auditing."""
    engine = QualityAuditEngine(default_profile=profile)
    return engine.audit_media(file_path, profile=profile, **kwargs)
