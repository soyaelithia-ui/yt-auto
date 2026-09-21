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
CONFIG_CHANNELS_JSON = REPO_ROOT / "config" / "channels.json"


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
    aliases: Tuple[str, ...] = ()


class ChannelProfileRegistry:
    """
    Thread-safe registry for declarative channel profiles.
    Loads and caches JSON configurations from config/channels/ and config/channels.json.
    """
    _cache: Dict[str, ChannelProfile] = {}
    _cache_mtimes: Dict[str, int] = {}
    _alias_to_id: Dict[str, str] = {
        "moku": "horror",
        "terror": "horror",
        "scp": "horror",
        "moku_horror": "horror",
        "moku_terror": "horror",
        "horror": "horror",
        "drama": "drama",
        "aelithia": "drama",
        "aita": "drama",
        "aelithia_drama": "drama",
        "soy_el_malo": "drama",
        "channel1": "horror",
        "channel_1": "horror",
        "channel-1": "horror",
        "canal1": "horror",
        "canal_1": "horror",
        "canal-1": "horror",
        "canal 1": "horror",
        "channel2": "drama",
        "channel_2": "drama",
        "channel-2": "drama",
        "canal2": "drama",
        "canal_2": "drama",
        "canal-2": "drama",
        "canal 2": "drama",
        "scifi": "scifi",
        "singularidad": "scifi",
    }

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
        prefixes = [cid.upper()] + [a.upper() for a in profile.aliases]
        active_channel_env = os.environ.get("CHANNEL_KEY", "").strip().lower()
        active_cid = cls.normalize_channel_id(active_channel_env) if active_channel_env else ""
        use_generic_env = (active_cid == cid or not active_channel_env)

        def _get_env(suffix: str, generic_var: Optional[str] = None) -> Optional[str]:
            if generic_var and use_generic_env and generic_var in os.environ:
                return os.environ[generic_var]
            for pfx in prefixes:
                var_name = f"{pfx}_{suffix}"
                if var_name in os.environ:
                    return os.environ[var_name]
            return None

        handle = _get_env("HANDLE", "CHANNEL_HANDLE") or profile.editorial.handle
        channel_url = _get_env("CHANNEL_URL", "CHANNEL_URL") or profile.editorial.channel_url
        public_name = (
            _get_env("NAME", "CHANNEL_NAME")
            or _get_env("PUBLIC_NAME")
            or profile.editorial.public_name
        )
        watermark_text = _get_env("WATERMARK", "CHANNEL_WATERMARK") or profile.visual.watermark_text
        voice = _get_env("TTS_VOICE", "CHANNEL_TTS_VOICE") or profile.audio.default_voice_profile
        tts_provider = _get_env("TTS_PROVIDER", "CHANNEL_TTS_PROVIDER") or profile.audio.default_tts_provider

        cookies_override = _get_env("COOKIES_PATH", "CHANNEL_COOKIES_PATH")
        cookies_path = (
            Path(cookies_override).expanduser().resolve()
            if cookies_override
            else profile.auth.cookies_path
        )

        token_override = _get_env("YOUTUBE_TOKEN_PATH", "CHANNEL_YOUTUBE_TOKEN_PATH")
        youtube_token_path = (
            Path(token_override).expanduser().resolve()
            if token_override
            else profile.auth.youtube_token_path
        )

        expected_channel_id = (
            _get_env("YOUTUBE_CHANNEL_ID", "CHANNEL_YOUTUBE_CHANNEL_ID")
            or profile.auth.expected_youtube_channel_id
        ).strip()
        source_feed = _get_env("SOURCE_FEED", "CHANNEL_SOURCE_FEED") or profile.auth.source_feed

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
            title_suffix=profile.editorial.title_suffix,
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
        cls._ensure_loaded()
        if hasattr(raw, "value"):
            s = str(raw.value).strip().lower()
        else:
            s = (str(raw or "")).strip().lower()
        if not s:
            return s
        if s in cls._cache:
            return s
        if s in cls._alias_to_id:
            return cls._alias_to_id[s]
        prefix = s.split("-")[0]
        if prefix in cls._cache:
            return prefix
        if prefix in cls._alias_to_id:
            return cls._alias_to_id[prefix]
        return s

    @classmethod
    def _ensure_loaded(cls, force_reload: bool = False) -> None:
        has_channels_json = False
        if CONFIG_CHANNELS_JSON.is_file():
            has_channels_json = True
            try:
                mtime_cj = CONFIG_CHANNELS_JSON.stat().st_mtime_ns
                if force_reload or cls._cache_mtimes.get("__channels_json__") != mtime_cj:
                    with open(CONFIG_CHANNELS_JSON, "r", encoding="utf-8") as f:
                        cj_data = json.load(f)
                    channels_list = cj_data.get("channels", []) if isinstance(cj_data, dict) else cj_data
                    if isinstance(channels_list, list):
                        for entry in channels_list:
                            if isinstance(entry, dict) and "config_file" in entry:
                                p_path = REPO_ROOT / entry["config_file"]
                                if p_path.is_file():
                                    with open(p_path, "r", encoding="utf-8") as pf:
                                        p_data = json.load(pf)
                                    prof = cls._parse_profile_dict(p_data, p_path)
                                    cls._cache[prof.id] = prof
                                    for al in (entry.get("aliases") or ()):
                                        cls._alias_to_id[str(al).lower()] = prof.id
                                    for al in prof.aliases:
                                        cls._alias_to_id[al] = prof.id
                        has_channels_json = bool(cls._cache)
                    cls._cache_mtimes["__channels_json__"] = mtime_cj
            except Exception as e:
                logger.warning("Failed to load config/channels.json: %s", e)

        if has_channels_json:
            return

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
                for al in profile.aliases:
                    cls._alias_to_id[al] = profile.id
            except Exception as e:
                logger.warning("Failed to load channel profile from %s: %s", jf, e)

    @classmethod
    def _parse_profile_dict(cls, data: Dict[str, Any], file_path: Path) -> ChannelProfile:
        cid = str(data.get("id", file_path.stem)).lower()
        enabled = bool(data.get("enabled", True))
        aliases = tuple(str(a).lower() for a in data.get("aliases", ()))

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
            title_suffix=ed_data.get("title_suffix", ""),
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
            aliases=aliases,
        )
