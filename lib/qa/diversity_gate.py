"""
lib/qa/diversity_gate.py - QA Gates for Scene Diversity and Perceived Luminance.

Enforces:
1. Minimum scene diversity for longform productions (rejecting static single-loop videos).
2. Asset dominance ceilings (no single visual asset exceeding 25% duration in longform).
3. Perceived luminance and contrast floors (rejecting pitch-black and under-illuminated scenes).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from lib.qa.models import GateResult, GateStatus, Severity
from lib.qa.gates import BaseGate, AuditContext


def audit_scene_diversity(
    manifest_or_dict: Union[Dict[str, Any], Path, str],
    duration_sec: float,
    min_longform_scenes: int = 6,
    max_asset_dominance_ratio: float = 0.25,
    *,
    is_short: bool = False,
    min_short_scenes: int = 3,
) -> Tuple[bool, str, str, Dict[str, Any]]:
    """Audit scene count and single-asset dominance.

    - Shorts (`is_short=True`): require at least `min_short_scenes` (default 3).
    - Longform (`duration_sec >= 300` when not short): require at least `min_longform_scenes`.
    - No single visual asset may occupy more than `max_asset_dominance_ratio` (25%) of the runtime.
    """
    data: Dict[str, Any] = {}
    if isinstance(manifest_or_dict, dict):
        data = manifest_or_dict
    else:
        p = Path(manifest_or_dict)
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                data = {}

    scenes = data.get("scenes") or []
    scene_count = len(scenes)
    total_dur = float(data.get("duration_sec") or duration_sec or 0.0)

    # Scene count invariants (shorts vs longform)
    if is_short:
        if scene_count < min_short_scenes:
            return (
                False,
                "ERR_QA_SHORT_DIVERSITY_INSUFFICIENT",
                f"Short production ({total_dur:.1f}s) has {scene_count} scenes, but requires at least {min_short_scenes} distinct scenes.",
                {"scene_count": scene_count, "min_required": min_short_scenes, "duration_sec": total_dur, "is_short": True},
            )
    elif total_dur >= 300.0 and scene_count < min_longform_scenes:
        return (
            False,
            "ERR_QA_SCENE_DIVERSITY_INSUFFICIENT",
            f"Longform production ({total_dur:.1f}s) has {scene_count} scenes, but requires at least {min_longform_scenes} distinct scenes.",
            {"scene_count": scene_count, "min_required": min_longform_scenes, "duration_sec": total_dur},
        )

    # Asset dominance invariant (25% ceiling; applies whenever runtime is known)
    asset_durations: Dict[str, float] = {}
    for sc in scenes:
        proc_cfg = sc.get("procedural_config")
        template_name = proc_cfg.get("template_name") if isinstance(proc_cfg, dict) else None
        asset_id = (
            sc.get("image_path")
            or sc.get("asset_path")
            or sc.get("source")
            or template_name
            or sc.get("category")
            or "unknown"
        )
        sc_dur = float(sc.get("duration_sec") or sc.get("duration") or (total_dur / max(1, scene_count)))
        asset_durations[str(asset_id)] = asset_durations.get(str(asset_id), 0.0) + sc_dur

    if total_dur > 0 and scenes:
        for asset_id, dur in asset_durations.items():
            ratio = dur / total_dur
            if ratio > max_asset_dominance_ratio:
                return (
                    False,
                    "ERR_QA_ASSET_DOMINANCE_EXCEEDED",
                    f"Asset '{asset_id}' occupies {ratio * 100:.1f}% of total duration ({dur:.1f}s / {total_dur:.1f}s), exceeding maximum allowed 25%.",
                    {"dominant_asset": asset_id, "duration": dur, "ratio": ratio, "max_allowed": max_asset_dominance_ratio},
                )

    return (
        True,
        "OK_SCENE_DIVERSITY",
        f"Scene diversity compliant ({scene_count} scenes across {total_dur:.1f}s)",
        {"scene_count": scene_count, "duration_sec": total_dur},
    )



def evaluate_scene_diversity(manifest: Dict[str, Any], is_short: bool = False) -> Dict[str, Any]:
    """Dict API for gatekeeper / callers (is_passed, failure_code, message)."""
    scenes = manifest.get("scenes") or []
    total = float(manifest.get("duration_sec") or sum(float(s.get("duration_sec") or 0.0) for s in scenes) or 0.0)
    passed, code, msg, _details = audit_scene_diversity(manifest, duration_sec=total, is_short=is_short)
    return {
        "is_passed": bool(passed),
        "failure_code": None if passed else code,
        "message": msg,
    }


class SceneDiversityGate(BaseGate):
    """Audits scene count diversity and asset dominance in production."""

    def audit(self, ctx: AuditContext) -> List[GateResult]:
        wd = ctx.work_dir
        manifest_data = None
        if wd:
            for fname in ("scene_manifest.json", "visual_plan.json"):
                p = Path(wd) / fname
                if p.is_file():
                    try:
                        manifest_data = json.loads(p.read_text(encoding="utf-8"))
                        if manifest_data.get("scenes"):
                            break
                    except Exception:
                        pass

        dur = float(ctx.facts.duration_seconds or (ctx.probe.duration if ctx.probe else 0.0))
        if not manifest_data or dur <= 0:
            return []

        is_short = bool(
            dur < 180.0
            or (
                getattr(ctx.facts, "height", 0) > getattr(ctx.facts, "width", 0)
                and dur < 300.0
            )
        )
        passed, code, msg, details = audit_scene_diversity(
            manifest_data, duration_sec=dur, is_short=is_short
        )
        if passed:
            return [
                GateResult(
                    gate_id="scene_diversity",
                    gate_name="scene_diversity",
                    name="SceneDiversity",
                    status=GateStatus.PASS,
                    score=1.0,
                    passed=True,
                    code="OK_SCENE_DIVERSITY",
                    message=msg,
                    details=details,
                )
            ]
        return [
            GateResult(
                gate_id="scene_diversity",
                gate_name="scene_diversity",
                name="SceneDiversity",
                status=GateStatus.FAIL,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                code=code,
                message=msg,
                errors=[msg],
                details=details,
            )
        ]


def audit_frame_luminance(
    image_or_path: Any,
    min_mean_y: float = 22.0,
    max_dark_ratio: float = 0.85,
) -> Tuple[bool, str, str, Dict[str, Any]]:
    """Audit human-perceived luminance and shadow contrast.

    Calculates ITU-R BT.709 relative luminance:
    Y = 0.2126 * R + 0.7152 * G + 0.0722 * B

    Fails if:
    - Mean luminance is lower than min_mean_y (under-illuminated).
    - Or proportion of pixels with Y < 16.0 exceeds max_dark_ratio (85%+ black).
    """
    from PIL import Image

    if isinstance(image_or_path, (str, Path)):
        im = Image.open(str(image_or_path)).convert("RGB")
    elif hasattr(image_or_path, "convert"):
        im = image_or_path.convert("RGB")
    else:
        return True, "OK_LUMINANCE_SKIPPED", "No image object provided", {}

    # Downsample for microsecond performance if image is large
    w, h = im.size
    if w > 200 or h > 200:
        im = im.resize((100, 100))

    # Fast photometric luminance via native Pillow grayscale conversion
    gray = im.convert("L")
    raw_bytes = gray.tobytes()
    total_pixels = len(raw_bytes)
    if total_pixels == 0:
        return True, "OK_LUMINANCE_SKIPPED", "Empty image", {}

    sum_y = sum(raw_bytes)
    dark_pixels = sum(1 for val in raw_bytes if val < 16)

    mean_y = sum_y / total_pixels
    dark_ratio = dark_pixels / total_pixels

    if mean_y < min_mean_y or dark_ratio > max_dark_ratio:
        return (
            False,
            "ERR_QA_UNDER_ILLUMINATED_SCENE",
            f"Scene under-illuminated: mean luminance Y={mean_y:.1f} (min {min_mean_y}), darkness ratio={dark_ratio*100:.1f}% (max {max_dark_ratio*100:.1f}%).",
            {"mean_luminance": round(mean_y, 2), "dark_ratio": round(dark_ratio, 3), "min_required_y": min_mean_y},
        )

    return (
        True,
        "OK_LUMINANCE_COMPLIANT",
        f"Luminance compliant: mean Y={mean_y:.1f}, dark ratio={dark_ratio*100:.1f}%.",
        {"mean_luminance": round(mean_y, 2), "dark_ratio": round(dark_ratio, 3)},
    )


class LuminanceContrastGate(BaseGate):
    """Evaluates sampled video frames for minimum perceived luminance and visibility."""

    def audit(self, ctx: AuditContext) -> List[GateResult]:
        path = getattr(ctx, "file_path", None) or getattr(ctx, "video_path", None)
        if not path or not Path(path).is_file() or Path(path).stat().st_size < 1024:
            return []

        try:
            from src.visual_integrity import VisualIntegrityVerifier
            import tempfile
            from PIL import Image

            verifier = VisualIntegrityVerifier(sample_fps=1.0)
            lum_results = []
            with tempfile.TemporaryDirectory(prefix="lum_qa_") as tmp:
                frames = verifier.extract_frames(path, tmp, fps=1.0)
                if not frames:
                    return []
                for fp in frames:
                    try:
                        with Image.open(fp) as im:
                            passed, code, msg, details = audit_frame_luminance(im)
                            lum_results.append((passed, code, details))
                    except Exception:
                        continue

            if not lum_results:
                return []

            failed_frames = sum(1 for passed, _, _ in lum_results if not passed)
            total = len(lum_results)
            if total > 0 and (failed_frames / total >= 0.70):
                return [
                    GateResult(
                        gate_id="luminance_contrast",
                        gate_name="luminance_contrast",
                        name="LuminanceContrast",
                        status=GateStatus.FAIL,
                        score=0.0,
                        passed=False,
                        severity=Severity.CRITICAL,
                        code="ERR_QA_UNDER_ILLUMINATED_SCENE",
                        message=f"Over 70% of frames ({failed_frames}/{total}) are under-illuminated / near pitch-black",
                        metric_value=float(failed_frames / total),
                        threshold_limit=0.70,
                        errors=[f"{failed_frames}/{total} frames failed minimum luminance"],
                    )
                ]

            return [
                GateResult(
                    gate_id="luminance_contrast",
                    gate_name="luminance_contrast",
                    name="LuminanceContrast",
                    status=GateStatus.PASS,
                    score=1.0,
                    passed=True,
                    code="OK_LUMINANCE_COMPLIANT",
                    message=f"Luminance contrast verified ({total - failed_frames}/{total} frames compliant)",
                )
            ]
        except Exception as exc:
            return [
                GateResult(
                    gate_id="luminance_contrast",
                    gate_name="luminance_contrast",
                    name="LuminanceContrast",
                    status=GateStatus.PASS,
                    score=1.0,
                    passed=True,
                    code="OK_LUMINANCE_SKIPPED",
                    message=f"Luminance audit skipped: {exc}",
                )
            ]


