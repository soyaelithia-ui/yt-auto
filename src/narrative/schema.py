"""
src/narrative/schema.py - Schema contracts and data models for Cosmic/Analog Horror Video Pipeline.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union


class VideoFormat(str, Enum):
    SHORT_VERTICAL = "SHORT_VERTICAL"
    LONG_HORIZONTAL = "LONG_HORIZONTAL"


class VoicePreset(str, Enum):
    INTERCOM_BUNKER = "intercom_bunker"
    HYDROPHONE_RADIO = "hydrophone_radio"
    BLACKBOX_TAPE = "blackbox_tape"


class NarrativeArchetype(str, Enum):
    HYDROACOUSTIC_TELEMETRY = "hydroacoustic_telemetry"
    PROCEDURAL_INSTITUTIONAL_MANUAL = "procedural_institutional_manual"
    SPECULATIVE_BIOLOGICAL_DOSSIER = "speculative_biological_dossier"


@dataclass
class SFXCue:
    time_sec: float
    sfx_id: str  # e.g., "ptt_squelch", "sonar_ping_deep_reverb", "hull_stress_metal_groan", "singularity_glitch_burst"
    volume: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AudioContract:
    voice_text: str
    voice_preset: VoicePreset = VoicePreset.INTERCOM_BUNKER
    drone_base_freq_hz: float = 38.0
    sfx_timeline: List[SFXCue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "voice_text": self.voice_text,
            "voice_preset": self.voice_preset.value if isinstance(self.voice_preset, VoicePreset) else str(self.voice_preset),
            "drone_base_freq_hz": float(self.drone_base_freq_hz),
            "sfx_timeline": [cue.to_dict() if hasattr(cue, "to_dict") else cue for cue in self.sfx_timeline],
        }


@dataclass
class SceneContract:
    start_sec: float
    end_sec: float
    shader_id: str  # "RADAR_HYDROACOUSTIC", "MONOLITHS_RAYMARCHING", "GRAVITATIONAL_SINGULARITY"
    shader_params: Dict[str, Any] = field(default_factory=dict)
    hud_status: str = "STATUS: ONLINE"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CosmicScriptContract:
    title: str
    format: VideoFormat
    telemetry_header: str
    audio: AudioContract
    scenes: List[SceneContract]
    loop_continuity_phrase: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "format": self.format.value if isinstance(self.format, VideoFormat) else str(self.format),
            "telemetry_header": self.telemetry_header,
            "audio": self.audio.to_dict() if hasattr(self.audio, "to_dict") else self.audio,
            "scenes": [s.to_dict() if hasattr(s, "to_dict") else s for s in self.scenes],
            "loop_continuity_phrase": self.loop_continuity_phrase,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CosmicScriptContract:
        audio_data = data.get("audio", {})
        sfx_timeline = [
            SFXCue(**c) if isinstance(c, dict) else c
            for c in audio_data.get("sfx_timeline", [])
        ]
        audio = AudioContract(
            voice_text=audio_data.get("voice_text", ""),
            voice_preset=VoicePreset(audio_data.get("voice_preset", VoicePreset.INTERCOM_BUNKER.value)),
            drone_base_freq_hz=float(audio_data.get("drone_base_freq_hz", 38.0)),
            sfx_timeline=sfx_timeline,
        )
        scenes = [
            SceneContract(**s) if isinstance(s, dict) else s
            for s in data.get("scenes", [])
        ]
        return cls(
            title=data.get("title", "EXPEDIENTE SIN TITULO"),
            format=VideoFormat(data.get("format", VideoFormat.SHORT_VERTICAL.value)),
            telemetry_header=data.get("telemetry_header", "REC [●] 2026-08-28 00:00:00 UTC // RESTRICTED"),
            audio=audio,
            scenes=scenes,
            loop_continuity_phrase=data.get("loop_continuity_phrase"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> CosmicScriptContract:
        return cls.from_dict(json.loads(json_str))
