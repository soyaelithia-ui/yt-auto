"""Low-CPU director assembly helpers (DIRECTOR_SINGLE_PASS)."""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple
from src.log import get_logger
logger = get_logger("director_single_pass")
__all__ = ["director_single_pass_enabled","director_xfade_enabled","is_procedural_engine_type","manifest_eligible_for_loop_single_pass","clamp_transition_sec","build_xfade_video_filters","build_scale_concat_video_filters","count_director_video_encodes","DirectorAssemblyPlan"]
def _env_flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1","true","yes","on")
def director_single_pass_enabled() -> bool:
    return _env_flag("DIRECTOR_SINGLE_PASS", "1")
def director_xfade_enabled() -> bool:
    return _env_flag("DIRECTOR_XFADE", "0")
def is_procedural_engine_type(engine_type: Optional[str]) -> bool:
    et = (engine_type or "").strip().lower()
    return et in ("pure_procedural_webgl","procedural_canvas2d","procedural","pure_procedural")
def manifest_eligible_for_loop_single_pass(scenes: Sequence[Any]) -> bool:
    if not scenes: return False
    return all(is_procedural_engine_type(getattr(sc, "engine_type", None)) for sc in scenes)
def clamp_transition_sec(dur_a: float, dur_b: float, requested: float = 0.75) -> float:
    shortest = min(float(dur_a), float(dur_b))
    return max(0.05, min(float(requested), shortest * 0.30))
def build_scale_concat_video_filters(n: int, width: int, height: int, fps: int) -> Tuple[List[str], str]:
    parts: List[str] = []; labels: List[str] = []
    for i in range(n):
        lab = f"[v{i}]"
        parts.append(f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps},setsar=1,format=yuv420p{lab}")
        labels.append(lab)
    if n == 1:
        parts.append(f"{labels[0]}null[vout]"); return parts, "[vout]"
    parts.append(f"{''.join(labels)}concat=n={n}:v=1:a=0[vout]"); return parts, "[vout]"
def build_xfade_video_filters(durations: Sequence[float], width: int, height: int, fps: int, transition_sec: float = 0.75, transition_name: str = "fade") -> Tuple[List[str], str, float]:
    n = len(durations)
    if n == 0: return [], "[vout]", 0.0
    parts: List[str] = []
    for i in range(n):
        parts.append(f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps},setsar=1,format=yuv420p[v{i}]")
    if n == 1:
        parts.append("[v0]null[vout]"); return parts, "[vout]", float(durations[0])
    cum = float(durations[0]); current = "[v0]"; out_dur = float(durations[0])
    for k in range(n - 1):
        t = clamp_transition_sec(durations[k], durations[k + 1], transition_sec)
        offset = max(0.0, cum - t)
        out_tag = f"[vx{k + 1}]" if k < n - 2 else "[vout]"
        parts.append(f"{current}[v{k + 1}]xfade=transition={transition_name}:duration={t:.3f}:offset={offset:.3f}{out_tag}")
        current = out_tag; cum += float(durations[k + 1]) - t; out_dur += float(durations[k + 1]) - t
    return parts, "[vout]", out_dur
@dataclass(frozen=True)
class DirectorAssemblyPlan:
    mode: str; scene_video_encodes: int; assembly_video_encodes: int
    master_video_encodes_if_ass: int; master_video_encodes_if_copy: int; notes: str
    def total_video_encodes(self, *, has_ass_burn: bool) -> int:
        master = self.master_video_encodes_if_ass if has_ass_burn else self.master_video_encodes_if_copy
        return self.scene_video_encodes + self.assembly_video_encodes + master
    def as_dict(self) -> Dict[str, Any]:
        return {"mode": self.mode, "scene_video_encodes": self.scene_video_encodes, "assembly_video_encodes": self.assembly_video_encodes, "master_video_encodes_if_ass": self.master_video_encodes_if_ass, "master_video_encodes_if_copy": self.master_video_encodes_if_copy, "notes": self.notes}
def count_director_video_encodes(*, n_scenes: int, single_pass: bool, use_xfade: bool, needs_scale: bool) -> DirectorAssemblyPlan:
    if not single_pass:
        return DirectorAssemblyPlan("legacy_multipass", max(0, n_scenes), 0, 1, 0, "Per-scene encodes → concat stream-copy → master.")
    if use_xfade:
        return DirectorAssemblyPlan("loop_filter_xfade", 0, 1, 1, 0, "One filter_complex xfade encode from catalog loops.")
    if needs_scale:
        return DirectorAssemblyPlan("loop_filter_concat", 0, 1, 1, 0, "One filter_complex scale+concat encode.")
    return DirectorAssemblyPlan("loop_stream_copy", 0, 0, 1, 0, "Stream-copy trim + concat demuxer -c:v copy (near-zero CPU).")
