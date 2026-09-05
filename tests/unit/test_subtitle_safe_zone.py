"""
tests/unit/test_subtitle_safe_zone.py - Tests for Stream-Copy Preservation and Subtitle Filter Gating.

Verifies:
- LoopVideoEngine preserves stream-copy (-c:v copy) when subtitles are absent or inactive,
  and injects escaped filter when active.
- MultiSceneCompositor._master_assembly preserves video_copy=True and omits ass= filter
  when subtitles are inactive, and injects escaped filter when active.
- MultiActVideoRenderer omits subtitles= filter when inactive and injects escaped filter when active.
- MultiActVideoRenderer.generate_ass_subtitles complies with safe margins and font sizing.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.media.loop_engine import LoopVideoEngine
from src.media.compositor import MultiSceneCompositor
from src.media.multi_act_renderer import MultiActVideoRenderer, NarrativeSceneAct
from src.media.subtitles_ass import calculate_safe_margins, calculate_font_size


# ==============================================================================
# Helper fixtures for subtitle files
# ==============================================================================

@pytest.fixture
def empty_ass_file(tmp_path: Path) -> Path:
    p = tmp_path / "zero_byte.ass"
    p.write_bytes(b"")
    return p


@pytest.fixture
def header_only_ass_file(tmp_path: Path) -> Path:
    p = tmp_path / "header_only.ass"
    p.write_text(
        "[Script Info]\nTitle: Test\n\n[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default,Arial\n\n[Events]\nFormat: Layer, Start, End, Text\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def whitespace_dialogue_ass_file(tmp_path: Path) -> Path:
    p = tmp_path / "whitespace.ass"
    p.write_text(
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,   \n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def active_ass_file(tmp_path: Path) -> Path:
    # Path with colon and single quote to test escaping
    p = tmp_path / "sub's:active.ass"
    p.write_text(
        "[Script Info]\nTitle: Active\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,Active subtitle dialogue\n",
        encoding="utf-8",
    )
    return p


# ==============================================================================
# 2.1 RED: LoopVideoEngine Stream-Copy and Filter Gating
# ==============================================================================

def test_loop_video_engine_build_render_command_inactive_subtitles(
    tmp_path: Path,
    empty_ass_file: Path,
    header_only_ass_file: Path,
    whitespace_dialogue_ass_file: Path,
):
    """2.1 RED: LoopVideoEngine.build_render_command omits subtitle filter when subtitle file is inactive."""
    engine = LoopVideoEngine()
    video_paths = [tmp_path / "dummy.mp4"]
    audio_path = tmp_path / "audio.wav"
    output_path = tmp_path / "out.mp4"

    for inactive_sub in [None, empty_ass_file, header_only_ass_file, whitespace_dialogue_ass_file]:
        cmd = engine.build_render_command(
            video_paths=video_paths,
            audio_path=audio_path,
            output_path=output_path,
            target_duration=5.0,
            include_subtitles=True,
            subtitle_path=inactive_sub,
        )
        cmd_str = " ".join(cmd)
        assert "ass=" not in cmd_str, f"Found ass= filter with inactive sub: {inactive_sub}"
        assert "subtitles=" not in cmd_str, f"Found subtitles= filter with inactive sub: {inactive_sub}"
        assert "[vbase]null[vout];" in cmd_str


def test_loop_video_engine_build_render_command_active_subtitles(
    tmp_path: Path, active_ass_file: Path
):
    """2.1 RED: LoopVideoEngine.build_render_command injects escaped filter when active dialogue exists."""
    engine = LoopVideoEngine()
    video_paths = [tmp_path / "dummy.mp4"]
    audio_path = tmp_path / "audio.wav"
    output_path = tmp_path / "out.mp4"

    cmd = engine.build_render_command(
        video_paths=video_paths,
        audio_path=audio_path,
        output_path=output_path,
        target_duration=5.0,
        include_subtitles=True,
        subtitle_path=active_ass_file,
    )
    cmd_str = " ".join(cmd)
    assert "ass=" in cmd_str
    # Escaped colon and single quote in path: sub\'s\:active.ass
    assert "sub\\'s\\:active.ass" in cmd_str


def test_loop_video_engine_compose_stream_copy_preserved_on_inactive_subtitles(
    tmp_path: Path, header_only_ass_file: Path
):
    """2.1 RED: LoopVideoEngine.compose preserves stream-copy (-c:v copy) when subtitles are inactive."""
    engine = LoopVideoEngine()
    fake_video = tmp_path / "loop.mp4"
    fake_video.write_bytes(b"dummy")
    fake_audio = tmp_path / "audio.wav"
    fake_audio.write_bytes(b"dummy")
    out_video = tmp_path / "output.mp4"

    mock_probe = MagicMock()
    mock_probe.duration = 10.0
    mock_probe.video_streams = [MagicMock(width=1920, height=1080)]

    captured_cmds: list[list[str]] = []

    def fake_run_ffmpeg(cmd, **kwargs):
        captured_cmds.append(list(cmd))
        out_video.write_bytes(b"rendered")
        return MagicMock(returncode=0)

    with patch("src.media.loop_engine.probe_media", return_value=mock_probe), \
         patch("src.media.loop_engine.run_ffmpeg", side_effect=fake_run_ffmpeg):

        engine.compose(
            audio_path=fake_audio,
            output_video_path=out_video,
            video_loop_path=fake_video,
            orientation="horizontal",
            stream_copy=True,
            include_subtitles=True,
            subtitle_path=header_only_ass_file,
        )

    assert len(captured_cmds) == 1
    stream_cmd = captured_cmds[0]
    assert "-c:v" in stream_cmd
    assert stream_cmd[stream_cmd.index("-c:v") + 1] == "copy"
    assert "libx264" not in stream_cmd


# ==============================================================================
# 2.2 RED: MultiSceneCompositor Stream-Copy and Filter Gating
# ==============================================================================

def test_multi_scene_compositor_master_assembly_inactive_subtitles(
    tmp_path: Path,
    empty_ass_file: Path,
    header_only_ass_file: Path,
    whitespace_dialogue_ass_file: Path,
):
    """2.2 RED: MultiSceneCompositor._master_assembly preserves video_copy=True and omits ass= when subtitles inactive."""
    compositor = MultiSceneCompositor()
    video_input = tmp_path / "in.mp4"
    video_input.write_bytes(b"dummy")
    output_mp4 = tmp_path / "out.mp4"

    for inactive_sub in [None, empty_ass_file, header_only_ass_file, whitespace_dialogue_ass_file]:
        captured_cmds: list[list[str]] = []

        def fake_run_ffmpeg(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            return MagicMock(returncode=0)

        with patch("src.media.compositor.run_ffmpeg", side_effect=fake_run_ffmpeg):
            compositor._master_assembly(
                video_input=video_input,
                narration_audio=None,
                music_audio=None,
                music_volume=0.0,
                subtitle_path=inactive_sub,
                total_duration=5.0,
                width=1920,
                height=1080,
                crf=23,
                preset="veryfast",
                output_mp4=output_mp4,
            )

        assert len(captured_cmds) == 1
        cmd = captured_cmds[0]
        assert "-c:v" in cmd
        assert cmd[cmd.index("-c:v") + 1] == "copy"
        cmd_str = " ".join(cmd)
        assert "ass=" not in cmd_str
        assert "subtitles=" not in cmd_str


def test_multi_scene_compositor_master_assembly_active_subtitles(
    tmp_path: Path, active_ass_file: Path
):
    """2.2 RED: MultiSceneCompositor._master_assembly re-encodes and injects escaped ass= filter when active."""
    compositor = MultiSceneCompositor()
    video_input = tmp_path / "in.mp4"
    video_input.write_bytes(b"dummy")
    output_mp4 = tmp_path / "out.mp4"

    captured_cmds: list[list[str]] = []

    def fake_run_ffmpeg(cmd, **kwargs):
        captured_cmds.append(list(cmd))
        return MagicMock(returncode=0)

    with patch("src.media.compositor.run_ffmpeg", side_effect=fake_run_ffmpeg):
        compositor._master_assembly(
            video_input=video_input,
            narration_audio=None,
            music_audio=None,
            music_volume=0.0,
            subtitle_path=active_ass_file,
            total_duration=5.0,
            width=1920,
            height=1080,
            crf=23,
            preset="veryfast",
            output_mp4=output_mp4,
        )

    assert len(captured_cmds) == 1
    cmd = captured_cmds[0]
    assert "-c:v" in cmd
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    cmd_str = " ".join(cmd)
    assert "ass=" in cmd_str
    # Escaped path in filter argument
    assert "sub\\'s\\:active.ass" in cmd_str


# ==============================================================================
# 2.3 RED: MultiActVideoRenderer Subtitle Filter Gating & Safe Margins
# ==============================================================================

def test_multi_act_video_renderer_composite_omits_inactive_subtitles(
    tmp_path: Path,
    empty_ass_file: Path,
    header_only_ass_file: Path,
    whitespace_dialogue_ass_file: Path,
):
    """2.3 RED: MultiActVideoRenderer.composite_multi_act_video omits subtitles= filter when inactive."""
    renderer = MultiActVideoRenderer()
    acts = [
        NarrativeSceneAct(act_index=0, start_sec=0.0, duration_sec=5.0, title="Act 1", theme_category="scp"),
    ]
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"dummy")
    output_video = tmp_path / "out.mp4"

    for inactive_sub in [None, empty_ass_file, header_only_ass_file, whitespace_dialogue_ass_file]:
        captured_cmds: list[list[str]] = []

        def fake_run_ffmpeg(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            output_video.write_bytes(b"done")
            return MagicMock(returncode=0)

        with patch("src.media.multi_act_renderer.run_ffmpeg", side_effect=fake_run_ffmpeg), \
             patch.object(renderer, "resolve_loop_for_theme", return_value=tmp_path / "dummy_loop.mp4"):
            renderer.composite_multi_act_video(
                acts=acts,
                audio_path=audio_path,
                output_video=output_video,
                total_duration=5.0,
                is_vertical=False,
                ass_subtitles=inactive_sub,
            )

        assert len(captured_cmds) == 1
        cmd_str = " ".join(captured_cmds[0])
        assert "subtitles=" not in cmd_str
        assert "null[vout]" in cmd_str


def test_multi_act_video_renderer_composite_active_subtitles(
    tmp_path: Path, active_ass_file: Path
):
    """2.3 RED: MultiActVideoRenderer.composite_multi_act_video injects escaped subtitles= filter when active."""
    renderer = MultiActVideoRenderer()
    acts = [
        NarrativeSceneAct(act_index=0, start_sec=0.0, duration_sec=5.0, title="Act 1", theme_category="scp"),
    ]
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"dummy")
    output_video = tmp_path / "out.mp4"

    captured_cmds: list[list[str]] = []

    def fake_run_ffmpeg(cmd, **kwargs):
        captured_cmds.append(list(cmd))
        output_video.write_bytes(b"done")
        return MagicMock(returncode=0)

    with patch("src.media.multi_act_renderer.run_ffmpeg", side_effect=fake_run_ffmpeg), \
         patch.object(renderer, "resolve_loop_for_theme", return_value=tmp_path / "dummy_loop.mp4"):
        renderer.composite_multi_act_video(
            acts=acts,
            audio_path=audio_path,
            output_video=output_video,
            total_duration=5.0,
            is_vertical=False,
            ass_subtitles=active_ass_file,
        )

    assert len(captured_cmds) == 1
    cmd_str = " ".join(captured_cmds[0])
    assert "subtitles=" in cmd_str
    # Escaped colon and single quote
    assert "sub\\'s\\:active.ass" in cmd_str


def test_multi_act_video_renderer_generate_ass_subtitles_safe_margins(tmp_path: Path):
    """2.3 RED: MultiActVideoRenderer.generate_ass_subtitles produces ASS with safe margins and adaptive font."""
    renderer = MultiActVideoRenderer()
    acts = [
        NarrativeSceneAct(act_index=0, start_sec=0.0, duration_sec=5.0, title="Act 1", theme_category="scp"),
    ]

    # Portrait with drift
    out_vertical = tmp_path / "vertical.ass"
    renderer.generate_ass_subtitles(
        acts=acts,
        output_ass=out_vertical,
        is_vertical=True,
        downward_drift_px=30,
    )
    content_v = out_vertical.read_text(encoding="utf-8")
    assert ",64,130,510," in content_v
    assert "Style: Default,Liberation Sans,52," in content_v

    # Landscape
    out_horizontal = tmp_path / "horizontal.ass"
    renderer.generate_ass_subtitles(
        acts=acts,
        output_ass=out_horizontal,
        is_vertical=False,
    )
    content_h = out_horizontal.read_text(encoding="utf-8")
    assert ",40,40,130," in content_h
    assert "Style: Default,Liberation Sans,38," in content_h


def test_multi_act_inactive_ass_does_not_block_stream_copy(tmp_path: Path, header_only_ass_file: Path, monkeypatch):
    """Header-only ASS must not eject MultiAct from homogeneity-gated -c:v copy when HUD/xfade are off."""
    loop = tmp_path / "loop.mp4"
    loop.write_bytes(b"\0" * 64)
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"RIFF" + b"\0" * 40)
    output_video = tmp_path / "out.mp4"
    cmds: list[list[str]] = []

    def fake_run(cmd, check=True, **kwargs):
        cmds.append(list(cmd))
        Path(cmd[-1]).write_bytes(b"mp4")
        return MagicMock(returncode=0)

    vs = MagicMock(width=1920, height=1080, codec_name="h264", pix_fmt="yuv420p")
    probe = MagicMock(
        video_streams=[vs],
        primary_video=vs,
        raw_payload={"streams": [{"codec_type": "video", "time_base": "1/90000"}]},
    )
    monkeypatch.setattr("src.media.multi_act_renderer.probe_media", lambda *a, **k: probe)
    monkeypatch.setattr("src.media.multi_act_renderer.run_ffmpeg", fake_run)
    monkeypatch.setenv("DIRECTOR_SINGLE_PASS", "1")
    monkeypatch.setenv("MULTIACT_XFADE", "0")

    renderer = MultiActVideoRenderer(loops_dir=tmp_path)
    monkeypatch.setattr(renderer, "resolve_loop_for_theme", lambda *a, **k: loop)
    acts = [
        NarrativeSceneAct(
            0, 0.0, 2.0, "A", "scp",
            hud_badge="", hud_site="", hud_telemetry="",
            niche_hud={"hud_enabled": False},
        ),
        NarrativeSceneAct(
            1, 2.0, 3.0, "B", "scp",
            hud_badge="", hud_site="", hud_telemetry="",
            niche_hud={"hud_layout": "none"},
        ),
    ]
    renderer.composite_multi_act_video(
        acts=acts,
        audio_path=audio_path,
        output_video=output_video,
        total_duration=5.0,
        is_vertical=False,
        ass_subtitles=header_only_ass_file,
    )

    assert not any("-filter_complex" in c for c in cmds)
    copy_trim_cmds = [c for c in cmds if "-stream_loop" in c and "-c:v" in c and c[c.index("-c:v") + 1] == "copy"]
    assert len(copy_trim_cmds) == 2
    concat_cmds = [c for c in cmds if "-f" in c and "concat" in c and "-c:v" in c and c[c.index("-c:v") + 1] == "copy"]
    assert len(concat_cmds) == 1
