"""
src/branding.py - Channel Branding, SEO & Metadata Management Engine.
Handles channel identities, handle references, high-CTR Spanish title/description formats,
voice mappings, and tag generation for YouTube upload pipeline.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from src.core.domain import CanonicalChannel, CHANNEL_ALIASES, canonical_channel
from src.log import get_logger

logger = get_logger("branding")


def truncate_at_word_boundary(text: str, max_len: int, trailer: str = "...") -> str:
    """Truncate string to max_len strictly at word boundary without splitting words.

    Preserves Spanish question mark closing ('...?') if string opens with '¿'.
    """
    clean = (text or "").strip()
    if not clean or len(clean) <= max_len:
        return clean

    is_question = clean.startswith("¿")
    effective_trailer = "...?" if (is_question and not trailer.endswith("?")) else trailer
    budget = max(1, max_len - len(effective_trailer))

    sliced = clean[:budget]
    last_space = sliced.rfind(" ")
    if last_space > int(budget * 0.4):
        sliced = sliced[:last_space]

    sliced = sliced.rstrip(" ,;.:-_'\"¿?")
    return f"{sliced}{effective_trailer}"


@dataclass
class ChannelBranding:
    channel_key: str              # Canonical key: e.g. "moku" or "aelithia"
    display_name: str             # Public name: e.g. "Moku" or "Aelithia"
    handle: str                   # Channel handle: e.g. "@ChannelHandle"
    channel_url: str              # Full YouTube URL
    voice_name: str               # Edge-TTS / Azure Voice name
    default_title_fallback: str   # Default title fallback
    narration_style: str          # Prompt narration style guide
    intro_hook_template: str      # Spoken intro greeting
    outro_cta_template: str       # Spoken outro CTA
    tags: List[str]               # Spanish YouTube tags
    category_id: str = "24"       # YouTube Category ID (24 = Entertainment)
    primary_color: str = "#E50914"  # Default Crimson Red
    accent_color: str = "#FFD700"   # Default Gold
    watermark_text: str = ""
    watermark_position: Dict[str, Any] = field(default_factory=lambda: {"x": 20, "y": 40, "opacity": 0.65})

    def generate_title(self, raw_title: str) -> str:
        """
        Formats a raw translated title into a clean, engaging Spanish title.
        Ensures the final title never exceeds YouTube's 100-character limit, respects word boundaries,
        and contains no hardcoded channel or brand leaks.
        """
        clean_t = (raw_title or "").strip()
        if not clean_t or clean_t.lower() in ("untitled", "title", "título", "historia de terror", "relato de aelithia"):
            clean_t = self.default_title_fallback

        # Strip any legacy brand prefix if present
        if clean_t.startswith("[RELATO DE TERROR] "):
            clean_t = clean_t[len("[RELATO DE TERROR] "):].strip()

        # Strip any trailing channel brand suffixes if present
        for suffix_to_strip in (
            f" | Historias Reales en {self.display_name}",
            f" | {self.display_name}",
            " | Moku",
            " | Aelithia",
            " | Singularidad Sci-Fi",
        ):
            if clean_t.endswith(suffix_to_strip):
                clean_t = clean_t[:-len(suffix_to_strip)].strip()

        if len(clean_t) > 100:
            clean_t = truncate_at_word_boundary(clean_t, 100)

        return clean_t


    def generate_description(self, title: str, summary: Optional[str] = None) -> str:
        """
        Generates a structured, high-SEO Spanish description with CTAs,
        channel handle links, and targeted Spanish hashtags.
        """
        summary_text = (summary or f"Una impactante narración en español para la comunidad de {self.display_name}.").strip()
        clean_handle_tag = self.handle.lstrip("@").replace("-", "").replace("_", "")
        clean_name_tag = self.display_name.replace(" ", "").replace("-", "").replace("_", "")

        if self.channel_key == "aelithia":
            desc = (
                f"💭 {title} | Historias Reales y Confesiones en {self.display_name}\n\n"
                f"Bienvenidos a {self.display_name} ({self.handle}). Historias fascinantes, dilemas morales y experiencias reales narradas en español.\n\n"
                f"📌 RESUMEN DE LA HISTORIA:\n{summary_text}\n\n"
                f"🔔 ÚNETE A LA COMUNIDAD DE {self.display_name.upper()}:\n"
                f"Suscríbete para disfrutar de más relatos y dramas de la vida real:\n"
                f"👉 {self.channel_url}\n"
                f"¡Haz clic en la campanita 🔔 y comparte tu punto de vista!\n\n"
                f"💬 ¿TÚ QUÉ OPINAS?:\n"
                f"¿Crees que actuó de la manera correcta? Cuéntanos en los comentarios.\n\n"
                f"#{clean_name_tag} #HistoriasReales #DramasDeLaVidaReal #Confesiones #HistoriasEnEspañol"
                + (f" #{clean_handle_tag}" if clean_handle_tag and clean_handle_tag.lower() != clean_name_tag.lower() else "")
            )
        elif self.channel_key == "moku":
            desc = (
                f"😱 {title} | Relato de Terror y Suspenso en Español\n\n"
                f"Bienvenidos a {self.display_name} ({self.handle}). Una experiencia inmersiva para escuchar en la oscuridad.\n\n"
                f"📌 SOBRE ESTE RELATO:\n{summary_text}\n\n"
                f"🔔 SUSCRÍBETE Y APOYA EL CANAL:\n"
                f"Si te apasionan las historias de terror, los relatos perturbadores y el suspenso, suscríbete a nuestro canal:\n"
                f"👉 {self.channel_url}\n"
                f"¡Activa la campanita 🔔 para no perderte ningún nuevo relato!\n\n"
                f"💬 COMUNIDAD:\n"
                f"¿Has vivido alguna experiencia paranormal similar? Déjanos tu historia en los comentarios.\n\n"
                f"#HistoriasDeTerror #CreepypastaEnEspañol #RelatosDeTerror #Paranormal #Suspenso"
            )
        else:
            tag_block = " ".join(f"#{t.replace(' ', '')}" for t in self.tags[:5]) if self.tags else f"#{clean_name_tag}"
            desc = (
                f"🎬 {title} | {self.display_name}\n\n"
                f"Bienvenidos a {self.display_name} ({self.handle}).\n\n"
                f"📌 RESUMEN:\n{summary_text}\n\n"
                f"🔔 SUSCRÍBETE:\n"
                f"👉 {self.channel_url}\n"
                f"¡Activa la campanita 🔔 y comparte tu opinión!\n\n"
                f"{tag_block}"
            )
        return desc


    def generate_shorts_metadata(self, raw_title: str, summary: Optional[str] = None) -> Dict[str, Any]:
        """
        Generates Shorts-optimized title (<60 chars), description with mandatory hashtags (#Shorts), and tags list.
        """
        clean_t = (raw_title or "").strip()
        if not clean_t:
            clean_t = self.default_title_fallback

        # High-CTR punchy title under 60 chars strictly at word boundaries
        if len(clean_t) > 55:
            short_title = truncate_at_word_boundary(clean_t, 55)
        else:
            short_title = clean_t

        clean_name_tag = self.display_name.replace(" ", "").replace("-", "").replace("_", "")
        if self.channel_key == "aelithia":
            hashtag_block = f"#Shorts #HistoriasReales #{clean_name_tag} #DilemasMorales"
            full_title = f"{short_title} #Shorts"
        elif self.channel_key == "moku":
            hashtag_block = f"#Shorts #Horror #HistoriasDeTerror #{clean_name_tag}"
            full_title = f"{short_title} #Shorts"
        else:
            hashtag_block = f"#Shorts #{clean_name_tag}"
            full_title = f"{short_title} #Shorts"

        if len(full_title) > 100:
            full_title = truncate_at_word_boundary(full_title, 100)

        summary_text = (summary or f"Relato corto en {self.display_name}").strip()
        description = (
            f"🎬 {short_title}\n\n"
            f"{summary_text}\n\n"
            f"Suscríbete a {self.handle}: {self.channel_url}\n\n"
            f"{hashtag_block}"
        )
        shorts_tags = list(self.tags) + ["Shorts", "YouTubeShorts", "ShortsVideo"]

        return {
            "title": full_title,
            "description": description,
            "tags": shorts_tags,
            "category_id": self.category_id,
            "channel": self.channel_key,
        }


_CHANNEL_ALIASES: Dict[str, str] = {
    alias: target.value for alias, target in CHANNEL_ALIASES.items()
}


def resolve_channel_key(channel: Optional[str]) -> str:
    """Normalize a compatibility input alias without guessing unknown values."""
    res = canonical_channel(channel or "")
    return res.value if hasattr(res, "value") else str(res)


def get_channel_branding(channel: str) -> ChannelBranding:
    """Return branding dynamically populated from ChannelProfileRegistry."""
    from src.core.channel_profile import ChannelProfileRegistry
    prof = ChannelProfileRegistry.get_channel(channel)
    cid = prof.id
    ed = prof.editorial
    vis = prof.visual
    aud = prof.audio

    intro_hook = (
        "Todo comenzó cuando descubrí el secreto que mi propia familia intentaba ocultarme..."
        if cid == "aelithia"
        else "Una presencia inexplicable comienza a manifestarse..."
    )

    return ChannelBranding(
        channel_key=cid,
        display_name=ed.public_name,
        handle=ed.handle,
        channel_url=ed.channel_url,
        voice_name=aud.default_voice_profile,
        default_title_fallback=ed.default_title_fallback,
        narration_style=ed.tone,
        intro_hook_template=intro_hook,
        outro_cta_template="",
        tags=list(ed.tags),
        category_id=ed.category_id,
        primary_color=vis.palette.primary,
        accent_color=vis.palette.accent,
        watermark_text=vis.watermark_text or ed.handle,
        watermark_position={"x": 20, "y": 40, "opacity": 0.65},
    )


class _LazyChannelBrandingRegistry(dict):
    """Dynamic registry backed by ChannelProfileRegistry without hardcoded identities."""
    def __getitem__(self, key: Any) -> ChannelBranding:
        cid = key.value if hasattr(key, "value") else str(key)
        return get_channel_branding(cid)

    def __contains__(self, key: object) -> bool:
        try:
            cid = key.value if hasattr(key, "value") else str(key)
            get_channel_branding(cid)
            return True
        except Exception:
            return False

    def get(self, key: Any, default: Any = None) -> Any:
        try:
            cid = key.value if hasattr(key, "value") else str(key)
            return get_channel_branding(cid)
        except Exception:
            return default

    def items(self):
        from src.core.channel_profile import ChannelProfileRegistry
        return [(cid, get_channel_branding(cid)) for cid in ChannelProfileRegistry.list_active_channel_ids()]

    def values(self):
        from src.core.channel_profile import ChannelProfileRegistry
        return [get_channel_branding(cid) for cid in ChannelProfileRegistry.list_active_channel_ids()]

    def keys(self):
        from src.core.channel_profile import ChannelProfileRegistry
        return ChannelProfileRegistry.list_active_channel_ids()


_CHANNEL_BRANDING_REGISTRY: Dict[str, ChannelBranding] = _LazyChannelBrandingRegistry()
