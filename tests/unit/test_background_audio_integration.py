"""
tests/unit/test_background_audio_integration.py - Integration tests for background audio selection and procedural creation.
"""
import os
import wave
from pathlib import Path
import pytest

from src.asset_manager import get_asset_manager
from src.core.lanes import load_lanes
from src.media.manifest_compiler import ScenePlannerCompositorAgent
from lib.audio import apply_sidechain_ducking, build_sidechain_ducking_filter_graph, DEFAULT_BACKGROUND_AUDIO_VOLUME


def test_lane_background_audio_configuration():
    lanes = load_lanes()
    assert len(lanes) >= 3
    lane_map = {l.id: l for l in lanes}

    assert "horror-scp-shorts" in lane_map
    assert "horror-horror-long" in lane_map
    assert "drama-aita-long" in lane_map

    for lane in lanes:
        assert hasattr(lane, "background_audio")
        assert lane.background_audio.enabled is True
        assert lane.background_audio.volume == 0.04
        assert lane.background_audio.mode in ("auto", "choose", "create", "off")


def test_asset_manager_resolve_or_create_procedural_fallback(tmp_path: Path):
    manager = get_asset_manager()
    # "drama" category has no static MP3 in assets/music -> triggers procedural synthesis in auto mode
    track_path = manager.resolve_or_create_background_audio(
        category="drama",
        style="aita",
        duration_sec=4.0,
        work_dir=tmp_path,
        mode="auto",
    )
    assert track_path != ""
    p = Path(track_path)
    assert p.is_file()
    assert p.stat().st_size > 0

    with wave.open(str(p), "rb") as wf:
        assert wf.getnchannels() == 2
        assert wf.getframerate() == 48000
        dur = wf.getnframes() / float(wf.getframerate())
        assert abs(dur - 4.0) < 0.1


def test_asset_manager_mode_off(tmp_path: Path):
    manager = get_asset_manager()
    track_path = manager.resolve_or_create_background_audio(
        category="horror",
        style="creepypasta",
        duration_sec=4.0,
        work_dir=tmp_path,
        mode="off",
    )
    assert track_path == ""


def test_scene_planner_defaults_to_super_low_volume():
    agent = ScenePlannerCompositorAgent()
    script = {
        "metadata": {"title": "Test Story", "channel_lane": "horror-scp-shorts", "target_format": "short"},
        "acts": [
            {
                "act_number": 1,
                "scenes": [
                    {
                        "scene_id": "scene_001",
                        "estimated_duration_sec": 30.0,
                        "narration_text": "Texto de prueba de narración.",
                    }
                ]
            }
        ]
    }
    visual_plan = {
        "scenes": [
            {
                "scene_id": "scene_001",
                "scene_index": 1,
                "duration": 30.0,
            }
        ]
    }
    manifest = agent.plan_manifest(
        script=script,
        visual_plan=visual_plan,
        story_id="story_test",
        narration_path="tests/fixtures/sample_voice.wav",
        lane_id="horror-scp-shorts",
        channel_name="horror",
    )
    assert manifest["audio_tracks"]["music_volume"] == 0.04
    assert DEFAULT_BACKGROUND_AUDIO_VOLUME == 0.04


def test_build_sidechain_ducking_filter_graph_structure():
    graph = build_sidechain_ducking_filter_graph(
        speech_label="0:a",
        music_label="1:a",
        out_label="aout",
        music_volume=0.04,
        ducking_threshold=0.035,
        ducking_ratio=8.0,
    )
    assert "volume=0.0400" in graph
    assert "sidechaincompress=threshold=0.0350:ratio=8.0" in graph
    assert "amix=inputs=2:duration=first:normalize=0" in graph
