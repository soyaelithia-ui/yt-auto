"""
src/narrative/schema.py - Schema contracts and data models for Cosmic/Analog Horror Video Pipeline.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional, Union


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


class TensionLevel(IntEnum):
    BASELINE = 1
    MICRO_ANOMALY = 2
    ESCALATION = 3
    HIGH_ESCALATION = 4
    CLIMAX = 5


@dataclass
class Rec709Palette:
    """ITU-R BT.709 (Rec.709) compliant color palette specification."""
    primary: str
    secondary: str
    accent: str
    shadow: str
    highlight: str
    kelvin: int = 6500
    lut_profile: str = "cosmic_rec709"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary": self.primary,
            "secondary": self.secondary,
            "accent": self.accent,
            "shadow": self.shadow,
            "highlight": self.highlight,
            "kelvin": int(self.kelvin),
            "lut_profile": self.lut_profile,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Rec709Palette:
        return cls(
            primary=data.get("primary", "#041421"),
            secondary=data.get("secondary", "#0a2233"),
            accent=data.get("accent", "#00e5a3"),
            shadow=data.get("shadow", "#000305"),
            highlight=data.get("highlight", "#b0fff1"),
            kelvin=int(data.get("kelvin", 6500)),
            lut_profile=data.get("lut_profile", "cosmic_rec709"),
        )


@dataclass
class CameraTransform:
    """2.5D camera drift and transformation parameters."""
    offset_x: float = 0.0
    offset_y: float = 0.0
    rotation_deg: float = 0.0
    zoom_scale: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "offset_x": float(self.offset_x),
            "offset_y": float(self.offset_y),
            "rotation_deg": float(self.rotation_deg),
            "zoom_scale": float(self.zoom_scale),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CameraTransform:
        return cls(
            offset_x=float(data.get("offset_x", 0.0)),
            offset_y=float(data.get("offset_y", 0.0)),
            rotation_deg=float(data.get("rotation_deg", 0.0)),
            zoom_scale=float(data.get("zoom_scale", 1.0)),
        )


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
    hud_status: str = "STATUS: ONLINE"
    tension_level: int = 3
    visual_asset: Optional[str] = None
    palette: Optional[Rec709Palette] = None
    camera_transform: Optional[CameraTransform] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.palette:
            d["palette"] = self.palette.to_dict()
        if self.camera_transform:
            d["camera_transform"] = self.camera_transform.to_dict()
        return d


@dataclass
class SceneContractV2:
    start_sec: float
    end_sec: float
    tension_level: Union[TensionLevel, int] = TensionLevel.ESCALATION
    visual_asset: Optional[str] = None
    palette: Optional[Rec709Palette] = None
    camera_transform: Optional[CameraTransform] = None
    camera_drift: Dict[str, float] = field(default_factory=dict)
    hud_status: str = "STATUS: ONLINE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_sec": float(self.start_sec),
            "end_sec": float(self.end_sec),
            "tension_level": int(self.tension_level),
            "visual_asset": self.visual_asset,
            "palette": self.palette.to_dict() if self.palette else None,
            "camera_transform": self.camera_transform.to_dict() if self.camera_transform else None,
            "camera_drift": self.camera_drift,
            "hud_status": self.hud_status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SceneContractV2:
        pal_data = data.get("palette")
        palette = Rec709Palette.from_dict(pal_data) if pal_data else None
        cam_data = data.get("camera_transform")
        cam_transform = CameraTransform.from_dict(cam_data) if cam_data else None
        return cls(
            start_sec=float(data.get("start_sec", 0.0)),
            end_sec=float(data.get("end_sec", 10.0)),
            tension_level=int(data.get("tension_level", 3)),
            visual_asset=data.get("visual_asset"),
            palette=palette,
            camera_transform=cam_transform,
            camera_drift=data.get("camera_drift", {}),
            hud_status=data.get("hud_status", "STATUS: ONLINE"),
        )


@dataclass
class CosmicScriptContract:
    title: str
    format: VideoFormat
    telemetry_header: str
    audio: AudioContract
    scenes: List[Union[SceneContract, SceneContractV2]]
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
        scenes = []
        for s in data.get("scenes", []):
            if isinstance(s, dict):
                if "palette" in s or "camera_transform" in s:
                    scenes.append(SceneContractV2.from_dict(s))
                else:
                    scenes.append(SceneContract(**s))
            else:
                scenes.append(s)

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
