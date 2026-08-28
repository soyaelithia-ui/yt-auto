"""
tests/unit/test_narrative_engine.py - Unit tests for Cosmic Narrative Engine and Schema Contracts.
"""
import json
import pytest
from src.narrative.schema import (
    CosmicScriptContract,
    NarrativeArchetype,
    VideoFormat,
    VoicePreset,
)
from src.narrative.engine import CosmicNarrativeEngine


def test_schema_serialization_and_deserialization() -> None:
    engine = CosmicNarrativeEngine()
    script = engine.generate_script(
        topic="Anomalía Fosa de las Marianas",
        archetype=NarrativeArchetype.HYDROACOUSTIC_TELEMETRY,
        video_format=VideoFormat.SHORT_VERTICAL,
        duration_sec=30.0,
    )

    assert script.title == "Anomalía Fosa de las Marianas"
    assert script.format == VideoFormat.SHORT_VERTICAL
    assert len(script.scenes) >= 3
    assert len(script.audio.sfx_timeline) >= 3
    assert script.audio.voice_preset == VoicePreset.HYDROPHONE_RADIO
    assert script.loop_continuity_phrase is not None

    json_str = script.to_json()
    reloaded = CosmicScriptContract.from_json(json_str)

    assert reloaded.title == script.title
    assert reloaded.format == script.format
    assert len(reloaded.scenes) == len(script.scenes)
    assert reloaded.audio.drone_base_freq_hz == script.audio.drone_base_freq_hz
    assert reloaded.loop_continuity_phrase == script.loop_continuity_phrase


def test_tension_curve_scenes_progression() -> None:
    engine = CosmicNarrativeEngine()
    script = engine.generate_script(
        archetype=NarrativeArchetype.PROCEDURAL_INSTITUTIONAL_MANUAL,
        video_format=VideoFormat.LONG_HORIZONTAL,
        duration_sec=120.0,
    )

    assert script.format == VideoFormat.LONG_HORIZONTAL
    assert script.audio.voice_preset == VoicePreset.INTERCOM_BUNKER
    assert script.scenes[0].start_sec == 0.0
    assert script.scenes[-1].end_sec == 120.0

    # Ensure monotonic timeline
    for i in range(len(script.scenes) - 1):
        assert script.scenes[i].end_sec == script.scenes[i + 1].start_sec
        assert script.scenes[i].shader_params["uTension"] <= script.scenes[i + 1].shader_params["uTension"]


def test_all_archetypes_generate_valid_contracts() -> None:
    engine = CosmicNarrativeEngine()
    for arch in NarrativeArchetype:
        s = engine.generate_script(archetype=arch, duration_sec=35.0)
        assert len(s.audio.voice_text) > 50
        assert s.audio.drone_base_freq_hz > 0
        assert len(s.scenes) >= 1
