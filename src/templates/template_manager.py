"""
Template management system defining video presets, subtitle styling, audio mixing,
visual filters, and thumbnail design templates.
"""
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional
import json
import os
from src.log import get_logger

logger = get_logger("templates")


@dataclass
class SubtitleStyle:
    font_name: str = "Montserrat Black"
    font_size: int = 75
    primary_color: str = "&H0000FFFF"      # Yellow active text in ASS (&H00BBGGRR)
    secondary_color: str = "&H00FFFFFF"    # White inactive text
    outline_color: str = "&H00000000"      # Black outline
    back_color: str = "&H80000000"         # Dark shadow / panel fill
    bold: bool = True
    outline_width: int = 4
    shadow_depth: int = 3
    alignment: int = 5                      # 5 = Middle-Center
    margin_v: int = 230                    # Safe zone 180..280
    margin_l: int = 40
    margin_r: int = 40
    group_size: int = 4                     # 4 words per line for multi-word block layout
    style_type: str = "karaoke"             # "karaoke", "standard", "boxed"
    border_style: int = 1                   # 1 = outline + shadow, 3 = boxed background panel



@dataclass
class AudioStyle:
    speech_volume: float = 1.0
    music_volume: float = 0.012
    ambient_volume: float = 0.15
    lowpass_freq: int = 3000                # Lowpass filter frequency (0 = disabled)
    highpass_freq: int = 0                  # Highpass filter frequency (0 = disabled)
    sidechain_threshold: float = 0.05
    sidechain_ratio: float = 5.0
    fade_duration: float = 3.0


@dataclass
class VisualEffectStyle:
    resolution: str = "1920x1080"
    fps: int = 30
    zoom_speed: float = 0.0008
    max_zoom: float = 1.3
    contrast: float = 1.15
    brightness: float = -0.05
    saturation: float = 0.85
    enable_vignette: bool = True
    vignette_expr: str = "PI/4"
    scene_duration_sec: float = 15.0        # Duration before switching background in multi-scene mode


@dataclass
class ThumbnailStyle:
    layout_type: str = "neon_horror"        # "neon_horror", "reddit_card", "cyberpunk", "documentary"
    primary_font_size: int = 90
    accent_color_1: str = "#FFE600"         # Neon Yellow
    accent_color_2: str = "#FF003B"         # Crimson Red
    stroke_color: str = "#000000"
    card_border_color: str = "#FF4500"      # Reddit Orange
    card_bg_color: str = "#0F0F16"
    contrast_boost: float = 1.25
    color_boost: float = 1.15


@dataclass
class VideoTemplate:
    name: str
    description: str = ""
    subtitles: SubtitleStyle = field(default_factory=SubtitleStyle)
    audio: AudioStyle = field(default_factory=AudioStyle)
    visual: VisualEffectStyle = field(default_factory=VisualEffectStyle)
    thumbnail: ThumbnailStyle = field(default_factory=ThumbnailStyle)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VideoTemplate":
        name = data.get("name", "custom")
        desc = data.get("description", "")
        
        sub_data = data.get("subtitles", {})
        subtitles = SubtitleStyle(**sub_data) if isinstance(sub_data, dict) else SubtitleStyle()
        
        aud_data = data.get("audio", {})
        audio = AudioStyle(**aud_data) if isinstance(aud_data, dict) else AudioStyle()
        
        vis_data = data.get("visual", {})
        visual = VisualEffectStyle(**vis_data) if isinstance(vis_data, dict) else VisualEffectStyle()
        
        thumb_data = data.get("thumbnail", {})
        thumbnail = ThumbnailStyle(**thumb_data) if isinstance(thumb_data, dict) else ThumbnailStyle()
        
        return cls(name=name, description=desc, subtitles=subtitles, audio=audio, visual=visual, thumbnail=thumbnail)


class TemplateRegistry:
    """Registry managing video production templates."""

    def __init__(self):
        self._templates: Dict[str, VideoTemplate] = {}
        self._load_defaults()

    def _load_defaults(self):
        # 1. Creepypasta / Horror Default Template
        creepypasta = VideoTemplate(
            name="creepypasta",
            description="Atmospheric dark horror style with lowpass audio, neon captions, and dramatic vignette",
            subtitles=SubtitleStyle(
                font_name="Montserrat Black",
                font_size=75,
                primary_color="&H0000FFFF",   # Neon Yellow
                secondary_color="&H00FFFFFF", # White
                outline_width=4,
                shadow_depth=4,
                margin_v=230,
                group_size=1
            ),
            audio=AudioStyle(
                speech_volume=1.0,
                music_volume=0.012,
                ambient_volume=0.15,
                lowpass_freq=3000,
                sidechain_threshold=0.05,
                sidechain_ratio=5.0
            ),
            visual=VisualEffectStyle(
                resolution="1280x720",
                zoom_speed=0.0008,
                max_zoom=1.3,
                contrast=1.15,
                brightness=-0.05,
                saturation=0.85,
                enable_vignette=True,
                scene_duration_sec=12.0
            ),
            thumbnail=ThumbnailStyle(
                layout_type="neon_horror",
                primary_font_size=90,
                accent_color_1="#FFE600",
                accent_color_2="#FF003B",
                contrast_boost=1.25
            )
        )

        # 2. AITA / Reddit Story Default Template
        aita = VideoTemplate(
            name="aita",
            description="Clean Reddit story format with clear audio, card thumbnail layout, and high-visibility subtitles",
            subtitles=SubtitleStyle(
                font_name="Montserrat Black",
                font_size=75,
                primary_color="&H0000FFFF",
                secondary_color="&H00FFFFFF",
                outline_width=4,
                shadow_depth=3,
                margin_v=230,
                group_size=1
            ),
            audio=AudioStyle(
                speech_volume=1.0,
                music_volume=0.05,
                ambient_volume=0.08,
                lowpass_freq=0,               # Clean full audio range
                sidechain_threshold=0.05,
                sidechain_ratio=4.0
            ),
            visual=VisualEffectStyle(
                resolution="1280x720",
                zoom_speed=0.0006,
                max_zoom=1.25,
                contrast=1.05,
                brightness=0.0,
                saturation=1.0,
                enable_vignette=False,
                scene_duration_sec=20.0
            ),
            thumbnail=ThumbnailStyle(
                layout_type="reddit_card",
                primary_font_size=75,
                accent_color_1="#FFFFFF",
                accent_color_2="#FF4500",
                card_border_color="#FF4500",
                card_bg_color="#0F0F16",
                contrast_boost=1.1
            )
        )

        # 3. Cyberpunk Neon Template
        cyberpunk = VideoTemplate(
            name="cyberpunk",
            description="Futuristic neon sci-fi theme with cyan/magenta accents and energetic dynamic zoom",
            subtitles=SubtitleStyle(
                font_name="Montserrat Black",
                font_size=80,
                primary_color="&H00FFFF00",   # Cyan
                secondary_color="&H00FF00FF", # Magenta
                outline_width=4,
                shadow_depth=5,
                margin_v=230,
                group_size=1
            ),
            audio=AudioStyle(
                speech_volume=1.0,
                music_volume=0.025,
                ambient_volume=0.10,
                lowpass_freq=0
            ),
            visual=VisualEffectStyle(
                resolution="1280x720",
                zoom_speed=0.0012,
                max_zoom=1.35,
                contrast=1.2,
                brightness=0.0,
                saturation=1.2,
                enable_vignette=True,
                vignette_expr="PI/3",
                scene_duration_sec=12.0
            ),
            thumbnail=ThumbnailStyle(
                layout_type="cyberpunk",
                primary_font_size=95,
                accent_color_1="#00FFFF",
                accent_color_2="#FF00FF",
                contrast_boost=1.3
            )
        )

        # 4. Documentary Dramatic Template
        documentary = VideoTemplate(
            name="documentary",
            description="Cinematic documentary style with desaturated tones, subtle motion, and elegant audio",
            subtitles=SubtitleStyle(
                font_name="Montserrat Black",
                font_size=70,
                primary_color="&H00FFFFFF",
                secondary_color="&H00CCCCCC",
                outline_width=4,
                shadow_depth=3,
                margin_v=230,
                group_size=1
            ),
            audio=AudioStyle(
                speech_volume=1.0,
                music_volume=0.02,
                ambient_volume=0.05,
                lowpass_freq=0
            ),
            visual=VisualEffectStyle(
                resolution="1280x720",
                zoom_speed=0.0004,
                max_zoom=1.15,
                contrast=1.1,
                brightness=-0.02,
                saturation=0.75,
                enable_vignette=True,
                scene_duration_sec=15.0
            ),
            thumbnail=ThumbnailStyle(
                layout_type="documentary",
                primary_font_size=85,
                accent_color_1="#FFFFFF",
                accent_color_2="#E0E0E0",
                contrast_boost=1.2
            )
        )

        # 5. SCP Classified Preset
        scp_classified = VideoTemplate(
            name="scp_classified",
            description="SCP Foundation official classified documentary preset with green night-vision aesthetic",
            subtitles=SubtitleStyle(
                font_name="Montserrat Black",
                font_size=52,
                primary_color="&H000000FF",   # Red active text
                secondary_color="&H0000FFFF", # Yellow inactive text
                outline_color="&H00FFFFFF",   # White outline
                back_color="&HAA000000",
                outline_width=4,
                shadow_depth=3,
                alignment=5,
                margin_v=240,
                group_size=3,
                border_style=1
            ),
            audio=AudioStyle(
                speech_volume=1.0,
                music_volume=0.015,
                ambient_volume=0.12,
                lowpass_freq=2800,
                sidechain_threshold=0.05
            ),
            visual=VisualEffectStyle(
                resolution="720x1280",
                zoom_speed=0.001,
                max_zoom=1.25,
                contrast=1.2,
                brightness=-0.04,
                saturation=0.85,
                enable_vignette=True,
                vignette_expr="PI/3.5",
                scene_duration_sec=12.0
            ),
            thumbnail=ThumbnailStyle(
                layout_type="neon_horror",
                primary_font_size=85,
                accent_color_1="#00FF66",
                accent_color_2="#FF003B"
            )
        )

        # 6. Shorts Creepypasta Preset (9:16)
        shorts_creepypasta = VideoTemplate(
            name="shorts_creepypasta",
            description="Vertical 9:16 Creepypasta preset with centered ASS karaoke subtitles and dark vignette",
            subtitles=SubtitleStyle(
                font_name="Montserrat Black",
                font_size=64,
                primary_color="&H000000FF",   # Bright Red active text
                secondary_color="&H0000FFFF", # Bright Yellow inactive text
                outline_color="&H00FFFFFF",   # Solid White outline
                back_color="&HAA000000",      # Translucent drop shadow
                outline_width=5,
                shadow_depth=4,
                alignment=5,
                margin_v=250,
                group_size=2,
                border_style=1
            ),
            audio=AudioStyle(
                speech_volume=1.0,
                music_volume=0.012,
                ambient_volume=0.15,
                lowpass_freq=3000
            ),
            visual=VisualEffectStyle(
                resolution="720x1280",
                zoom_speed=0.001,
                max_zoom=1.25,
                contrast=1.12,
                brightness=0.02,
                saturation=0.9,
                enable_vignette=True,
                vignette_expr="PI/5"
            ),
            thumbnail=ThumbnailStyle(
                layout_type="neon_horror",
                accent_color_1="#FFE600",
                accent_color_2="#FF003B"
            )
        )

        # 7. Shorts AITA Preset (9:16)
        shorts_aita = VideoTemplate(
            name="shorts_aita",
            description="Vertical 9:16 Reddit AITA preset with high-visibility ASS karaoke subtitles and clean audio",
            subtitles=SubtitleStyle(
                font_name="Montserrat Black",
                font_size=64,
                primary_color="&H000000FF",   # Bright Red active text
                secondary_color="&H0000FFFF", # Bright Yellow inactive text
                outline_color="&H00FFFFFF",   # Solid White outline
                back_color="&HAA000000",      # Translucent drop shadow
                outline_width=5,
                shadow_depth=4,
                alignment=5,
                margin_v=250,
                group_size=2,
                border_style=1
            ),
            audio=AudioStyle(
                speech_volume=1.0,
                music_volume=0.04,
                ambient_volume=0.06,
                lowpass_freq=0
            ),
            visual=VisualEffectStyle(
                resolution="720x1280",
                zoom_speed=0.0006,
                max_zoom=1.2,
                contrast=1.1,
                brightness=0.0,
                saturation=1.0,
                enable_vignette=False
            ),
            thumbnail=ThumbnailStyle(
                layout_type="reddit_card",
                accent_color_1="#FFFFFF",
                accent_color_2="#FF4500"
            )
        )

        # 8. Shorts Cyberpunk Preset (9:16)
        shorts_cyberpunk = VideoTemplate(
            name="shorts_cyberpunk",
            description="Vertical 9:16 Cyberpunk preset with neon cyan/magenta styling and dynamic high-contrast zoom",
            subtitles=SubtitleStyle(
                font_name="Montserrat Black",
                font_size=64,
                primary_color="&H000000FF",   # Bright Red active text
                secondary_color="&H0000FFFF", # Bright Yellow inactive text
                outline_color="&H00FFFFFF",   # White outline
                outline_width=4,
                shadow_depth=4,
                alignment=5,
                margin_v=240,
                group_size=2,
                border_style=1
            ),
            audio=AudioStyle(
                speech_volume=1.0,
                music_volume=0.025,
                ambient_volume=0.10,
                lowpass_freq=0
            ),
            visual=VisualEffectStyle(
                resolution="720x1280",
                zoom_speed=0.0012,
                max_zoom=1.3,
                contrast=1.25,
                brightness=0.0,
                saturation=1.25,
                enable_vignette=True
            ),
            thumbnail=ThumbnailStyle(
                layout_type="cyberpunk",
                accent_color_1="#00E5FF",
                accent_color_2="#FF007F"
            )
        )

        # 9. Shorts Documentary Preset (9:16)
        shorts_documentary = VideoTemplate(
            name="shorts_documentary",
            description="Vertical 9:16 Documentary preset with cinematic muted tones and balanced typography",
            subtitles=SubtitleStyle(
                font_name="Montserrat Black",
                font_size=64,
                primary_color="&H000000FF",   # Bright Red active text
                secondary_color="&H0000FFFF", # Bright Yellow inactive text
                outline_color="&H00FFFFFF",   # White outline
                outline_width=4,
                shadow_depth=3,
                alignment=5,
                margin_v=240,
                group_size=2,
                border_style=1
            ),
            audio=AudioStyle(
                speech_volume=1.0,
                music_volume=0.02,
                ambient_volume=0.05,
                lowpass_freq=0
            ),
            visual=VisualEffectStyle(
                resolution="720x1280",
                zoom_speed=0.0004,
                max_zoom=1.15,
                contrast=1.1,
                brightness=-0.02,
                saturation=0.8,
                enable_vignette=True
            ),
            thumbnail=ThumbnailStyle(
                layout_type="documentary",
                accent_color_1="#FFFFFF",
                accent_color_2="#E0E0E0"
            )
        )

        self.register_template(creepypasta)
        self.register_template(aita)
        self.register_template(cyberpunk)
        self.register_template(documentary)
        self.register_template(scp_classified)
        self.register_template(shorts_creepypasta)
        self.register_template(shorts_aita)
        self.register_template(shorts_cyberpunk)
        self.register_template(shorts_documentary)


    def register_template(self, template: VideoTemplate):
        self._templates[template.name.lower()] = template
        logger.debug(f"Registered video template '{template.name}'")

    def get_template(self, name: str) -> VideoTemplate:
        key = name.lower() if name else "creepypasta"
        if key not in self._templates:
            logger.warning(f"Template '{name}' not found in registry. Falling back to 'creepypasta'.")
            return self._templates["creepypasta"]
        return self._templates[key]

    def list_templates(self) -> Dict[str, str]:
        return {name: t.description for name, t in self._templates.items()}

    def load_from_json(self, json_path: str) -> VideoTemplate:
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"Template file not found: {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        tpl = VideoTemplate.from_dict(data)
        self.register_template(tpl)
        return tpl


# Global singleton registry instance
_default_registry = TemplateRegistry()


def get_template(name_or_template: Any) -> VideoTemplate:
    """Helper function to resolve string or VideoTemplate into a VideoTemplate object."""
    if isinstance(name_or_template, VideoTemplate):
        return name_or_template
    if isinstance(name_or_template, str) and name_or_template.strip():
        return _default_registry.get_template(name_or_template.strip())
    return _default_registry.get_template("creepypasta")
