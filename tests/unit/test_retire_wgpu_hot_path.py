"""SSOT PDF v2.4.0: production hot path must not construct WebGPU / NativeProceduralEngine."""
from __future__ import annotations

import sys


def test_multiscene_compositor_default_does_not_load_wgpu(monkeypatch):
    monkeypatch.delenv("ENABLE_NATIVE_PROCEDURAL", raising=False)
    for key in list(sys.modules):
        if key == "wgpu" or key.startswith("wgpu.") or key == "src.media.native_procedural" or key.startswith("src.media.native_procedural."):
            del sys.modules[key]
        if key in ("src.media.compositor", "src.media.proc_engine", "src.media.hybrid_engine"):
            del sys.modules[key]

    from src.media.compositor import MultiSceneCompositor

    compositor = MultiSceneCompositor()
    assert compositor.procedural_engine.renderer is None
    assert "src.media.native_procedural" not in sys.modules
    assert "wgpu" not in sys.modules


def test_scenic_detector_does_not_import_native_procedural():
    for key in list(sys.modules):
        if key == "src.core.scenic_detector" or key.startswith("src.core.scenic_detector."):
            del sys.modules[key]
        if key == "src.media.native_procedural" or key.startswith("src.media.native_procedural."):
            del sys.modules[key]

    import src.core.scenic_detector as sd

    assert "src.media.native_procedural" not in sys.modules
    assert "dark_forest" in sd.VALID_ARCHETYPES
    assert "maritime_lighthouse" in sd.VALID_ARCHETYPES


def test_loop_worker_ffmpeg_technology_label(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.media.loop_worker import LoopSynthesizerWorker

    worker = LoopSynthesizerWorker(db_path=str(tmp_path / "loops.db"), renderer=None)
    rec = worker.synthesize_on_demand(category="scp", orientation="vertical", seed=123, duration_sec=0.5, fps=15)
    assert rec.technology == "ffmpeg_lavfi"
