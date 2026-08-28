"""
tests/unit/test_realtime_engine.py - Unit tests for the Real-Time Procedural Three.js Video Engine.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.media.realtime_video_engine import (
    RealtimeVideoEngine,
    TemporalAct,
    build_default_temporal_acts,
    generate_realtime_html_code,
    parse_manifest_to_temporal_acts,
    resolve_chrome_executable,
)


def test_build_default_temporal_acts_structure() -> None:
    """Verifies that default acts are properly configured across 5 distinct narrative environments."""
    total_dur = 120.0
    acts = build_default_temporal_acts(topic="SCP-2000", total_duration_sec=total_dur)
    
    assert len(acts) == 5
    assert acts[0].start_sec == 0.0
    assert acts[-1].end_sec == total_dur
    
    environments = [a.environment for a in acts]
    assert environments == ["bunker", "cloners", "neural", "vortex", "terminal"]
    
    motions = [a.camera_motion for a in acts]
    assert motions == ["dolly_in", "lateral_track", "orbital_ascend", "vortex_tilt", "tactical_pan"]

    # Verify continuity: each act's end matches next act's start
    for i in range(len(acts) - 1):
        assert abs(acts[i].end_sec - acts[i+1].start_sec) < 1e-4


def test_parse_manifest_from_dict_and_scene_manifest_v2() -> None:
    """Verifies that SceneManifestV2 dictionary structures are parsed into valid TemporalActs."""
    mock_manifest = {
        "manifest_version": "2.0",
        "story_id": "scp2000_long",
        "lane_id": "moku-horror-long",
        "channel_name": "moku",
        "resolution": [1920, 1080],
        "fps": 30,
        "total_duration_sec": 600.0,
        "scenes": [
            {
                "scene_index": 1,
                "scene_id": "sc_01",
                "environment_name": "Yellowstone Deep Bunker",
                "start_sec": 0.0,
                "duration_sec": 100.0,
                "tension_level": 2,
                "engine_type": "pure_procedural_webgl",
            },
            {
                "scene_index": 2,
                "scene_id": "sc_02",
                "environment_name": "BZHR Cloning Chambers",
                "start_sec": 100.0,
                "duration_sec": 200.0,
                "tension_level": 4,
                "engine_type": "pure_procedural_webgl",
            },
            {
                "scene_index": 3,
                "scene_id": "sc_03",
                "environment_name": "Class-XK Dimensional Spacetime Vortex",
                "start_sec": 300.0,
                "duration_sec": 300.0,
                "tension_level": 5,
                "engine_type": "pure_procedural_webgl",
            },
        ],
    }

    acts = parse_manifest_to_temporal_acts(mock_manifest, total_duration_sec=600.0)
    assert len(acts) == 3
    assert acts[0].start_sec == 0.0
    assert acts[0].duration_sec == 100.0
    assert acts[0].environment == "bunker"
    
    assert acts[1].start_sec == 100.0
    assert acts[1].duration_sec == 200.0
    assert acts[1].environment == "cloners"
    
    assert acts[2].start_sec == 300.0
    assert acts[2].duration_sec == 300.0
    assert acts[2].environment == "vortex"


def test_parse_manifest_from_custom_list() -> None:
    """Verifies that a list of act dicts is parsed into valid TemporalActs."""
    custom_acts = [
        {
            "start_sec": 0.0,
            "duration_sec": 45.0,
            "title": "SECTOR ALPHA",
            "label": "ACTO 1: ENTRADA",
            "environment": "bunker",
            "camera_motion": "dolly_in",
            "theme_color": "#00FF88",
        },
        {
            "start_sec": 45.0,
            "duration_sec": 55.0,
            "title": "NÚCLEO NEURONAL",
            "label": "ACTO 2: MEMORIA",
            "environment": "neural",
            "camera_motion": "orbital_ascend",
            "theme_color": "#9944FF",
        },
    ]

    acts = parse_manifest_to_temporal_acts(custom_acts, total_duration_sec=100.0)
    assert len(acts) == 2
    assert acts[0].title == "SECTOR ALPHA"
    assert acts[1].environment == "neural"


def test_generate_realtime_html_code_contains_acts_and_threejs() -> None:
    """Verifies that HTML code contains valid Three.js setup, acts JSON, and renderFrame function."""
    html = generate_realtime_html_code(
        topic="SCP-2000 Deus Ex Machina",
        width=1920,
        height=1080,
        duration_sec=30.0,
        fps=30,
    )

    assert "<!DOCTYPE html>" in html
    assert "three.min.js" in html
    assert "window.renderFrame" in html
    assert "bunkerGroup" in html
    assert "clonersGroup" in html
    assert "neuralGroup" in html
    assert "vortexGroup" in html
    assert "terminalGroup" in html
    assert "findActByTime" in html
    assert "crtOverlay" in html
    assert "1920" in html and "1080" in html


def test_generate_realtime_html_vertical_safe_area() -> None:
    """Verifies vertical (9:16) rendering adapts font sizes and safe padding."""
    html_vert = generate_realtime_html_code(
        topic="SCP-2000 Short",
        width=1080,
        height=1920,
        duration_sec=15.0,
        fps=30,
    )

    assert "width: 1080px;" in html_vert
    assert "height: 1920px;" in html_vert
    assert "35px 25px" in html_vert  # Vertical padding


def test_realtime_engine_initialization_and_chrome_resolve(tmp_path: Path) -> None:
    """Verifies RealtimeVideoEngine instance properties and Chrome path resolution."""
    engine = RealtimeVideoEngine(work_dir=tmp_path)
    assert engine.work_dir == tmp_path
    assert tmp_path.is_dir()

    chrome_path = resolve_chrome_executable()
    if chrome_path:
        assert Path(chrome_path).is_file()


def test_composite_with_explicit_audio_stream_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that _composite_with_explicit_audio uses stream copy (-c:v copy) when no subtitles are passed."""
    engine = RealtimeVideoEngine(work_dir=tmp_path)
    v_in = tmp_path / "raw.mp4"
    a_in = tmp_path / "audio.wav"
    v_out = tmp_path / "out.mp4"
    v_in.write_bytes(b"dummy_video")
    a_in.write_bytes(b"dummy_audio")

    captured_cmds: List[List[str]] = []

    def mock_run(cmd: List[str], check: bool = True) -> Any:
        captured_cmds.append(cmd)
        return None

    import subprocess
    monkeypatch.setattr(subprocess, "run", mock_run)

    # 1. No subtitles -> should use -c:v copy
    engine._composite_with_explicit_audio(
        video_input=v_in,
        audio_input=a_in,
        output_final=v_out,
        subtitles_ass_path=None,
        duration_sec=10.0,
    )
    assert len(captured_cmds) == 1
    assert "-c:v" in captured_cmds[0]
    idx_v = captured_cmds[0].index("-c:v")
    assert captured_cmds[0][idx_v + 1] == "copy"
    assert "-c:a" in captured_cmds[0]

    # 2. With subtitles -> should use -c:v libx264
    sub_file = tmp_path / "sub.ass"
    sub_file.write_text("[Script Info]\nTitle: Test", encoding="utf-8")
    engine._composite_with_explicit_audio(
        video_input=v_in,
        audio_input=a_in,
        output_final=v_out,
        subtitles_ass_path=sub_file,
        duration_sec=10.0,
    )
    assert len(captured_cmds) == 2
    idx_v2 = captured_cmds[1].index("-c:v")
    assert captured_cmds[1][idx_v2 + 1] == "libx264"

