"""Visual coherence SSOT for multi-scene longform/shorts.

Ownership (D2 paso 6):
- art_director: inclusion + palette (theme) + per-scene mood
- scene_planner: order (script acts) + timing scaled to audio; must not reshuffle
- director_single_pass: encode/assembly only (no palette/order rewrite)

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


__all__ = [
    "ordered_script_scene_ids",
    "plan_scenes_by_id",
    "timing_scales_to_audio",
    "visual_plan_palette",
]
