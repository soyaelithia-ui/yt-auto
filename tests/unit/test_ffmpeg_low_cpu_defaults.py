"""Guardrails for low-CPU FFmpeg defaults (stream-copy / veryfast / no default rawvideo)."""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.media.encode_defaults import (
    default_ffmpeg_threads,
    default_render_crf,
    default_render_preset,
    loop_matches_target_geometry,
)


def test_default_render_preset_is_veryfast(monkeypatch):
    monkeypatch.delenv("RENDER_PRESET", raising=False)
    assert default_render_preset() == "veryfast"


def test_default_render_crf_is_21(monkeypatch):
    monkeypatch.delenv("RENDER_CRF", raising=False)
    assert default_render_crf() == 21


def test_render_env_overrides(monkeypatch):
    monkeypatch.setenv("RENDER_PRESET", "faster")
    monkeypatch.setenv("RENDER_CRF", "20")
    monkeypatch.setenv("FFMPEG_THREADS", "2")
    assert default_render_preset() == "faster"
    assert default_render_crf() == 20
    assert default_ffmpeg_threads() == 2


def test_loop_engine_compose_defaults_are_low_cpu(monkeypatch):
    monkeypatch.delenv("RENDER_PRESET", raising=False)
    monkeypatch.delenv("RENDER_CRF", raising=False)
    from src.media.loop_engine import LoopVideoEngine

    sig = inspect.signature(LoopVideoEngine.compose)
    # None defaults resolve to encode_defaults at runtime
    assert sig.parameters["preset"].default is None
    assert sig.parameters["crf"].default is None


def test_loop_engine_build_filter_uses_veryfast(monkeypatch):
    monkeypatch.delenv("RENDER_PRESET", raising=False)
    monkeypatch.delenv("RENDER_CRF", raising=False)
    from src.media.loop_engine import LoopVideoEngine

    engine = LoopVideoEngine()
    # build_filter_graph needs real-ish paths; call the kwargs resolution via a thin stub
    # by inspecting source defaults used in build methods
    src = Path("src/media/loop_engine.py").read_text(encoding="utf-8")
    assert 'kwargs.get("preset", default_render_preset())' in src
    assert 'kwargs.get("crf", default_render_crf())' in src
    assert 'preset: str = "fast"' not in src
    assert 'crf: int = 23' not in src


def test_pipeline_rejects_slow_hot_path_literal():
    """Multi-scene render must not hardcode preset=slow (CPU disaster)."""
    src = Path("src/pipeline.py").read_text(encoding="utf-8")
    assert 'preset="slow"' not in src
    assert "default_render_preset()" in src


def test_horizontal_stream_copy_policy_in_pipeline():
    src = Path("src/pipeline.py").read_text(encoding="utf-8")
    assert 'stream_copy_mode = bool(lane.orientation == "horizontal" and not burn_subtitles)' in src
    assert "stream_copy=stream_copy_mode" in src


def test_loop_stream_copy_cmd_uses_copy_codec():
    from src.media.loop_engine import LoopVideoEngine

    engine = LoopVideoEngine()
    cmd = engine.build_stream_copy_composition_cmd(
        concat_list_path=Path("/tmp/concat.txt"),
        audio_path=Path("/tmp/a.wav"),
        bgm_path=None,
        duration_sec=10.0,
        output_video_path=Path("/tmp/out.mp4"),
    )
    assert "-c:v" in cmd
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert "libx264" not in cmd


def test_no_default_rawvideo_outside_force_flags():
    """Hybrid default path must stay behind FORCE_PILLOW_*; source-level guard."""
    hybrid = Path("src/media/hybrid_engine.py").read_text(encoding="utf-8")
    assert "force_pillow_hybrid_frames_enabled" in hybrid
    assert "FORCE_PILLOW_HYBRID_FRAMES" in hybrid
    # Default branch calls ffmpeg camera path, not rawvideo, unless force flag
    assert "_render_scene_ffmpeg_camera" in hybrid
    assert "use_pillow_frames = force_pillow_hybrid_frames_enabled" in hybrid


def test_lib_video_crf_default_matches_compose(monkeypatch):
    monkeypatch.delenv("RENDER_CRF", raising=False)
    monkeypatch.delenv("RENDER_PRESET", raising=False)
    # Re-import would be sticky; assert source default string instead
    src = Path("lib/video.py").read_text(encoding="utf-8")
    assert 'os.environ.get("RENDER_CRF", "21")' in src
    assert 'os.environ.get("RENDER_PRESET", "veryfast")' in src


def test_loop_matches_target_geometry_uses_probe(monkeypatch):
    """Shared helper must agree with PR #11 compositor geometry predicate."""
    from types import SimpleNamespace

    class FakeProbe:
        def __init__(self, w, h):
            self.primary_video = SimpleNamespace(width=w, height=h)
            self.video_streams = [self.primary_video]

    def fake_probe(path):
        return FakeProbe(1920, 1080)

    monkeypatch.setattr("lib.ffmpeg.probe_media", fake_probe)
    assert loop_matches_target_geometry("/tmp/loop.mp4", 1920, 1080) is True
    assert loop_matches_target_geometry("/tmp/loop.mp4", 1080, 1920) is False


def test_proc_engine_stream_copy_aligned_with_director_pr11():
    """Guardrail: procedural no-sub path shares geometry helper + PR #11 copy/scale shape."""
    src = Path("src/media/proc_engine.py").read_text(encoding="utf-8")
    assert "loop_matches_target_geometry" in src
    assert "-stream_loop" in src
    assert '"-c:v", "copy"' in src
    assert "force_original_aspect_ratio=increase" in src
    assert '"-preset", "faster"' not in src
    assert "default_render_preset()" in src
