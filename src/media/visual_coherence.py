"""Visual coherence SSOT for multi-scene longform/shorts.

Ownership (D2 paso 6):
- art_director: inclusion + palette (theme) + per-scene mood
- scene_planner: order (script acts) + timing scaled to audio; must not reshuffle
- local asset assembly: encode/assembly only (no palette/order rewrite)

Helpers keep planner from inventing a second scene order or dropping art_director palettes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


def visual_plan_palette(visual_plan: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Top-level or first-scene palette from art_director output."""
    if not isinstance(visual_plan, dict):
        return {}
    top = visual_plan.get("palette")
    if isinstance(top, dict) and top.get("accent"):
        return {k: str(v) for k, v in top.items() if isinstance(v, str)}
    scenes = visual_plan.get("scenes") or []
    if scenes and isinstance(scenes[0], dict):
        pal = scenes[0].get("palette")
        if isinstance(pal, dict):
            return {k: str(v) for k, v in pal.items() if isinstance(v, str)}
    return {}


def ordered_script_scene_ids(script: Dict[str, Any]) -> List[str]:
    """Canonical inclusion/order: flatten acts in script order."""
    ids: List[str] = []
    for act in script.get("acts") or []:
        if not isinstance(act, dict):
            continue
        for i, sc in enumerate(act.get("scenes") or []):
            if not isinstance(sc, dict):
                continue
            sid = sc.get("scene_id") or f"scene_{len(ids)+1:03d}"
            ids.append(str(sid))
            if "scene_id" not in sc:
                sc["scene_id"] = sid
            sc.setdefault("scene_index", len(ids))
    return ids


def plan_scenes_by_id(visual_plan: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(visual_plan, dict):
        return out
    for sc in visual_plan.get("scenes") or []:
        if isinstance(sc, dict) and sc.get("scene_id"):
            out[str(sc["scene_id"])] = sc
    return out


def timing_scales_to_audio(
    raw_durations: Sequence[float],
    target_duration: Optional[float],
) -> List[float]:
    """Proportional scene durations aligned to narration (planner timing contract)."""
    raw = [max(0.1, float(d)) for d in raw_durations]
    if not raw:
        return []
    total = sum(raw)
    if not target_duration or target_duration <= 0 or total <= 0:
        return raw
    scale = float(target_duration) / total
    scaled = [max(1.0, round(d * scale, 2)) for d in raw]
    diff = round(float(target_duration) - sum(scaled), 2)
    scaled[-1] = max(1.0, round(scaled[-1] + diff, 2))
    return scaled


def build_coherent_color_grade(
    accent_hex: str = "#00FF88",
    primary_hex: str = "#030A14",
    channel: str = "moku",
) -> str:
    """Generate subtle, filmic FFmpeg color harmony filter.

    Unifies disparate stock loops into a single cohesive visual world matching
    the channel brand identity without crushing blacks or blowing out highlights.
    """
    ch = (channel or "moku").lower()
    if "drama" in ch or "aelithia" in ch or "aita" in ch:
        # Warm, cinematic, gentle hearth tones, lifelike skin tones
        return (
            "eq=contrast=1.05:saturation=0.96:brightness=0.01:gamma=0.98,"
            "colorbalance=rs=0.02:gs=0.01:bs=-0.03:rm=0.02:gm=0.01:bm=-0.02"
        )
    elif "scifi" in ch or "singularidad" in ch or "space" in ch:
        # Deep space blacks, cool cyan shadow lift, high micro-contrast
        return (
            "eq=contrast=1.08:saturation=0.92:brightness=-0.01:gamma=0.95,"
            "colorbalance=rs=-0.03:gs=0.01:bs=0.04:rh=-0.02:gh=0.02:bh=0.05"
        )
    else:
        # Default Moku / Horror / SCP: moody dark ambient, subdued saturation, crisp shadow details
        return (
            "eq=contrast=1.06:saturation=0.88:brightness=0.00:gamma=0.97,"
            "colorbalance=rs=-0.02:gs=0.01:bs=0.02:rm=-0.01:gm=0.02:bm=0.01"
        )


def harmonize_scene_transitions(
    scenes: Sequence[Any],
    default_transition: float = 0.5,
) -> List[float]:
    """Calculate pacing-aware transition durations based on tension differentials."""
    if not scenes or len(scenes) < 2:
        return []
    transitions: List[float] = []
    for i in range(len(scenes) - 1):
        s_curr = scenes[i]
        s_next = scenes[i + 1]
        t_curr = int(getattr(s_curr, "tension_level", 2) or 2)
        t_next = int(getattr(s_next, "tension_level", 2) or 2)
        dur_curr = float(getattr(s_curr, "duration_sec", 4.0) or 4.0)
        dur_next = float(getattr(s_next, "duration_sec", 4.0) or 4.0)
        max_t = min(dur_curr, dur_next) * 0.30

        # Big tension jump: quick, punchy cut/xfade (0.20 - 0.35s)
        # Steady tension: atmospheric, gradual dissolve (0.35 - 0.75s)
        diff = abs(t_next - t_curr)
        if diff >= 2:
            ideal = min(0.35, max(0.20, default_transition * 0.5))
        elif diff == 1:
            ideal = min(0.50, max(0.30, default_transition * 0.8))
        else:
            ideal = min(0.75, max(0.35, default_transition))
        capped = min(ideal, max_t)
        transitions.append(round(capped, 2))
    return transitions


def enforce_shorts_safe_zone(width: int, height: int) -> Dict[str, int]:
    """Compute YouTube Shorts / TikTok UI safe zone to prevent UI occlusion."""
    is_vertical = height > width
    if is_vertical:
        top_margin = max(180, int(height * 0.10))
        bottom_margin = max(460, int(height * 0.25))
        if width == 1080 and height == 1920:
            right_margin = 130
            left_margin = 64
        else:
            right_margin = max(130, int(width * 0.15))
            left_margin = max(64, int(width * 0.06))
    else:
        if width == 1920 and height == 1080:
            top_margin = 80
            bottom_margin = 120
            left_margin = 80
            right_margin = 80
        else:
            top_margin = max(80, int(height * 0.08))
            bottom_margin = max(120, int(height * 0.12))
            right_margin = max(80, int(width * 0.08))
            left_margin = max(80, int(width * 0.08))

    return {
        "top": top_margin,
        "bottom": bottom_margin,
        "left": left_margin,
        "right": right_margin,
        "safe_width": width - (left_margin + right_margin),
        "safe_height": height - (top_margin + bottom_margin),
    }


def validate_visual_continuity(scenes: Sequence[Any]) -> Dict[str, Any]:
    """Validate visual continuity across scene sequence."""
    if not scenes:
        return {"valid": False, "reason": "empty_scenes"}
    durations = [float(getattr(sc, "duration_sec", 0.0) or 0.0) for sc in scenes]
    if any(d <= 0.0 for d in durations):
        return {"valid": False, "reason": "zero_or_negative_duration"}
    tensions = [int(getattr(sc, "tension_level", 1) or 1) for sc in scenes]
    transitions = harmonize_scene_transitions(scenes)
    return {
        "valid": True,
        "scene_count": len(scenes),
        "total_duration": sum(durations),
        "tensions": tensions,
        "recommended_transitions": transitions,
    }


__all__ = [
    "build_coherent_color_grade",
    "enforce_shorts_safe_zone",
    "harmonize_scene_transitions",
    "ordered_script_scene_ids",
    "plan_scenes_by_id",
    "timing_scales_to_audio",
    "validate_visual_continuity",
    "visual_plan_palette",
]
