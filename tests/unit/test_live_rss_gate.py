"""CI gate: live select + lavfi synth must stay near-zero RSS (stages 8–9).

Budgets from Live smoke (#45): process ~84–88 MB, stage deltas <+1 MB.
Fails the suite if parent RSS regresses toward compositor/numpy bombs.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.core.guard import read_vm_rss_bytes, reset_module_watchdog
from src.core.rss_budgets import (
    COMPOSE_SMALL_MEM_LIMIT_MB,
    LIVE_SMOKE_PEAK_RSS_MB_MAX,
    LIVE_SMOKE_PROCESS_RSS_MB,
    LIVE_STAGE8_SELECT_DELTA_MB_MAX,
    LIVE_STAGE9_LAVFI_DELTA_MB_MAX,
)
from src.media.loop_engine import LoopVideoEngine


def _rss_mb() -> float:
    return read_vm_rss_bytes() / (1024 * 1024)


@pytest.fixture(autouse=True)
def _reset_watchdog():
    reset_module_watchdog()
    yield
    reset_module_watchdog()


def test_rss_budgets_under_compose_small_ceiling():
    assert LIVE_SMOKE_PROCESS_RSS_MB < COMPOSE_SMALL_MEM_LIMIT_MB
    assert LIVE_SMOKE_PEAK_RSS_MB_MAX <= COMPOSE_SMALL_MEM_LIMIT_MB
    assert LIVE_STAGE8_SELECT_DELTA_MB_MAX < 64
    assert LIVE_STAGE9_LAVFI_DELTA_MB_MAX < 64


def test_live_select_empty_catalog_rss_delta(tmp_path: Path):
    """Stage 8 live select on empty catalog must not inflate parent RSS."""
    loops = tmp_path / "loops"
    loops.mkdir()
    engine = LoopVideoEngine(loops_root_dir=loops, catalog=None)

    before = _rss_mb()
    info = engine._live_rss_checkpoint("8_loop_scene_live_select")
    # Empty FS + no catalog → fallback path; still must be cheap.
    try:
        engine.resolve_loop_video(
            category="scp",
            asset_root=loops,
            allow_fallback=False,
            seed=1,
            orientation="vertical",
        )
    except Exception:
        pass
    after = engine._live_rss_checkpoint("8_loop_scene_live_select_done")
    end = _rss_mb()

    delta = end - before
    assert delta <= LIVE_STAGE8_SELECT_DELTA_MB_MAX, (
        f"stage-8 select ΔRSS {delta:.1f} MB > {LIVE_STAGE8_SELECT_DELTA_MB_MAX} MB"
    )
    assert end <= LIVE_SMOKE_PEAK_RSS_MB_MAX, (
        f"stage-8 peak RSS {end:.1f} MB > {LIVE_SMOKE_PEAK_RSS_MB_MAX} MB"
    )
    assert info.get("disabled") is not True or "observed_bytes" in after or after.get("disabled")


def test_live_lavfi_synth_2s_rss_delta(tmp_path: Path):
    """Stage 9 lavfi gradients 2s (Live smoke) must keep parent ΔRSS tiny."""
    out = tmp_path / "lavfi_2s.mp4"
    width, height, duration, fps = 1080, 1920, 2.0, 30
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        (
            f"gradients=s={width}x{height}:d={duration}:r={fps}"
            f":c0=0x1a252f:c1=0x34495e:x0=0:y0=0:x1={width}:y1={height}"
            f":type=radial:speed=0.02"
        ),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "ultrafast",
        "-crf",
        "28",
        "-frames:v",
        "60",
        str(out),
    ]

    before = _rss_mb()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    after = _rss_mb()
    delta = after - before

    assert proc.returncode == 0, f"ffmpeg lavfi failed: {proc.stderr[-400:]}"
    assert out.is_file() and out.stat().st_size > 0
    assert delta <= LIVE_STAGE9_LAVFI_DELTA_MB_MAX, (
        f"stage-9 lavfi ΔRSS {delta:.1f} MB > {LIVE_STAGE9_LAVFI_DELTA_MB_MAX} MB"
    )
    assert after <= LIVE_SMOKE_PEAK_RSS_MB_MAX, (
        f"stage-9 peak RSS {after:.1f} MB > {LIVE_SMOKE_PEAK_RSS_MB_MAX} MB"
    )


def test_live_synth_worker_rss_delta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """LoopSynthesizerWorker lavfi path: parent RSS must not balloon."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "assets" / "loops" / "procedural" / "scp").mkdir(parents=True)

    from src.media.loop_worker import LoopSynthesizerWorker

    worker = LoopSynthesizerWorker(db_path=str(tmp_path / "loops.db"))
    before = _rss_mb()
    rec = worker.synthesize_on_demand(
        category="scp",
        orientation="vertical",
        seed=42,
        duration_sec=2.0,
        fps=30,
    )
    after = _rss_mb()
    delta = after - before

    assert Path(rec.file_path).is_file()
    assert rec.technology == "ffmpeg_lavfi"
    assert delta <= LIVE_STAGE9_LAVFI_DELTA_MB_MAX, (
        f"worker lavfi ΔRSS {delta:.1f} MB > {LIVE_STAGE9_LAVFI_DELTA_MB_MAX} MB"
    )
    assert after <= LIVE_SMOKE_PEAK_RSS_MB_MAX


def test_live_rss_checkpoint_records_observed_bytes():
    engine = LoopVideoEngine(
        loops_root_dir=Path(tempfile.mkdtemp()),
        catalog=MagicMock(),
    )
    info = engine._live_rss_checkpoint("8_loop_scene_live_select")
    if info.get("disabled"):
        pytest.skip("memory checkpoint disabled in this environment")
    observed = info.get("observed_bytes") or info.get("rss_bytes") or 0
    assert int(observed) > 0
