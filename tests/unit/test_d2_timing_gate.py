"""CI gate: D2 mock wall-clock budgets for moku-scp-shorts profile."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.rss_budgets import LIVE_SMOKE_PEAK_RSS_MB_MAX, LIVE_STAGE8_SELECT_DELTA_MB_MAX, LIVE_STAGE9_LAVFI_DELTA_MB_MAX
from src.core.timing_budgets import (
    BASELINE_MOCK_TOP_STAGE,
    HOTSPOT_WALL_PCT,
    MOCK_PIPELINE_WALL_SEC_MAX,
    assert_mock_timing_gate,
    hotspots,
    stage_wall_ranking,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "d2_baseline_mock.json"


@pytest.fixture(scope="module")
def baseline_summary() -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload.get("mock_mode") is True
    summaries = payload["summaries"]
    assert summaries
    return summaries[-1]


def test_fixture_timing_gate_passes(baseline_summary: dict):
    assert_mock_timing_gate(baseline_summary)
    assert baseline_summary["total_duration_sec"] < MOCK_PIPELINE_WALL_SEC_MAX
    assert baseline_summary["peak_rss_mb"] <= LIVE_SMOKE_PEAK_RSS_MB_MAX


def test_fixture_rss_stage_deltas_within_live_gate(baseline_summary: dict):
    rows = {r.get("stage") or r.get("stage_name"): r for r in baseline_summary["phase_breakdown"]}
    d8 = float(rows["8_loop_scene"]["rss_delta_mb"])
    d9 = float(rows["9_video_rendering"]["rss_delta_mb"])
    assert d8 <= LIVE_STAGE8_SELECT_DELTA_MB_MAX
    assert d9 <= LIVE_STAGE9_LAVFI_DELTA_MB_MAX


def test_fixture_no_hotspot_at_25pct_on_mock(baseline_summary: dict):
    """Mock baseline: leader ~24% — no stage crosses the 25% report threshold."""
    hs = hotspots(baseline_summary, pct=HOTSPOT_WALL_PCT)
    assert hs == []
    top_name, top_dur, top_pct = stage_wall_ranking(baseline_summary)[0]
    assert top_name == BASELINE_MOCK_TOP_STAGE
    assert top_pct < HOTSPOT_WALL_PCT
    assert top_dur < 1.0


def test_live_mock_profile_respects_timing_gate():
    """Run one mock benchmark cycle and enforce wall ceilings (needs repo imports)."""
    from src.core.profiling import run_benchmark_cycle

    summaries = run_benchmark_cycle(
        channel="moku",
        lane_id="moku-scp-shorts",
        iterations=1,
        mock_mode=True,
        stages=None,
        db_path=":memory:",
    )
    assert summaries
    summary = summaries[-1]
    payload = summary.to_dict() if hasattr(summary, "to_dict") else summary
    if not isinstance(payload, dict):
        pytest.fail(f"unexpected summary type: {type(payload)}")
    assert_mock_timing_gate(payload)
    assert float(payload.get("peak_rss_mb") or 0) <= LIVE_SMOKE_PEAK_RSS_MB_MAX
