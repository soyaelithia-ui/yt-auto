"""
src/scene_manifest.py - Canonical Visual & Audio Scene Manifest Contract Engine (v2.0).

Defines Draft-07 JSON Schema validation, Pydantic data models, and high-level builders
for the Dual-Engine (Hybrid Cinematic AI + Pure Procedural WebGL/Canvas) rendering pipeline.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import jsonschema
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core.resolution import LONGFORM_RESOLUTION, SHORT_RESOLUTION
from src.log import get_logger

logger = get_logger("scene_manifest")

SCHEMA_FILE_PATH = Path(__file__).resolve().parent.parent / "schemas" / "scene_manifest.schema.json"


# ---------------------------------------------------------------------------
# Pydantic v2 Models for Scene Manifest v2.0
# ---------------------------------------------------------------------------

class ColorProfile(BaseModel):
    color_space: str = "bt709"
    color_primaries: str = "bt709"
    color_trc: str = "bt709"
    pixel_format: Literal["yuv420p", "yuv420p10le"] = "yuv420p"


class DuckingConfig(BaseModel):
    enabled: bool = True
    threshold: float = 0.035
    ratio: float = 8.0
    attack_ms: float = 20.0
    release_ms: float = 350.0
    target_lufs: float = -14.0
    max_tp: float = -1.5
    lra: float = 11.0


class SFXCue(BaseModel):
    sfx_id: Optional[str] = None
    sfx_path: str
    timestamp_sec: float = Field(..., ge=0.0)
    volume: float = Field(..., ge=0.0, le=1.0)
    pan: float = Field(0.0, ge=-1.0, le=1.0)


class AudioTracks(BaseModel):
    narration_path: str
    music_path: Optional[str] = ""
    music_volume: float = Field(0.04, ge=0.0, le=1.0)
    ducking: Optional[DuckingConfig] = Field(default_factory=DuckingConfig)
    sfx_cues: Optional[List[SFXCue]] = Field(default_factory=list)


class SafeArea(BaseModel):
    margin_top: int = Field(60, ge=0)
    margin_bottom: int = Field(124, ge=0)
    margin_left: int = Field(85, ge=0)
    margin_right: int = Field(85, ge=0)


class LayerConfig(BaseModel):
    layer_id: str
    asset_path: str
    z_depth: float = Field(..., ge=0.0, le=1.0)
    blend_mode: Literal["normal", "screen", "multiply", "overlay", "add"] = "normal"
    opacity: float = Field(1.0, ge=0.0, le=1.0)


class CameraMotionConfig(BaseModel):
    type: Literal[
        "ken_burns_3d",
        "parallax_drift",
        "orbital_pan",
        "zoom_in",
        "zoom_out",
        "pan_left",
        "pan_right",
        "static",
    ] = "ken_burns_3d"
    start_zoom: float = 1.0
    end_zoom: float = 1.08
    pan_direction: Literal[
        "center_to_top",
        "center_to_bottom",
        "left_to_right",
        "right_to_left",
        "static",
    ] = "center_to_top"
    easing: Literal["linear", "ease_in_out", "cubic_bezier"] = "cubic_bezier"
    parallax_intensity: float = Field(0.15, ge=0.0, le=1.0)


class LightingConfig(BaseModel):
    volumetric_rays: bool = False
    light_source_pos: Optional[List[float]] = None
    intensity: float = Field(0.3, ge=0.0, le=1.0)
    flicker_frequency: float = Field(0.0, ge=0.0)
    color_tint: str = "#ffffff"

    @field_validator("light_source_pos")
    @classmethod
    def validate_light_pos(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None and len(v) != 2:
            raise ValueError("light_source_pos must have exactly 2 coordinates [x, y]")
        return v


class ParticleConfig(BaseModel):
    type: Literal[
        "dust_motes",
        "ember_sparks",
        "fog_mist",
        "spores",
        "rain_streaks",
        "none",
    ] = "none"
    density: int = Field(40, ge=0, le=500)
    velocity: float = Field(1.0, ge=0.0, le=5.0)
    color: str = "#ffffff"
    opacity: float = Field(0.4, ge=0.0, le=1.0)


class HybridAIConfig(BaseModel):
    background_image_path: Optional[str] = None
    depth_map_path: Optional[str] = None
    prompt_used: Optional[str] = None
    seed: Optional[int] = None
    layers: Optional[List[LayerConfig]] = Field(default_factory=list)
    camera_motion: Optional[CameraMotionConfig] = Field(default_factory=CameraMotionConfig)
    lighting: Optional[LightingConfig] = Field(default_factory=LightingConfig)
    particles: Optional[ParticleConfig] = Field(default_factory=ParticleConfig)


class ProceduralPalette(BaseModel):
    base_dark: Optional[str] = "#020104"
    mid_tone: Optional[str] = "#1e0838"
    accent: Optional[str] = "#780a1e"


class ProceduralUniforms(BaseModel):
    u_noise_scale: float = 1.0
    u_speed: float = 1.0
    u_distortion: float = 0.5
    u_glow_intensity: float = 0.8


VisualArchetypeId = Literal[
    "cosmic_singularity",
    "dark_forest",
    "synaptic_network",
    "tactical_chamber",
]


class ProceduralConfig(BaseModel):
    archetype_id: VisualArchetypeId = "cosmic_singularity"
    template_name: Optional[str] = None
    seed: int = 42
    palette: Optional[ProceduralPalette] = Field(default_factory=ProceduralPalette)
    uniforms: Optional[ProceduralUniforms] = Field(default_factory=ProceduralUniforms)


class TransitionConfig(BaseModel):
    type: Literal[
        "crossfade",
        "volumetric_fade",
        "depth_dissolve",
        "glitch_cut",
        "cut",
        "fade_to_black",
        "fade",
    ] = "crossfade"
    duration_sec: float = Field(0.8, ge=0.0, le=3.0)


class SceneConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    scene_index: int = Field(..., ge=1)
    scene_id: str
    environment_name: Optional[str] = None
    start_sec: float = Field(..., ge=0.0)
    duration_sec: float = Field(..., ge=0.1)
    tension_level: int = Field(..., ge=1, le=5)
    engine_type: Literal[
        "hybrid_cinematic_ai",
        "pure_procedural_webgl",
        "procedural_canvas2d",
    ]
    hybrid_ai_config: Optional[HybridAIConfig] = None
    procedural_config: Optional[ProceduralConfig] = None
    transition_out: Optional[TransitionConfig] = Field(default_factory=TransitionConfig)
    niche_hud: Optional[Dict[str, Any]] = None
    camera_motion: Optional[Union[CameraMotionConfig, Dict[str, Any]]] = None
    image_path: Optional[str] = None
    asset_path: Optional[str] = None


class SubtitleCue(BaseModel):
    start: float = Field(..., ge=0.0)
    end: float = Field(..., ge=0.0)
    text: str


class BrandingConfig(BaseModel):
    stamp_text: Optional[str] = "[MOKU]"
    channel_name: Optional[str] = "moku"


class SceneManifestV2(BaseModel):
    manifest_version: Literal["2.0", "2.1", "2.0.0"] = "2.0"
    story_id: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$")
    lane_id: str
    channel_name: str
    resolution: List[int] = Field(..., min_length=2, max_length=2)
    fps: Literal[24, 25, 30, 50, 60] = 30
    total_duration_sec: float = Field(..., ge=0.1)
    color_profile: Optional[ColorProfile] = Field(default_factory=ColorProfile)
    audio_tracks: AudioTracks
    safe_area: SafeArea
    scenes: List[SceneConfig] = Field(..., min_length=1)
    subtitles: Optional[List[SubtitleCue]] = Field(default_factory=list)
    branding: Optional[BrandingConfig] = None
    hook_text: Optional[str] = None
    thumbnail_candidate_timestamp: Optional[float] = 5.0
    cache_keys: Optional[Dict[str, Any]] = None

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, v: List[int]) -> List[int]:
        if len(v) != 2 or v[0] < 640 or v[1] < 640:
            raise ValueError("resolution must be [width, height] with each dimension >= 640")
        return v

    @model_validator(mode="after")
    def validate_scene_durations_and_continuity(self) -> SceneManifestV2:
        if not self.scenes:
            raise ValueError("SceneManifest must contain at least one scene.")
        return self


# ---------------------------------------------------------------------------
# Schema Validation & Loader Helpers
# ---------------------------------------------------------------------------

def get_scene_manifest_schema() -> Dict[str, Any]:
    """Load and return the canonical Draft-07 JSON Schema for scene manifests."""
    if not SCHEMA_FILE_PATH.is_file():
        raise FileNotFoundError(f"Canonical schema not found at {SCHEMA_FILE_PATH}")
    return json.loads(SCHEMA_FILE_PATH.read_text(encoding="utf-8"))


def validate_scene_manifest(manifest_path_or_data: Union[Path, str, Dict[str, Any]]) -> bool:
    """
    Validates a scene manifest against the canonical Draft-07 JSON schema and Pydantic models.
    Supports both v2.0 manifests and legacy v1 manifests.

    Raises:
        ValueError: If manifest is missing, empty, or fails schema validation.
    """
    if isinstance(manifest_path_or_data, (Path, str)):
        p = Path(manifest_path_or_data)
        if not p.is_file() or p.stat().st_size == 0:
            raise ValueError(f"scene_manifest.json missing or empty at {p}")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"scene_manifest.json contains invalid JSON: {exc}") from exc
    elif isinstance(manifest_path_or_data, dict):
        data = manifest_path_or_data
    else:
        raise ValueError("manifest_path_or_data must be a Path, str, or dict")

    # Check for legacy v1 manifest format
    if data.get("version") == "1.0" and "manifest_version" not in data:
        required_keys = ["resolution", "fps", "duration_sec", "audio", "story", "branding", "scenes"]
        for k in required_keys:
            if k not in data:
                raise ValueError(f"scene_manifest.json (v1) missing required key: '{k}'")
        if not isinstance(data["resolution"], list) or len(data["resolution"]) < 2:
            raise ValueError("scene_manifest.json 'resolution' must be a [width, height] list")
        if data["duration_sec"] <= 0:
            raise ValueError("scene_manifest.json 'duration_sec' must be positive")
        if not data["audio"].get("narration_path"):
            raise ValueError("scene_manifest.json 'audio.narration_path' is required")
        return True

    # Validate against canonical JSON Schema (Draft-07)
    schema = get_scene_manifest_schema()
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errors:
        first_err = errors[0]
        field_path = ".".join(str(p) for p in first_err.path) or "root"
        raise ValueError(f"Scene manifest schema validation failed at '{field_path}': {first_err.message}")

    # Validate against Pydantic model for strict type and semantic integrity
    try:
        SceneManifestV2.model_validate(data)
    except Exception as exc:
        raise ValueError(f"Scene manifest model validation failed: {exc}") from exc

    return True


def load_scene_manifest(manifest_path: Union[Path, str]) -> Dict[str, Any]:
    """Loads and validates a scene manifest from disk."""
    p = Path(manifest_path)
    validate_scene_manifest(p)
    return json.loads(p.read_text(encoding="utf-8"))


def parse_scene_manifest_model(
    manifest_path_or_data: Union[Path, str, Dict[str, Any], SceneManifestV2],
) -> SceneManifestV2:
    """Parses and converts any validated manifest representation into a typed SceneManifestV2."""
    if isinstance(manifest_path_or_data, SceneManifestV2):
        return manifest_path_or_data
    if isinstance(manifest_path_or_data, (Path, str)):
        p = Path(manifest_path_or_data)
        data = json.loads(p.read_text(encoding="utf-8"))
    elif isinstance(manifest_path_or_data, dict):
        data = manifest_path_or_data
    else:
        raise ValueError("manifest_path_or_data must be a Path, str, dict, or SceneManifestV2")

    if "manifest_version" in data and str(data["manifest_version"]).startswith("2"):
        return SceneManifestV2.model_validate(data)

    # If legacy v1 format, adapt to v2 model
    res = data.get("resolution", [1920, 1080])
    dur = float(data.get("duration_sec", 60.0))
    story_meta = data.get("story", {})
    branding_meta = data.get("branding", {})
    audio_meta = data.get("audio", {})
    scenes_raw = data.get("scenes", [])

    adapted_scenes: List[SceneConfig] = []
    for idx, sc in enumerate(scenes_raw):
        sc_dur = float(sc.get("duration_sec", dur / max(1, len(scenes_raw))))
        sc_start = float(sc.get("start_sec", idx * sc_dur))
        img_p = sc.get("image_path") or sc.get("source")
        is_video_source = bool(img_p and str(img_p).endswith(".mp4"))
        if is_video_source:
            engine_t = "pure_procedural_webgl"
            proc_cfg = ProceduralConfig(template_name="cosmic_horror_three.html")
            hyb_cfg = None
        else:
            engine_t = "hybrid_cinematic_ai"
            proc_cfg = None
            hyb_cfg = HybridAIConfig(background_image_path=str(img_p) if img_p else None)

        adapted_scenes.append(
            SceneConfig(
                scene_index=idx + 1,
                scene_id=f"scene_{idx+1:03d}",
                environment_name=sc.get("category", "Scene Environment"),
                start_sec=sc_start,
                duration_sec=sc_dur,
                tension_level=3,
                engine_type=engine_t,
                hybrid_ai_config=hyb_cfg,
                procedural_config=proc_cfg,
                transition_out=TransitionConfig(type="crossfade", duration_sec=0.8),
            )
        )

    if not adapted_scenes:
        adapted_scenes.append(
            SceneConfig(
                scene_index=1,
                scene_id="scene_001",
                start_sec=0.0,
                duration_sec=dur,
                tension_level=3,
                engine_type="pure_procedural_webgl",
                procedural_config=ProceduralConfig(),
            )
        )

    return SceneManifestV2(
        manifest_version="2.0",
        story_id=story_meta.get("story_id", "story_001"),
        lane_id=story_meta.get("slot", "moku-horror-long"),
        channel_name=branding_meta.get("channel_name", "moku"),
        resolution=res,
        fps=int(data.get("fps", 30)),
        total_duration_sec=dur,
        color_profile=ColorProfile(),
        audio_tracks=AudioTracks(
            narration_path=audio_meta.get("narration_path", ""),
            music_path=audio_meta.get("music_path", ""),
            music_volume=float(audio_meta.get("music_volume", 0.04)),
            ducking=DuckingConfig(),
        ),
        safe_area=SafeArea(
            margin_top=60 if res[0] > res[1] else 120,
            margin_bottom=124 if res[0] > res[1] else 330,
            margin_left=85 if res[0] > res[1] else 72,
            margin_right=85 if res[0] > res[1] else 72,
        ),
        scenes=adapted_scenes,
    )



def save_scene_manifest(
    manifest_data: Union[SceneManifestV2, Dict[str, Any]],
    output_path: Union[Path, str],
) -> Path:
    """Serializes, validates, and writes a scene manifest to disk."""
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(manifest_data, SceneManifestV2):
        dict_data = manifest_data.model_dump(exclude_none=True)
    elif isinstance(manifest_data, dict):
        dict_data = manifest_data
    else:
        raise ValueError("manifest_data must be SceneManifestV2 or dict")

    out_p.write_text(json.dumps(dict_data, indent=2, ensure_ascii=False), encoding="utf-8")
    validate_scene_manifest(out_p)
    logger.info("Saved and validated scene manifest at %s", out_p)
    return out_p


# ---------------------------------------------------------------------------
# High-Level Builders
# ---------------------------------------------------------------------------

def build_scene_manifest_v2(
    *,
    work_dir: Union[Path, str],
    story_id: str = "story_001",
    lane_id: str = "moku-horror-long",
    channel_name: str = "moku",
    total_duration_sec: float,
    narration_path: Union[Path, str],
    music_path: Optional[Union[Path, str]] = None,
    music_volume: float = 0.04,
    scenes: Optional[List[Dict[str, Any]]] = None,
    subtitles: Optional[List[Dict[str, Any]]] = None,
    resolution: Tuple[int, int] = LONGFORM_RESOLUTION,
    fps: int = 30,
    safe_area: Optional[Dict[str, int]] = None,
    color_profile: Optional[Dict[str, str]] = None,
    ducking_params: Optional[Dict[str, Any]] = None,
    sfx_cues: Optional[List[Dict[str, Any]]] = None,
    hook_text: Optional[str] = None,
) -> Path:
    """
    Constructs, validates, and persists a canonical v2.0 Scene Manifest.
    """
    w_dir = Path(work_dir)
    manifest_path = w_dir / "scene_manifest.json"

    # Default safe area based on aspect ratio
    if safe_area is None:
        if resolution[0] == 1080 and resolution[1] == 1920:
            # Vertical shorts safe area
            safe_area = {"margin_top": 60, "margin_bottom": 330, "margin_left": 72, "margin_right": 72}
        else:
            # Horizontal longform safe area
            safe_area = {"margin_top": 60, "margin_bottom": 124, "margin_left": 85, "margin_right": 85}

    # Audio tracks configuration
    ducking_obj = ducking_params or {
        "enabled": True,
        "threshold": 0.035,
        "ratio": 8.0,
        "attack_ms": 20.0,
        "release_ms": 350.0,
        "target_lufs": -14.0,
        "max_tp": -1.5,
        "lra": 11.0,
    }

    parsed_sfx: List[Dict[str, Any]] = []
    if sfx_cues:
        for cue in sfx_cues:
            parsed_sfx.append({
                "sfx_id": cue.get("sfx_id"),
                "sfx_path": str(cue["sfx_path"]),
                "timestamp_sec": float(cue["timestamp_sec"]),
                "volume": float(cue.get("volume", 0.6)),
                "pan": float(cue.get("pan", 0.0)),
            })

    audio_tracks_data: Dict[str, Any] = {
        "narration_path": str(narration_path),
        "music_path": str(music_path) if music_path else "",
        "music_volume": float(music_volume),
        "ducking": ducking_obj,
        "sfx_cues": parsed_sfx,
    }

    # Parse and construct scene list if not explicitly provided
    scene_list: List[Dict[str, Any]] = []
    if scenes:
        for sc in scenes:
            scene_list.append(sc)
    else:
        # Default single procedural scene if none provided
        scene_list.append({
            "scene_index": 1,
            "scene_id": f"{story_id}_scene_01",
            "environment_name": "Default Environment",
            "start_sec": 0.0,
            "duration_sec": round(float(total_duration_sec), 3),
            "tension_level": 3,
            "engine_type": "pure_procedural_webgl",
            "procedural_config": {
                "template_name": "cosmic_horror_three.html",
                "seed": 42,
                "palette": {
                    "base_dark": "#020104",
                    "mid_tone": "#1e0838",
                    "accent": "#780a1e",
                },
                "uniforms": {
                    "u_noise_scale": 1.0,
                    "u_speed": 1.0,
                    "u_distortion": 0.5,
                    "u_glow_intensity": 0.8,
                },
            },
            "transition_out": {
                "type": "crossfade",
                "duration_sec": 0.8,
            },
        })

    # Subtitles mapping
    subtitle_list: List[Dict[str, Any]] = []
    if subtitles:
        for sub in subtitles:
            subtitle_list.append({
                "start": round(float(sub.get("start", 0.0)), 3),
                "end": round(float(sub.get("end", 0.0)), 3),
                "text": str(sub.get("text") or sub.get("word") or "").strip(),
            })

    manifest_payload: Dict[str, Any] = {
        "manifest_version": "2.0",
        "story_id": story_id,
        "lane_id": lane_id,
        "channel_name": channel_name,
        "resolution": list(resolution),
        "fps": fps,
        "total_duration_sec": round(float(total_duration_sec), 3),
        "color_profile": color_profile or {
            "color_space": "bt709",
            "color_primaries": "bt709",
            "color_trc": "bt709",
            "pixel_format": "yuv420p",
        },
        "audio_tracks": audio_tracks_data,
        "safe_area": safe_area,
        "scenes": scene_list,
        "subtitles": subtitle_list,
        "hook_text": hook_text or story_id,
    }

    manifest = SceneManifestV2.model_validate(manifest_payload)
    return save_scene_manifest(manifest, manifest_path)


# Backwards-compatible builder for v1 callers
def build_scene_manifest(
    *,
    work_dir: Union[Path, str],
    scp_id: str = "story-000",
    title: str = "Historia",
    object_class: str = "moku",
    attribution: str = "Fuente original",
    narration_path: Union[Path, str],
    music_path: Optional[Union[Path, str]] = None,
    duration_sec: float,
    scene_images: List[str],
    subtitles: List[Dict[str, Any]],
    resolution: Tuple[int, int] = SHORT_RESOLUTION,
    fps: int = 30,
    stamp_text: str = "[MOKU]",
    channel_name: str = "moku",
    thumbnail_candidate_timestamp: float = 5.0,
    shot_durations: Optional[List[float]] = None,
) -> Path:
    """
    Legacy backwards-compatible builder for scene_manifest.json.
    """
    w_dir = Path(work_dir)
    manifest_path = w_dir / "scene_manifest.json"

    scenes: List[Dict[str, Any]] = []
    if scene_images:
        num_scenes = len(scene_images)
        if shot_durations and len(shot_durations) == num_scenes:
            durs = [round(float(d), 3) for d in shot_durations]
        else:
            scene_dur = duration_sec / max(1, num_scenes)
            durs = [round(scene_dur, 3)] * num_scenes
            drift = round(duration_sec - sum(durs), 3)
            if durs:
                durs[-1] = round(durs[-1] + drift, 3)
        cum = 0.0
        for idx, img_p in enumerate(scene_images):
            dur = durs[idx]
            scenes.append({
                "scene_index": idx + 1,
                "start_sec": round(cum, 3),
                "duration_sec": round(dur, 3),
                "image_path": str(img_p),
                "framing": {
                    "zoom_start": 1.0,
                    "zoom_end": 1.12,
                    "pan_direction": "center_to_top" if idx % 2 == 0 else "center_to_bottom",
                },
                "effects": ["vignette", "film_grain"],
                "transition": {"type": "fade", "duration_sec": 0.2},
            })
            cum += dur

    sub_cues: List[Dict[str, Any]] = []
    for s in subtitles:
        sub_cues.append({
            "start": round(float(s.get("start", 0.0)), 3),
            "end": round(float(s.get("end", 0.0)), 3),
            "text": str(s.get("word") or s.get("text") or "").strip(),
        })

    manifest_data: Dict[str, Any] = {
        "version": "1.0",
        "resolution": list(resolution),
        "fps": fps,
        "duration_sec": round(duration_sec, 3),
        "audio": {
            "narration_path": str(narration_path),
            "music_path": str(music_path) if music_path else "",
            "music_volume": 0.04,
        },
        "story": {
            "story_id": scp_id,
            "title": title,
            "slot": object_class,
            "attribution": attribution,
        },
        "branding": {
            "stamp_text": stamp_text,
            "channel_name": channel_name,
        },
        "safe_area": {
            "margin_v": 330 if resolution != (1280, 720) and resolution != (1920, 1080) else 124,
            "margin_l": 72 if resolution != (1280, 720) and resolution != (1920, 1080) else 85,
            "margin_r": 72 if resolution != (1280, 720) and resolution != (1920, 1080) else 85,
        },
        "scenes": scenes,
        "subtitles": sub_cues,
        "hook_text": title,
        "thumbnail_candidate_timestamp": thumbnail_candidate_timestamp,
        "cache_keys": {
            "audio_path": str(narration_path),
            "image_count": len(scene_images),
        },
    }

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved legacy scene_manifest.json at %s (%d scenes)", manifest_path, len(scenes))
    validate_scene_manifest(manifest_path)
    return manifest_path
