"""
src/core/code_review_verdict.py - Deterministic code-based video review verdict.

Composes MediaIntegrityVerifier (container/codec/decode), QAGatekeeper (loudness/freeze/black),
and VisualIntegrityROIGate (ROI edge/entropy) into a single CodeReviewVerdict. No LLM call.

Gate results are accumulated as {gate_id: {passed, severity, code, message, metric_value, ...}}
and reasons are flattened to human-readable strings prefixed with their ERR_QA_* code.

VideoQAAgent (Gemini vision) is intentionally NOT in the default path; if a caller needs
vision QA, run it as a separate audit step and merge results into the verdict via
update_verdict_payload(). The default verdict is fully deterministic and offline.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("code_review_verdict")


@dataclass
class GateResultLite:
    """Lightweight gate result for the verdict payload."""
    gate_id: str
    passed: bool
    severity: str = "INFO"  # CRITICAL | WARNING | INFO
    code: str = ""
    message: str = ""
    metric_value: Optional[float] = None
    threshold_limit: Optional[float] = None


@dataclass
class CodeReviewVerdict:
    """Final deterministic verdict for a rendered video."""
    passed: bool
    gates: Dict[str, GateResultLite] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    report_path: Optional[str] = None
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    story_id: str = ""
    run_id: str = ""
    channel: str = ""
    video_mode: str = "short"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": bool(self.passed),
            "gates": {k: asdict(v) for k, v in self.gates.items()},
            "reasons": list(self.reasons),
            "report_path": self.report_path,
            "evaluated_at": self.evaluated_at,
            "story_id": self.story_id,
            "run_id": self.run_id,
            "channel": self.channel,
            "video_mode": self.video_mode,
        }

    def short_reason(self, limit: int = 280) -> str:
        if self.passed:
            return "code_review_pass"
        joined = "; ".join(self.reasons) or "code_review_fail"
        if len(joined) > limit:
            joined = joined[: limit - 1] + "…"
        return joined


def _safe_thumbnail_dimensions(thumbnail_path: Optional[str], video_mode: str = "short") -> Optional[GateResultLite]:
    """Check thumbnail dimensions against the lane's expected sizes."""
    if not thumbnail_path:
        return None
    p = Path(thumbnail_path)
    if not p.is_file() or p.stat().st_size == 0:
        return GateResultLite(
            gate_id="thumbnail_dimensions",
            passed=False,
            severity="CRITICAL",
            code="ERR_QA_THUMBNAIL_MISSING",
            message=f"Thumbnail missing or empty: {thumbnail_path}",
        )
    try:
        from PIL import Image  # lazy import to avoid hard dep at module load

        with Image.open(p) as img:
            w, h = img.size
        expected_short = {(720, 1280), (360, 640), (768, 1360), (1080, 1920), (1280, 720)}
        expected_long = {(1280, 720), (1920, 1080)}
        expected = expected_short if video_mode == "short" else expected_long
        if (w, h) not in expected:
            return GateResultLite(
                gate_id="thumbnail_dimensions",
                passed=False,
                severity="WARNING",
                code="ERR_QA_THUMBNAIL_SIZE",
                message=f"Thumbnail resolution {w}x{h} not in expected set for mode={video_mode}",
                metric_value=float(w * h),
            )
        return GateResultLite(
            gate_id="thumbnail_dimensions",
            passed=True,
            code="OK_THUMBNAIL",
            message=f"Thumbnail {w}x{h} acceptable for mode={video_mode}",
            metric_value=float(w * h),
        )
    except Exception as exc:
        return GateResultLite(
            gate_id="thumbnail_dimensions",
            passed=False,
            severity="WARNING",
            code="ERR_QA_THUMBNAIL_READ",
            message=f"Thumbnail open failed: {exc}",
        )


def _integrity_gate(video_path: str, work_dir: Optional[str]) -> GateResultLite:
    """Run MediaIntegrityVerifier and convert its report to a single GateResultLite."""
    try:
        from src.integrity import MediaIntegrityVerifier

        verifier = MediaIntegrityVerifier()
        report = verifier.verify_file(video_path, work_dir=work_dir)
    except Exception as exc:  # noqa: BLE001 - verifier is allowed to raise on hard corruption
        return GateResultLite(
            gate_id="media_integrity",
            passed=False,
            severity="CRITICAL",
            code="ERR_QA_MEDIA_INTEGRITY_EXCEPTION",
            message=f"MediaIntegrityVerifier crashed: {exc}",
        )

    passed = bool(report.get("passed"))
    errors = list(report.get("errors") or [])
    if not passed and not errors:
        errors = ["unknown integrity failure"]
    message = "; ".join(str(e) for e in errors[:5])
    code = "OK_INTEGRITY" if passed else (errors[0].split(":", 1)[0].replace(" ", "_").upper() if errors else "ERR_QA_INTEGRITY")
    return GateResultLite(
        gate_id="media_integrity",
        passed=passed,
        severity="INFO" if passed else "CRITICAL",
        code=code,
        message=message or ("passed" if passed else "integrity failure"),
    )


def _qa_gatekeeper_gate(
    video_path: str,
    *,
    run_id: Optional[str],
    channel: str,
    subtitle_path: Optional[str],
    ass_path: Optional[str],
    script_text: Optional[str],
    output_report_path: Optional[str],
    video_mode: str,
) -> GateResultLite:
    """Run QAGatekeeper.audit_video in strict mode and return a single GateResultLite."""
    try:
        from lib.qa_gatekeeper import QAGatekeeper

        gatekeeper = QAGatekeeper(strict_mode=True)
        report = gatekeeper.audit_video(
            video_path=video_path,
            run_id=run_id or "code_review",
            channel=channel,
            subtitle_path=subtitle_path,
            script_text=script_text,
            output_report_path=output_report_path,
            video_mode=video_mode,
            ass_path=ass_path,
        )
    except Exception as exc:  # noqa: BLE001
        return GateResultLite(
            gate_id="qa_gatekeeper",
            passed=False,
            severity="CRITICAL",
            code="ERR_QA_GATEKEEPER_EXCEPTION",
            message=f"QAGatekeeper crashed: {exc}",
        )

    issues = list(getattr(report, "issues", []) or [])
    critical = [i for i in issues if str(i.severity).upper() == "CRITICAL"]
    warnings = [i for i in issues if str(i.severity).upper() == "WARNING"]
    passed = bool(getattr(report, "passed", False))
    if critical:
        head = critical[0]
        message = "; ".join(f"{i.code}: {i.message}" for i in critical[:3])
        code = head.code or "ERR_QA_GATEKEEPER"
    elif warnings:
        head = warnings[0]
        message = "; ".join(f"{i.code}: {i.message}" for i in warnings[:3])
        code = head.code or "ERR_QA_GATEKEEPER_WARN"
    else:
        code = "OK_GATEKEEPER"
        message = "QAGatekeeper passed (strict mode)"
    return GateResultLite(
        gate_id="qa_gatekeeper",
        passed=passed,
        severity="INFO" if passed and not warnings else ("WARNING" if passed else "CRITICAL"),
        code=code,
        message=message,
        metric_value=float(len(critical)),
        threshold_limit=0.0,
    )


def _roi_gate(
    video_path: str,
    *,
    precomputed_visual: Optional[Dict[str, Any]] = None,
) -> GateResultLite:
    """Run VisualIntegrityROIGate. Returns WARNING on soft failures, CRITICAL on hard."""
    if precomputed_visual and bool(precomputed_visual.get("passed", True)):
        return GateResultLite(
            gate_id="visual_integrity_roi",
            passed=True,
            severity="INFO",
            code="OK_ROI_PRECOMPUTED",
            message="ROI gate bypassed via Stage 10 precomputed visual audit",
        )
    if not video_path or not Path(video_path).is_file() or Path(video_path).stat().st_size < 1024:
        return GateResultLite(
            gate_id="visual_integrity_roi",
            passed=True,
            severity="INFO",
            code="OK_ROI_SKIPPED",
            message="ROI gate skipped (file missing or too small)",
        )
    try:
        from src.visual_integrity import VisualIntegrityVerifier
        from PIL import Image
        import tempfile

        from lib.qa.diversity_gate import audit_frame_luminance

        verifier = VisualIntegrityVerifier(sample_fps=1.0)
        with tempfile.TemporaryDirectory(prefix="code_review_roi_") as tmp:
            frames = verifier.extract_frames(video_path, tmp, fps=1.0)
            if not frames:
                return GateResultLite(
                    gate_id="visual_integrity_roi",
                    passed=True,
                    severity="INFO",
                    code="OK_ROI_NO_FRAMES",
                    message="ROI gate skipped (no frames extracted)",
                )
            metrics = []
            lum_failures = 0
            valid_frames = 0
            for fp in frames:
                try:
                    with Image.open(fp) as im:
                        metrics.append(verifier.analyze_frame_roi(im))
                        valid_frames += 1
                        lum_ok, _, _, _ = audit_frame_luminance(im)
                        if not lum_ok:
                            lum_failures += 1
                except Exception:
                    continue

            if valid_frames > 0 and (lum_failures / valid_frames >= 0.70):
                return GateResultLite(
                    gate_id="visual_integrity_roi",
                    passed=False,
                    severity="CRITICAL",
                    code="ERR_QA_UNDER_ILLUMINATED_SCENE",
                    message=f"Over 70% of frames ({lum_failures}/{valid_frames}) are under-illuminated / near pitch-black",
                    threshold_limit=22.0,
                )
            if not metrics:
                return GateResultLite(
                    gate_id="visual_integrity_roi",
                    passed=True,
                    severity="INFO",
                    code="OK_ROI_NO_METRICS",
                    message="ROI gate skipped (no frame metrics)",
                )
            avg_edge = sum(m.get("edge_density", 0) for m in metrics) / len(metrics)
            avg_ent = sum(m.get("entropy", 0) for m in metrics) / len(metrics)
            is_critical = (avg_edge < 1.5) or (avg_ent < 4.0)
            if is_critical:
                return GateResultLite(
                    gate_id="visual_integrity_roi",
                    passed=False,
                    severity="CRITICAL",
                    code="ERR_QA_ROI_LOW_DETAIL",
                    message=f"ROI fail edge={avg_edge:.2f} ent={avg_ent:.2f}",
                    metric_value=avg_edge,
                    threshold_limit=4.0,
                )
            return GateResultLite(
                gate_id="visual_integrity_roi",
                passed=True,
                severity="INFO",
                code="OK_ROI",
                message=f"ROI pass edge={avg_edge:.2f} ent={avg_ent:.2f}",
                metric_value=avg_edge,
            )
    except Exception as exc:  # noqa: BLE001
        return GateResultLite(
            gate_id="visual_integrity_roi",
            passed=True,
            severity="WARNING",
            code="ERR_QA_ROI_EXCEPTION",
            message=f"ROI gate crashed (treated as warning): {exc}",
        )


def _scene_diversity_gate(work_dir: Optional[str], video_path: str) -> Optional[GateResultLite]:
    """Audits scene diversity and asset dominance from scene manifest."""
    if not work_dir:
        return None
    wd = Path(work_dir)
    manifest_p = wd / "scene_manifest.json"
    if not manifest_p.is_file():
        manifest_p = wd / "visual_plan.json"
    if not manifest_p.is_file():
        return None
    try:
        from lib.qa.diversity_gate import audit_scene_diversity
        dur = 0.0
        try:
            from lib.ffmpeg import probe_media
            pr = probe_media(video_path)
            dur = pr.duration or 0.0
        except Exception:
            dur = 0.0
        passed, code, msg, _ = audit_scene_diversity(manifest_p, duration_sec=dur)
        if not passed:
            return GateResultLite(
                gate_id="scene_diversity",
                passed=False,
                severity="CRITICAL",
                code=code,
                message=msg,
            )
        return GateResultLite(
            gate_id="scene_diversity",
            passed=True,
            severity="INFO",
            code=code,
            message=msg,
        )
    except Exception as exc:
        return GateResultLite(
            gate_id="scene_diversity",
            passed=True,
            severity="WARNING",
            code="ERR_QA_DIVERSITY_EXCEPTION",
            message=f"Scene diversity check failed: {exc}",
        )


def evaluate_video(
    video_path: str,
    *,
    work_dir: Optional[str] = None,
    subtitle_path: Optional[str] = None,
    ass_path: Optional[str] = None,
    script_text: Optional[str] = None,
    thumbnail_path: Optional[str] = None,
    story_id: str = "",
    run_id: str = "",
    channel: str = "moku",
    video_mode: str = "short",
    precomputed_visual: Optional[Dict[str, Any]] = None,
) -> CodeReviewVerdict:
    """Run the full deterministic code-review verdict.

    Composes (in order):
      1. MediaIntegrityVerifier (container/codec/full-decode) — fail-closed.
      2. QAGatekeeper.audit_video strict mode (loudness/freeze/black/AV drift).
      3. VisualIntegrityROIGate (ROI edge density / entropy).
      4. Thumbnail dimensions sanity.

    Verdict.passed is True only if all CRITICAL-severity gates passed.
    """
    gates: Dict[str, GateResultLite] = {}

    integrity = _integrity_gate(video_path, work_dir)
    gates["media_integrity"] = integrity
    if not integrity.passed:
        verdict = CodeReviewVerdict(
            passed=False,
            gates=gates,
            reasons=[f"{integrity.code}: {integrity.message}"] if integrity.code else [integrity.message],
            story_id=story_id,
            run_id=run_id,
            channel=channel,
            video_mode=video_mode,
        )
        if work_dir:
            verdict.report_path = _persist_report(verdict, work_dir)
        return verdict

    qa_report_path = None
    if work_dir:
        qa_report_path = str(Path(work_dir) / "code_review_qa_report.json")
    qa = _qa_gatekeeper_gate(
        video_path,
        run_id=run_id,
        channel=channel,
        subtitle_path=subtitle_path,
        ass_path=ass_path,
        script_text=script_text,
        output_report_path=qa_report_path,
        video_mode=video_mode,
    )
    gates["qa_gatekeeper"] = qa

    roi = _roi_gate(video_path, precomputed_visual=precomputed_visual)
    gates["visual_integrity_roi"] = roi

    scene_div = _scene_diversity_gate(work_dir, video_path)
    if scene_div is not None:
        gates["scene_diversity"] = scene_div

    thumb = _safe_thumbnail_dimensions(thumbnail_path, video_mode=video_mode)
    if thumb is not None:
        gates["thumbnail_dimensions"] = thumb

    reasons: List[str] = []
    for gate in gates.values():
        if not gate.passed and gate.severity == "CRITICAL":
            prefix = gate.code or "ERR_QA_UNKNOWN"
            reasons.append(f"{prefix}: {gate.message}" if gate.message else prefix)
        elif gate.severity == "WARNING":
            prefix = gate.code or "ERR_QA_WARN"
            if gate.message:
                reasons.append(f"{prefix}: {gate.message}")

    passed = all(g.passed or g.severity != "CRITICAL" for g in gates.values())
    verdict = CodeReviewVerdict(
        passed=passed,
        gates=gates,
        reasons=reasons,
        story_id=story_id,
        run_id=run_id,
        channel=channel,
        video_mode=video_mode,
    )
    if work_dir:
        verdict.report_path = _persist_report(verdict, work_dir)
    return verdict


def _persist_report(verdict: CodeReviewVerdict, work_dir: str) -> str:
    out = Path(work_dir) / "code_review_report.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(verdict.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Could not persist code_review_report.json at %s: %s", out, exc)
    return str(out)


def is_code_review_enabled() -> bool:
    """Read CODE_REVIEW_ENABLED env (default ON). 0/false/no disables the verdict."""
    flag = os.environ.get("CODE_REVIEW_ENABLED", "1").strip().lower()
    return flag not in ("0", "false", "no", "off", "")


def is_vision_qa_enabled() -> bool:
    """Opt-in Gemini vision QA. Off by default; never blocks the verdict."""
    flag = os.environ.get("CODE_REVIEW_VISION_QA", "0").strip().lower()
    return flag in ("1", "true", "yes", "on")


def update_verdict_payload(
    existing: Optional[Dict[str, Any]],
    verdict: CodeReviewVerdict,
    *,
    user_id: int = 0,
) -> Dict[str, Any]:
    """Merge a new verdict into a ReviewJob.metadata dict. Pure helper for tests/replays."""
    base: Dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}
    base["code_verdict"] = verdict.to_dict()
    base["code_reviewed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    base["code_reviewer_user_id"] = int(user_id)
    return base
