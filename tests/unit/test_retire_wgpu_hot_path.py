"""SSOT PDF v2.4.0: production hot path must not construct WebGPU / NativeProceduralEngine."""
from __future__ import annotations

import sys


def test_enable_native_procedural_defaults_off(monkeypatch):
    """Production default: ENABLE_NATIVE_PROCEDURAL unset/empty/0 => hot path disabled."""
    monkeypatch.delenv("ENABLE_NATIVE_PROCEDURAL", raising=False)
    # Ensure import sees a clean module (helper reads os.environ at call time).
    for key in list(sys.modules):
        if key in ("src.media.compositor",) or key.startswith("src.media.compositor."):
            del sys.modules[key]

    from src.media.compositor import _native_procedural_hot_path_enabled

    assert _native_procedural_hot_path_enabled() is False

    monkeypatch.setenv("ENABLE_NATIVE_PROCEDURAL", "0")
    assert _native_procedural_hot_path_enabled() is False

    monkeypatch.setenv("ENABLE_NATIVE_PROCEDURAL", "")
    assert _native_procedural_hot_path_enabled() is False


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


def test_beats_stream_copy_cmd_uses_concat_demuxer_and_cv_copy():
    """Theology dogma 2: beats default composition cmd must be concat demuxer + -c:v copy."""
    from pathlib import Path

    from src.media.loop_engine import LoopVideoEngine

    engine = LoopVideoEngine()
    concat_list = Path("/tmp/yt_auto_fake_concat.txt")
    audio = Path("/tmp/yt_auto_fake_audio.wav")
    out = Path("/tmp/yt_auto_fake_out.mp4")
    cmd = engine.build_stream_copy_composition_cmd(
        concat_list_path=concat_list,
        audio_path=audio,
        bgm_path=None,
        duration_sec=30.0,
        output_video_path=out,
    )
    assert "-f" in cmd and "concat" in cmd
    assert cmd[cmd.index("-f") + 1] == "concat"
    # Video stream-copy invariant
    assert "-c:v" in cmd
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert "libx264" not in cmd
