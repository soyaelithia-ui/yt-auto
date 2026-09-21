"""D2 wall-clock budgets for mock profile baseline (moku-scp-shorts).

Baseline Live export 2026-09-06 tip 70b9223 (`/tmp/d2-baseline.json`):
  total wall 0.132s | peak RSS 87.16 MB | net ΔRSS +3.44 MB
  top: 9_video_rendering 0.031s (~24%), 5_tts 0.021s (~16%), 2_ingest 0.012s (~9%)
  No stage ≥25% wall on mock (leader 23.9%).

CI ceilings keep runner headroom while catching hung mock / stage blowups.
Hotspot reporting threshold (25%) is for prioritization, not a hard fail on mock.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

# Absolute mock ceilings (seconds)
MOCK_PIPELINE_WALL_SEC_MAX = float(os.environ.get("YT_MOCK_WALL_SEC", "5.0"))
MOCK_ANY_STAGE_WALL_SEC_MAX = float(os.environ.get("YT_MOCK_STAGE_WALL_SEC", "2.0"))

# Hotspot report threshold (percent of total wall)
HOTSPOT_WALL_PCT = float(os.environ.get("YT_HOTSPOT_WALL_PCT", "25.0"))

# Baseline reference (documentation / soft checks)
BASELINE_MOCK_TOTAL_WALL_SEC = 0.132
BASELINE_MOCK_TOP_STAGE = "9_video_rendering"
BASELINE_MOCK_TOP_WALL_PCT = 23.9


def _phase_rows(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    breakdown = summary.get("phase_breakdown")
    rows: list[dict[str, Any]] = []
    if isinstance(breakdown, list):
        for item in breakdown:
            if isinstance(item, dict):
                rows.append(item)
    phases = summary.get("phases")
    if not rows and isinstance(phases, dict):
        for name, item in phases.items():
            if isinstance(item, dict):
                rows.append({"stage": name, **item})
            else:
                rows.append({"stage": name, "duration_sec": float(item)})
    elif not rows and isinstance(phases, list):
        rows = [p for p in phases if isinstance(p, dict)]
    return rows


def stage_wall_ranking(summary: Mapping[str, Any]) -> list[tuple[str, float, float]]:
    """Return [(stage, duration_sec, pct_of_total), ...] sorted by wall desc."""
    total = float(summary.get("total_duration_sec") or 0.0) or 1e-9
    ranked: list[tuple[str, float, float]] = []
    for row in _phase_rows(summary):
        name = str(row.get("stage") or row.get("stage_name") or row.get("name") or "?")
        dur = float(row.get("duration_sec") or row.get("wall_sec") or 0.0)
        ranked.append((name, dur, 100.0 * dur / total))
    ranked.sort(key=lambda t: t[1], reverse=True)
    return ranked


def hotspots(summary: Mapping[str, Any], *, pct: float = HOTSPOT_WALL_PCT) -> list[tuple[str, float, float]]:
    return [row for row in stage_wall_ranking(summary) if row[2] >= pct]


def assert_mock_timing_gate(summary: Mapping[str, Any]) -> None:
    """Raise AssertionError if mock wall-clock regresses past CI ceilings."""
    total = float(summary.get("total_duration_sec") or 0.0)
    assert total > 0.0, "timing summary missing total_duration_sec"
    assert total <= MOCK_PIPELINE_WALL_SEC_MAX, (
        f"mock total wall {total:.3f}s > {MOCK_PIPELINE_WALL_SEC_MAX}s"
    )
    for name, dur, pct in stage_wall_ranking(summary):
        assert dur <= MOCK_ANY_STAGE_WALL_SEC_MAX, (
            f"stage {name} wall {dur:.3f}s > {MOCK_ANY_STAGE_WALL_SEC_MAX}s ({pct:.1f}% of run)"
        )
