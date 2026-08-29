"""Unit tests verifying exception cleanup and process killing in render modules."""

from pathlib import Path
import subprocess
from unittest.mock import MagicMock, call, patch

from PIL import Image
import pytest

from src.compositing.stream_renderer import DirectStreamCompositor
from src.core.lifecycle import get_tracked_pids
from src.media.proc_engine import ProceduralVideoEngine
from src.media.subtitles import SubtitleCue, apply_code_subtitles_to_video
from src.media.web_renderer import RenderSpec, WebVideoRenderer
from src.scene_manifest import SceneConfig, ProceduralConfig


def test_proc_engine_exception_cleans_up_dual_popen(tmp_path):
    """Verify that proc_engine cleans up proc_in and proc_out when frame loop fails."""
    engine = ProceduralVideoEngine()

    mock_proc_in = MagicMock()
    mock_proc_in.pid = 41001
    mock_proc_in.poll.return_value = None
    mock_proc_in.stdout.read.return_value = b"\x00" * (1080 * 1920 * 3)

    mock_proc_out = MagicMock()
    mock_proc_out.pid = 41002
    mock_proc_out.poll.return_value = None

    mock_drawer = MagicMock()
    mock_drawer.draw_on_frame.side_effect = RuntimeError("Crash inside proc_engine loop")

    dummy_loop = tmp_path / "dummy_loop.mp4"
    dummy_loop.write_bytes(b"dummy video")

    mock_scene = SceneConfig(
        scene_id="s1",
        scene_index=1,
        start_sec=0.0,
        narration="test",
        duration_sec=3.0,
        environment_name="test_env",
        tension_level=1,
        engine_type="pure_procedural_webgl",
        procedural_config=ProceduralConfig(template_name="test"),
    )

    with patch("src.media.proc_engine.subprocess.Popen", side_effect=[mock_proc_in, mock_proc_out]), \
         patch("src.media.subtitles.CodeSubtitleDrawer", return_value=mock_drawer), \
         patch("src.media.proc_engine.probe_media", return_value=MagicMock(duration=3.0, primary_video=None)), \
         patch.object(engine.catalog, "get_best_loop", return_value=MagicMock(file_path=str(dummy_loop))):

        with pytest.raises(RuntimeError, match="Crash inside proc_engine loop"):
            engine.render_scene_segment(
                scene=mock_scene,
                width=1080,
                height=1920,
                fps=30,
                lane_id="lane1",
                output_mp4=tmp_path / "out.mp4",
                crf=23,
                subtitle_cues=[SubtitleCue(words=[], start_sec=0.0, end_sec=1.0, full_text="test")],
                scene_start_sec=0.0,
            )

    # Verify both processes were terminated and waited on
    mock_proc_in.terminate.assert_called()
    mock_proc_out.terminate.assert_called()
    mock_proc_in.wait.assert_called()
    mock_proc_out.wait.assert_called()
    assert 41001 not in get_tracked_pids()
    assert 41002 not in get_tracked_pids()


def test_subtitles_exception_cleans_up_dual_popen(tmp_path):
    """Verify that apply_code_subtitles_to_video cleans up proc_in and proc_out on failure."""
    mock_proc_in = MagicMock()
    mock_proc_in.pid = 42001
    mock_proc_in.poll.return_value = None
    mock_proc_in.stdout.read.return_value = b"\x00" * (1080 * 1920 * 3)

    mock_proc_out = MagicMock()
    mock_proc_out.pid = 42002
    mock_proc_out.poll.return_value = None

    mock_drawer = MagicMock()
    mock_drawer.draw_on_frame.side_effect = RuntimeError("Crash in subtitle drawer")

    with patch("src.media.subtitles.subprocess.Popen", side_effect=[mock_proc_in, mock_proc_out]):
        with pytest.raises(RuntimeError, match="Crash in subtitle drawer"):
            apply_code_subtitles_to_video(
                input_mp4=tmp_path / "in.mp4",
                output_mp4=tmp_path / "out.mp4",
                subtitle_cues=[SubtitleCue(words=[], start_sec=0.0, end_sec=1.0, full_text="hello")],
                scene_start_sec=0.0,
                width=1080,
                height=1920,
                fps=30,
                drawer=mock_drawer,
            )

    mock_proc_in.terminate.assert_called()
    mock_proc_out.terminate.assert_called()
    mock_proc_in.wait.assert_called()
    mock_proc_out.wait.assert_called()
    assert 42001 not in get_tracked_pids()
    assert 42002 not in get_tracked_pids()


def test_stream_renderer_exception_cleans_up_ffmpeg_and_browser(tmp_path):
    """Verify that stream_renderer cleans up FFmpeg and closes browser on exception."""
    compositor = DirectStreamCompositor()

    mock_proc = MagicMock()
    mock_proc.pid = 43001
    mock_proc.poll.return_value = None

    mock_browser = MagicMock()
    mock_page = MagicMock()
    mock_page.screenshot.side_effect = RuntimeError("Browser screenshot failed")
    mock_browser.new_page.return_value = mock_page

    mock_playwright_ctx = MagicMock()
    mock_playwright_ctx.__enter__.return_value.chromium.launch.return_value = mock_browser

    mock_contract = MagicMock()
    mock_contract.scenes = []

    with patch("src.compositing.stream_renderer.subprocess.Popen", return_value=mock_proc), \
         patch("src.compositing.stream_renderer.sync_playwright", return_value=mock_playwright_ctx), \
         patch.object(compositor.shader_renderer, "build_runtime_html", return_value="<html></html>"):

        with pytest.raises(RuntimeError, match="Browser screenshot failed"):
            compositor.render_and_mux(
                script_contract=mock_contract,
                output_mp4_path=tmp_path / "out.mp4",
                duration_sec=1.0,
                total_frames=30,
                width=1080,
                height=1920,
                fps=30,
            )

    mock_proc.terminate.assert_called()
    mock_browser.close.assert_called()
    assert 43001 not in get_tracked_pids()


def test_web_renderer_exception_cleans_up_ffmpeg_and_browser(tmp_path):
    """Verify that web_renderer cleans up FFmpeg and browser on exception."""
    renderer = WebVideoRenderer()

    mock_proc = MagicMock()
    mock_proc.pid = 44001
    mock_proc.poll.return_value = None

    mock_browser = MagicMock()
    mock_page = MagicMock()
    mock_page.evaluate.side_effect = RuntimeError("Shader execution failed")
    mock_browser.new_page.return_value = mock_page

    mock_playwright_ctx = MagicMock()
    mock_playwright_ctx.__enter__.return_value.chromium.launch.return_value = mock_browser

    mock_spec = RenderSpec(
        category="classified_terminal",
        duration_sec=2.0,
        fps=30,
        width=1080,
        height=1920,
        seed=123,
        orientation="vertical",
        output_path=tmp_path / "out.mp4",
    )

    template_file = tmp_path / "template.html"
    template_file.write_text("<html></html>")

    with patch("src.media.web_renderer.subprocess.Popen", return_value=mock_proc), \
         patch("playwright.sync_api.sync_playwright", return_value=mock_playwright_ctx), \
         patch.object(renderer, "resolve_template_path", return_value=template_file):

        with pytest.raises(RuntimeError, match="Shader execution failed"):
            renderer.render_loop(
                spec=mock_spec,
            )

    mock_proc.terminate.assert_called()
    mock_browser.close.assert_called()
    assert 44001 not in get_tracked_pids()


def test_stream_renderer_backpressure_timeout():
    """Verify that _write_frame_with_backpressure exits and returns False when cumulative deadline expires."""
    compositor = DirectStreamCompositor()
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.stdin = MagicMock()
    mock_proc.stdin.fileno.return_value = 10

    # select always returns not writable
    with patch("select.select", return_value=([], [], [])):
        res = compositor._write_frame_with_backpressure(mock_proc, b"dummy_frame", timeout=0.05)
        assert res is False


def test_proc_engine_fallback_loop_cleanup_on_exception(tmp_path):
    """Verify that _generate_fallback_loop registers and cleans up proc on failure."""
    engine = ProceduralVideoEngine()

    mock_proc = MagicMock()
    mock_proc.pid = 45001
    mock_proc.poll.return_value = None
    mock_proc.stdin = MagicMock()
    mock_proc.stdin.write.side_effect = BrokenPipeError("Broken pipe during fallback loop")

    with patch("src.media.proc_engine.subprocess.Popen", return_value=mock_proc):
        with pytest.raises(BrokenPipeError):
            engine._generate_fallback_loop(
                category="classified_terminal",
                width=100,
                height=100,
                fps=10,
                duration_sec=0.5,
                out_path=tmp_path / "fallback.mp4",
            )

    mock_proc.terminate.assert_called()
    mock_proc.wait.assert_called()
    assert 45001 not in get_tracked_pids()

