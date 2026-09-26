"""Stage 9 mock harness must not inflate wall-clock vs lavfi/stream-copy reality."""
from pathlib import Path

def test_benchmark_mock_video_rendering_is_light():
    src = Path("src/core/profiling/benchmarking.py").read_text(encoding="utf-8")
    idx = src.index("elif stage == CanonicalStage.VIDEO_RENDERING:")
    block = src[idx : idx + 400]
    assert "0.03" not in block
    assert "2 * 1024 * 1024" not in block
    assert "0.008" in block


def test_scene_asset_tracker_outside_render_phase():
    pipe = Path("src/pipeline.py").read_text(encoding="utf-8")
    assert "outside stage-9 timer" in pipe
    assert pipe.count("SceneAssetTracker(repository=repository)") == 1
