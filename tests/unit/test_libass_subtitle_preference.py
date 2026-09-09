"""
tests/unit/test_libass_subtitle_preference.py

Proves production subtitle burn prefers native libass (ASS) over the Pillow
frame-by-frame bridge, with Pillow available only via FORCE_PILLOW_SUBTITLES.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.media.subtitles import CodeSubtitleDrawer
from src.media.subtitles_ass import (
    force_pillow_subtitles_enabled,
    word_timestamps_from_cues,
    write_ass_from_cues_or_words,
)


def test_force_pillow_subtitles_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FORCE_PILLOW_SUBTITLES", raising=False)
    assert force_pillow_subtitles_enabled() is False
    assert force_pillow_subtitles_enabled({}) is False
    assert force_pillow_subtitles_enabled({"force_pillow_subtitles": False}) is False


def test_force_pillow_subtitles_opt_in_env_and_kwarg(monkeypatch):
    monkeypatch.setenv("FORCE_PILLOW_SUBTITLES", "1")
    assert force_pillow_subtitles_enabled() is True
    monkeypatch.delenv("FORCE_PILLOW_SUBTITLES", raising=False)
    assert force_pillow_subtitles_enabled({"force_pillow_subtitles": True}) is True


def test_write_ass_from_cues_and_offset(tmp_path: Path):
    words = [
        {"word": "Hola", "start": 2.0, "end": 2.4},
        {"word": "mundo", "start": 2.4, "end": 2.9},
    ]
    cues = CodeSubtitleDrawer.parse_word_timestamps(words, words_per_cue=2)
    stamps = word_timestamps_from_cues(cues)
    assert stamps[0]["word"] == "Hola"
    assert stamps[0]["start"] == pytest.approx(2.0)

    out = tmp_path / "subs.ass"
    write_ass_from_cues_or_words(
        output_path=out,
        cues=cues,
        video_width=320,
        video_height=180,
        time_offset_sec=2.0,
    )
    content = out.read_text(encoding="utf-8")
    assert "Dialogue:" in content
    # After offset, dialogue should start near 0:00:00.00
    assert "0:00:00." in content


def test_compositor_prefers_libass_and_skips_pillow_cues(tmp_path: Path, monkeypatch):
    """MultiSceneCompositor must not pass subtitle_cues to engines by default."""
    monkeypatch.delenv("FORCE_PILLOW_SUBTITLES", raising=False)

    from src.media.compositor import MultiSceneCompositor
    from src.scene_manifest import SceneConfig, SceneManifestV2, AudioTracks, SafeArea

    comp = MultiSceneCompositor(
        hybrid_engine=MagicMock(),
        loop_engine=MagicMock(),
    )
    captured = {"cues": "UNSET", "subtitle_path": "UNSET"}

    def fake_proc_render(**kwargs):
        captured["cues"] = kwargs.get("subtitle_cues")
        out = Path(kwargs["output_mp4"])
        import subprocess
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1280x720:d=0.4",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", "0.4", str(out),
            ],
            check=True,
            capture_output=True,
        )
        return out

    def fake_master(**kwargs):
        captured["subtitle_path"] = kwargs.get("subtitle_path")
        Path(kwargs["output_mp4"]).write_bytes(b"ok")

    manifest_obj = SceneManifestV2(
        story_id="test_libass",
        lane_id="test-lane",
        channel_name="test",
        resolution=(1280, 720),
        fps=30,
        total_duration_sec=0.4,
        audio_tracks=AudioTracks(narration_path="", music_path="", music_volume=0.0),
        safe_area=SafeArea(margin_top=60, margin_bottom=124, margin_left=85, margin_right=85),
        scenes=[
            SceneConfig(
                scene_index=1,
                scene_id="sc1",
                start_sec=0.0,
                duration_sec=0.4,
                tension_level=1,
                engine_type="catalog_loop",
            )
        ],
    )
    man_path = tmp_path / "scene_manifest.json"
    man_path.write_text(manifest_obj.model_dump_json(), encoding="utf-8")

    ass_path = tmp_path / "subs.ass"
    write_ass_from_cues_or_words(
        output_path=ass_path,
        word_timestamps=[{"word": "TEST", "start": 0.0, "end": 0.3}],
        video_width=320,
        video_height=180,
    )

    words = [{"word": "TEST", "start": 0.0, "end": 0.3}]
    cues = CodeSubtitleDrawer.parse_word_timestamps(words)

    comp.loop_engine.render_scene_segment = fake_proc_render  # type: ignore
    comp._master_assembly = fake_master  # type: ignore
    comp._assemble_video_scenes = lambda *a, **k: Path(a[1]).write_bytes(b"v")  # type: ignore

    out_p = tmp_path / "out.mp4"
    # Even if caller passes cues + word_timestamps, default must prefer ASS path
    res = comp.render(
        manifest_path=man_path,
        output_video_path=out_p,
        crf=28,
        preset="ultrafast",
        subtitle_cues=cues,
        word_timestamps=words,
        subtitle_path=ass_path,
    )
    assert res["status"] == "success"
    assert captured["cues"] is None, "engines must not receive Pillow subtitle_cues by default"
    assert captured["subtitle_path"] is not None
    assert Path(captured["subtitle_path"]).suffix.lower() == ".ass"


def test_loop_engine_default_path_uses_libass_not_pillow(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("FORCE_PILLOW_SUBTITLES", raising=False)
    from src.media.loop_engine import LoopVideoEngine
    from src.scene_manifest import SceneConfig

    engine = LoopVideoEngine()
    sc = SceneConfig(
        scene_index=1,
        scene_id="sc_loop_sub_libass",
        start_sec=0.0,
        duration_sec=0.4,
        tension_level=2,
        engine_type="catalog_loop",
        environment_name="dark_forest",
    )
    words = [
        {"word": "ENTIDAD", "start": 0.0, "end": 0.2},
        {"word": "DETECTADA", "start": 0.2, "end": 0.4},
    ]
    cues = CodeSubtitleDrawer.parse_word_timestamps(words, words_per_cue=2)
    out_sub = tmp_path / "loop_sub_libass.mp4"

    seen_cmds = []

    def fake_run_ffmpeg(cmd, *a, **k):
        seen_cmds.append(list(cmd))
        out = Path(cmd[-1])
        import subprocess
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1280x720:d=0.4",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", "0.4", str(out),
            ],
            check=True,
            capture_output=True,
        )
        return MagicMock(returncode=0)

    loop = tmp_path / "loop.mp4"
    import subprocess
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=0.5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", "0.5", str(loop),
        ],
        check=True,
        capture_output=True,
    )

    monkeypatch.setattr(engine, "resolve_loop_video", lambda *a, **k: loop)

    with patch("src.media.loop_engine.run_ffmpeg", side_effect=fake_run_ffmpeg):
        with patch("src.media.loop_engine.probe_media") as probe:
            probe.return_value = MagicMock(primary_video=MagicMock(duration=0.5), duration=0.5)
            engine.render_scene_segment(
                scene=sc,
                width=320,
                height=180,
                fps=30,
                lane_id="moku-horror-long",
                output_mp4=out_sub,
                crf=28,
                subtitle_cues=cues,
                scene_start_sec=0.0,
                threads=2,
            )

    assert out_sub.exists()
    assert seen_cmds, "expected libass ffmpeg path via run_ffmpeg"
    joined = " ".join(seen_cmds[0])
    assert "ass=filename=" in joined
    assert "ass=filename='" not in joined
    assert "fontsdir='" not in joined
    assert "rawvideo" not in seen_cmds[0], "must not use Pillow rawvideo bridge by default"


def test_hybrid_libass_burn_is_unquoted_for_ffmpeg_61(tmp_path: Path, monkeypatch):
    """Hybrid post-pass libass must use unquoted ass=filename= (FFmpeg 6.1)."""
    from src.media.hybrid_engine import HybridVideoEngine
    from src.media.subtitles_ass import write_ass_from_cues_or_words

    out_path = tmp_path / "scene.mp4"
    out_path.write_bytes(b"dummy")
    words = [{"word": "Hola", "start": 0.0, "end": 0.3}]
    cues = CodeSubtitleDrawer.parse_word_timestamps(words)
    captured: list[list[str]] = []

    def fake_run(cmd, *a, **k):
        captured.append([str(c) for c in cmd])
        Path(cmd[-1]).write_bytes(b"ok")

    monkeypatch.setattr("src.media.hybrid_engine.run_ffmpeg", fake_run)
    engine = HybridVideoEngine(output_dir=tmp_path)
    engine._burn_libass_subtitles(
        out_path=out_path,
        subtitle_cues=cues,
        width=320,
        height=180,
        scene_start_sec=0.0,
        crf=21,
        preset="veryfast",
        threads_val="2",
        write_ass_from_cues_or_words=write_ass_from_cues_or_words,
    )
    assert captured
    vf = captured[0][captured[0].index("-vf") + 1]
    assert vf.startswith("ass=filename=")
    assert "ass=filename='" not in vf
    assert "fontsdir='" not in vf

