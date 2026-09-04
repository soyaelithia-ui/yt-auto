"""
src/core/channel_profile.py - Declarative Channel Profile Domain Model and Dynamic Registry.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("channel_profile")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_CHANNELS_DIR = REPO_ROOT / "config" / "channels"


@dataclass(frozen=True)
class TypographyConfig:
    font_bold: str = "Montserrat-Black.ttf"
    font_regular: str = "Montserrat-Black.ttf"
    font_subtitles: str = "Montserrat Black"
    subtitle_font_size: int = 64
    subtitle_primary_color: str = "&H0000FFFF"  # Yellow in ASS (&H00BBGGRR)
    subtitle_secondary_color: str = "&H00FFFFFF"
    subtitle_outline_color: str = "&H00000000"
    subtitle_back_color: str = "&HAA000000"
    subtitle_outline_width: int = 4
    subtitle_shadow_depth: int = 3
    subtitle_alignment: int = 5                  # Center
    subtitle_margin_v: int = 240


@dataclass(frozen=True)
class PaletteConfig:
    primary: str
    secondary: str
    accent: str
    shadow: str
    highlight: str
    kelvin: int = 5600
    lut_profile: str = "standard_rec709"
    contrast_curve: str = "cinematic_s_curve"
    saturation_modifier: float = 1.0


@dataclass(frozen=True)
class VisualStrategyConfig:
    style_id: str
    palette: PaletteConfig
    typography: TypographyConfig = field(default_factory=TypographyConfig)
    default_weather_effect: str = "none"
    default_particle_layer: str = "dust_motes"
    default_camera_motion: str = "slow_zoom_in"
    vignette_default_strength: float = 0.35
    watermark_text: str = ""
    prompt_style_prefix: str = "Masterpiece 8k cinematic atmospheric matte painting"
    prompt_style_suffix: str = "35mm photograph, shot on Arri Alexa, Rec.709 color grade"
    negative_prompt: str = "deformed, distorted, cartoon, low resolution, cluttered"
    archetype_mappings: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AudioStrategyConfig:
    default_voice_profile: str
    default_tts_provider: str = "edge-tts"
    speech_volume: float = 1.0
    music_volume: float = 0.04
    ambient_volume: float = 0.10
    ducking_db: float = -18.0
    default_bg_theme: str = "default"


@dataclass(frozen=True)
class EditorialMetadataConfig:
    public_name: str
    handle: str
    topic: str
    tone: str
    channel_url: str
    persona_system_prompt: str
    language: str = "es"
    category_id: str = "24"
    title_prefix: str = ""
    title_suffix: str = ""
    default_title_fallback: str = "Relato"
    description_summary_template: str = "Una impactante narración en {public_name}."
    community_question: str = "¿Qué opinas de esta historia? Déjanos tu perspectiva en los comentarios."
    tags: Tuple[str, ...] = ()
    shorts_hashtags: Tuple[str, ...] = ("#Shorts",)
    thematic_scoring_keywords: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ChannelAuthConfig:
    cookies_path: Path
    youtube_token_path: Path
    expected_youtube_channel_id: str
    source_feed: str


@dataclass(frozen=True)
class ChannelProfile:
    id: str
    enabled: bool
    editorial: EditorialMetadataConfig
    visual: VisualStrategyConfig
    audio: AudioStrategyConfig
    auth: ChannelAuthConfig


class ChannelProfileRegistry:
    """
    Thread-safe registry for declarative channel profiles.
    Loads and caches JSON configurations from config/channels/.
    """
    _cache: Dict[str, ChannelProfile] = {}
    _cache_mtimes: Dict[str, int] = {}

    @classmethod
    def get_channel(cls, channel_id_or_alias: str) -> ChannelProfile:
        cls._ensure_loaded()
        normalized = cls.normalize_channel_id(channel_id_or_alias)
        if normalized in cls._cache:
            base = cls._cache[normalized]
            return cls._apply_env_overrides(base)
        raise KeyError(f"Canal desconocido o no configurado en config/channels/: {channel_id_or_alias!r}")

    @classmethod
    def list_active_channels(cls) -> List[ChannelProfile]:
        cls._ensure_loaded()
        return [cls._apply_env_overrides(p) for p in cls._cache.values() if p.enabled]

    @classmethod
    def _apply_env_overrides(cls, profile: ChannelProfile) -> ChannelProfile:
        cid = profile.id
        prefix = cid.upper()
        active_channel_env = os.environ.get("CHANNEL_KEY", "").strip().lower()
        use_generic_env = (active_channel_env == cid or not active_channel_env)

        handle = (
            os.environ.get(f"{prefix}_HANDLE")
            or (os.environ.get("CHANNEL_HANDLE") if use_generic_env and "CHANNEL_HANDLE" in os.environ else None)
            or profile.editorial.handle
        )
        channel_url = (
            os.environ.get(f"{prefix}_CHANNEL_URL")
            or (os.environ.get("CHANNEL_URL") if use_generic_env and "CHANNEL_URL" in os.environ else None)
            or profile.editorial.channel_url
        )
        public_name = (
            os.environ.get(f"{prefix}_NAME")
            or os.environ.get(f"{prefix}_PUBLIC_NAME")
            or (os.environ.get("CHANNEL_NAME") if use_generic_env and "CHANNEL_NAME" in os.environ else None)
            or profile.editorial.public_name
        )

        watermark_text = (
            os.environ.get(f"{prefix}_WATERMARK")
            or (os.environ.get("CHANNEL_WATERMARK") if use_generic_env and "CHANNEL_WATERMARK" in os.environ else None)
            or profile.visual.watermark_text
        )

        voice = os.environ.get(f"{prefix}_TTS_VOICE") or profile.audio.default_voice_profile
        tts_provider = os.environ.get(f"{prefix}_TTS_PROVIDER") or profile.audio.default_tts_provider
        cookies_path = (
            Path(os.environ[f"{prefix}_COOKIES_PATH"]).expanduser().resolve()
            if f"{prefix}_COOKIES_PATH" in os.environ
            else profile.auth.cookies_path
        )
        youtube_token_path = (
            Path(os.environ[f"{prefix}_YOUTUBE_TOKEN_PATH"]).expanduser().resolve()
            if f"{prefix}_YOUTUBE_TOKEN_PATH" in os.environ
            else profile.auth.youtube_token_path
        )
        expected_channel_id = (
            os.environ.get(f"{prefix}_YOUTUBE_CHANNEL_ID")
            or profile.auth.expected_youtube_channel_id
        ).strip()
        source_feed = os.environ.get(f"{prefix}_SOURCE_FEED") or profile.auth.source_feed

        if (
            handle == profile.editorial.handle
            and channel_url == profile.editorial.channel_url
            and public_name == profile.editorial.public_name
            and watermark_text == profile.visual.watermark_text
            and voice == profile.audio.default_voice_profile
            and tts_provider == profile.audio.default_tts_provider
            and cookies_path == profile.auth.cookies_path
            and youtube_token_path == profile.auth.youtube_token_path
            and expected_channel_id == profile.auth.expected_youtube_channel_id
            and source_feed == profile.auth.source_feed
        ):
            return profile

        from dataclasses import replace
        new_editorial = replace(
            profile.editorial,
            public_name=public_name,
            handle=handle,
            channel_url=channel_url,
            title_suffix=f" | {public_name}" if profile.editorial.title_suffix.startswith(" | ") else profile.editorial.title_suffix,
            description_summary_template=f"Una impactante narración en {public_name}." if "{public_name}" not in profile.editorial.description_summary_template else profile.editorial.description_summary_template,
        )
        new_visual = replace(
            profile.visual,
            watermark_text=watermark_text,
        )
        new_audio = replace(
            profile.audio,
            default_voice_profile=voice,
            default_tts_provider=tts_provider,
        )
        new_auth = replace(
            profile.auth,
            cookies_path=cookies_path,
            youtube_token_path=youtube_token_path,
            expected_youtube_channel_id=expected_channel_id,
            source_feed=source_feed,
        )
        return replace(
            profile,
            editorial=new_editorial,
            visual=new_visual,
            audio=new_audio,
            auth=new_auth,
        )

    @classmethod
    def list_active_channel_ids(cls) -> List[str]:
        cls._ensure_loaded()
        return [p.id for p in cls._cache.values() if p.enabled]

    @classmethod
    def normalize_channel_id(cls, raw: Any) -> str:
        if hasattr(raw, "value"):
            s = str(raw.value).strip().lower()
        else:
            s = (str(raw or "")).strip().lower()
        if s in ("moku", "channel1", "primary", "terror", "scp", "horror") or s.startswith("moku-") or "moku" in s:
            return "moku"
        if s in ("aelithia", "channel2", "secondary", "aita", "reddit", "drama", "soy_el_malo") or s.startswith("aelithia-") or "aelithia" in s:
            return "aelithia"
        if s in ("scifi", "sci_fi", "space", "singularidad") or s.startswith("scifi-") or "scifi" in s:
            return "scifi"
        return s

    @classmethod
    def _ensure_loaded(cls, force_reload: bool = False) -> None:
        if not CONFIG_CHANNELS_DIR.exists():
            CONFIG_CHANNELS_DIR.mkdir(parents=True, exist_ok=True)
            return

        json_files = list(CONFIG_CHANNELS_DIR.glob("*.json"))
        for jf in json_files:
            try:
                mtime = jf.stat().st_mtime_ns
                cid = jf.stem.lower()
                if not force_reload and cid in cls._cache and cls._cache_mtimes.get(cid) == mtime:
                    continue

                with open(jf, "r", encoding="utf-8") as f:
                    data = json.load(f)

                profile = cls._parse_profile_dict(data, jf)
                cls._cache[profile.id] = profile
                cls._cache_mtimes[profile.id] = mtime
            except Exception as e:
                logger.warning("Failed to load channel profile from %s: %s", jf, e)

    @classmethod
    def _parse_profile_dict(cls, data: Dict[str, Any], file_path: Path) -> ChannelProfile:
        cid = str(data.get("id", file_path.stem)).lower()
        enabled = bool(data.get("enabled", True))

        # Editorial
        ed_data = data.get("editorial", {})
        public_name = ed_data.get("public_name", cid.capitalize())
        editorial = EditorialMetadataConfig(
            public_name=public_name,
            handle=ed_data.get("handle", f"@{cid}"),
            topic=ed_data.get("topic", "relatos e historias"),
            tone=ed_data.get("tone", "cinemático"),
            channel_url=ed_data.get("channel_url", "https://youtube.com"),
            persona_system_prompt=ed_data.get("persona_system_prompt", "Eres un narrador profesional."),
            language=ed_data.get("language", "es"),
            category_id=ed_data.get("category_id", "24"),
            title_prefix=ed_data.get("title_prefix", ""),
            title_suffix=ed_data.get("title_suffix", f" | {public_name}"),
            default_title_fallback=ed_data.get("default_title_fallback", "Relato"),
            description_summary_template=ed_data.get("description_summary_template", f"Una impactante narración en {public_name}."),
            community_question=ed_data.get("community_question", "¿Qué opinas? Déjanos tu comentario."),
            tags=tuple(ed_data.get("tags", [cid])),
            shorts_hashtags=tuple(ed_data.get("shorts_hashtags", ["#Shorts"])),
            thematic_scoring_keywords=tuple(ed_data.get("thematic_scoring_keywords", [])),
        )

        # Visual
        vis_data = data.get("visual", {})
        pal_data = vis_data.get("palette", {})
        palette = PaletteConfig(
            primary=pal_data.get("primary", "#020408"),
            secondary=pal_data.get("secondary", "#0A192F"),
            accent=pal_data.get("accent", "#00FF66"),
            shadow=pal_data.get("shadow", "#000000"),
            highlight=pal_data.get("highlight", "#FFFFFF"),
            kelvin=int(pal_data.get("kelvin", 5600)),
            lut_profile=pal_data.get("lut_profile", "standard_rec709"),
            contrast_curve=pal_data.get("contrast_curve", "cinematic_s_curve"),
            saturation_modifier=float(pal_data.get("saturation_modifier", 1.0)),
        )

        typo_data = vis_data.get("typography", {})
        typography = TypographyConfig(
            font_bold=typo_data.get("font_bold", "Montserrat-Black.ttf"),
            font_regular=typo_data.get("font_regular", "Montserrat-Black.ttf"),
            font_subtitles=typo_data.get("font_subtitles", "Montserrat Black"),
            subtitle_font_size=int(typo_data.get("subtitle_font_size", 64)),
            subtitle_primary_color=typo_data.get("subtitle_primary_color", "&H0000FFFF"),
            subtitle_secondary_color=typo_data.get("subtitle_secondary_color", "&H00FFFFFF"),
            subtitle_outline_color=typo_data.get("subtitle_outline_color", "&H00000000"),
            subtitle_back_color=typo_data.get("subtitle_back_color", "&HAA000000"),
            subtitle_outline_width=int(typo_data.get("subtitle_outline_width", 4)),
            subtitle_shadow_depth=int(typo_data.get("subtitle_shadow_depth", 3)),
            subtitle_alignment=int(typo_data.get("subtitle_alignment", 5)),
            subtitle_margin_v=int(typo_data.get("subtitle_margin_v", 240)),
        )

        visual = VisualStrategyConfig(
            style_id=vis_data.get("style_id", "default_cinematic"),
            palette=palette,
            typography=typography,
            default_weather_effect=vis_data.get("default_weather_effect", "none"),
            default_particle_layer=vis_data.get("default_particle_layer", "dust_motes"),
            default_camera_motion=vis_data.get("default_camera_motion", "slow_zoom_in"),
            vignette_default_strength=float(vis_data.get("vignette_default_strength", 0.35)),
            watermark_text=vis_data.get("watermark_text", ""),
            prompt_style_prefix=vis_data.get("prompt_style_prefix", "Masterpiece 8k cinematic atmospheric matte painting"),
            prompt_style_suffix=vis_data.get("prompt_style_suffix", "35mm photograph, shot on Arri Alexa, Rec.709 color grade"),
            negative_prompt=vis_data.get("negative_prompt", "deformed, distorted, cartoon, low resolution"),
            archetype_mappings=vis_data.get("archetype_mappings", {}),
        )

        # Audio
        aud_data = data.get("audio", {})
        audio = AudioStrategyConfig(
            default_voice_profile=aud_data.get("default_voice_profile", "es-ES-AlvaroNeural"),
            default_tts_provider=aud_data.get("default_tts_provider", "edge-tts"),
            speech_volume=float(aud_data.get("speech_volume", 1.0)),
            music_volume=float(aud_data.get("music_volume", 0.04)),
            ambient_volume=float(aud_data.get("ambient_volume", 0.10)),
            ducking_db=float(aud_data.get("ducking_db", -18.0)),
            default_bg_theme=aud_data.get("default_bg_theme", "default"),
        )

        # Auth
        auth_data = data.get("auth", {})
        auth = ChannelAuthConfig(
            cookies_path=REPO_ROOT / auth_data.get("cookies_path", f"secrets/cookies_{cid}.txt"),
            youtube_token_path=REPO_ROOT / auth_data.get("youtube_token_path", f"secrets/youtube_token_{cid}.json"),
            expected_youtube_channel_id=auth_data.get("expected_youtube_channel_id", ""),
            source_feed=auth_data.get("source_feed", ""),
        )

        return ChannelProfile(
            id=cid,
            enabled=enabled,
            editorial=editorial,
            visual=visual,
            audio=audio,
            auth=auth,
        )
