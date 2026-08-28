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


@dataclass
class ChannelBranding:
    channel_key: str              # Canonical key: "moku" or "aelithia"
    display_name: str             # Public name: "Moku" or "Aelithia"
    handle: str                   # Channel handle: "@MokuRedit" or "@Aelithia-c1f"
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
    watermark_text: str = "@MokuRedit"
    watermark_position: Dict[str, Any] = field(default_factory=lambda: {"x": 20, "y": 40, "opacity": 0.65})

    def generate_title(self, raw_title: str) -> str:
        """
        Formats a raw translated title into a high-CTR Spanish title format.
        Ensures the final title never exceeds YouTube's 100-character limit.
        """
        clean_t = (raw_title or "").strip()
        if not clean_t or clean_t.lower() in ("untitled", "title", "título", "historia de terror", "relato de aelithia"):
            clean_t = self.default_title_fallback

        if self.channel_key == "aelithia":
            suffix = " | Historias Reales en Aelithia" if (not clean_t.startswith("¿") and not clean_t.startswith("[")) else " | Aelithia"
            full = f"{clean_t}{suffix}"
            if len(full) > 100:
                max_clean_len = max(1, 100 - len(suffix) - 3)
                clean_t = clean_t[:max_clean_len].strip() + "..."
                full = f"{clean_t}{suffix}"
            return full
        else:
            prefix = "[RELATO DE TERROR] " if not clean_t.startswith("[") else ""
            suffix = " | Moku"
            full = f"{prefix}{clean_t}{suffix}"
            if len(full) > 100:
                max_clean_len = max(1, 100 - len(prefix) - len(suffix) - 3)
                clean_t = clean_t[:max_clean_len].strip() + "..."
                full = f"{prefix}{clean_t}{suffix}"
            return full


    def generate_description(self, title: str, summary: Optional[str] = None) -> str:
        """
        Generates a structured, high-SEO Spanish description with CTAs,
        channel handle links, and targeted Spanish hashtags.
        """
        summary_text = (summary or f"Una impactante narración en español para la comunidad de {self.display_name}.").strip()

        if self.channel_key == "aelithia":
            desc = (
                f"💭 {title} | Historias Reales y Confesiones en Aelithia\n\n"
                f"Bienvenidos a {self.display_name} ({self.handle}). Historias fascinantes, dilemas morales y experiencias reales narradas en español.\n\n"
                f"📌 RESUMEN DE LA HISTORIA:\n{summary_text}\n\n"
                f"🔔 ÚNETE A LA COMUNIDAD DE AELITHIA:\n"
                f"Suscríbete para disfrutar de más relatos y dramas de la vida real:\n"
                f"👉 {self.channel_url}\n"
                f"¡Haz clic en la campanita 🔔 y comparte tu punto de vista!\n\n"
                f"💬 ¿TÚ QUÉ OPINAS?:\n"
                f"¿Crees que actuó de la manera correcta? Cuéntanos en los comentarios.\n\n"
                f"#Aelithia #HistoriasReales #DramasDeLaVidaReal #Confesiones #HistoriasEnEspañol #AelithiaC1f"
            )
        else:
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
                f"#HistoriasDeTerror #CreepypastaEnEspañol #RelatosDeTerror #Paranormal #Suspenso #MokuRedit"
            )
        return desc


    def generate_shorts_metadata(self, raw_title: str, summary: Optional[str] = None) -> Dict[str, Any]:
        """
        Generates Shorts-optimized title (<60 chars), description with mandatory hashtags (#Shorts), and tags list.
        """
        clean_t = (raw_title or "").strip()
        if not clean_t:
            clean_t = self.default_title_fallback

        # High-CTR punchy title under 60 chars
        if len(clean_t) > 55:
            words = clean_t.split()
            short_t = ""
            for w in words:
                if len((short_t + " " + w).strip()) <= 52:
                    short_t = (short_t + " " + w).strip()
                else:
                    break
            short_title = f"{short_t}..." if short_t else clean_t[:52] + "..."
        else:
            short_title = clean_t

        if self.channel_key == "aelithia":
            hashtag_block = "#Shorts #HistoriasReales #Aelithia #DilemasMorales"
            full_title = f"{short_title} #Shorts"
        else:
            hashtag_block = "#Shorts #Horror #HistoriasDeTerror #Moku"
            full_title = f"{short_title} #Shorts"

        if len(full_title) > 100:
            full_title = full_title[:97] + "..."

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


_CHANNEL_BRANDING_REGISTRY: Dict[str, ChannelBranding] = {
    "moku": ChannelBranding(
        channel_key="moku",
        display_name="Moku",
        handle="@MokuRedit",
        channel_url="https://www.youtube.com/@MokuRedit",
        voice_name="es-MX-JorgeNeural",
        default_title_fallback="Historia de Terror",
        narration_style="oscura, inmersiva, de suspenso perturbador y terror psicológico",
        intro_hook_template="En la oscuridad más profunda, una presencia inexplicable comienza a manifestarse...",
        outro_cta_template="",
        tags=[
            "historias de terror",
            "creepypasta en español",
            "relatos de terror",
            "historias de suspenso",
            "paranormal",
            "relatos de la noche",
            "terror psicológico",
            "historias de miedo",
            "leyendas urbanas",
            "MokuRedit"
        ],
        primary_color="#E50914",
        accent_color="#FFD700",
        watermark_text="@MokuRedit",
        watermark_position={"x": 20, "y": 40, "opacity": 0.65}
    ),
    "aelithia": ChannelBranding(
        channel_key="aelithia",
        display_name="Aelithia",
        handle="@Aelithia-c1f",
        channel_url="https://www.youtube.com/@Aelithia-c1f",
        voice_name="es-MX-DaliaNeural",
        default_title_fallback="Relato de Aelithia",
        narration_style="emotiva, expresiva, envolvente para dramas interpersonales y reflexiones reales",
        intro_hook_template="Todo comenzó cuando descubrí el secreto que mi propia familia intentaba ocultarme...",
        outro_cta_template="",
        tags=[
            "aelithia",
            "historias reales",
            "dramas de la vida real",
            "confesiones",
            "historias de la vida real",
            "dilemas morales",
            "historias en español",
            "relatos impactantes",
            "Aelithia-c1f"
        ],
        primary_color="#00E5FF",
        accent_color="#FF007F",
        watermark_text="@Aelithia-c1f",
        watermark_position={"x": 20, "y": 40, "opacity": 0.65}
    )
}

_CHANNEL_ALIASES: Dict[str, str] = {
    alias: target.value for alias, target in CHANNEL_ALIASES.items()
}


def resolve_channel_key(channel: Optional[str]) -> str:
    """Normalize a compatibility input alias without guessing unknown values."""
    return canonical_channel(channel or "").value


def get_channel_branding(channel: str) -> ChannelBranding:
    """Return branding dynamically populated from ChannelProfileRegistry."""
    from src.core.channel_profile import ChannelProfileRegistry
    prof = ChannelProfileRegistry.get_channel(channel)
    cid = prof.id
    ed = prof.editorial
    vis = prof.visual
    aud = prof.audio

    return ChannelBranding(
        channel_key=cid,
        display_name=ed.public_name,
        handle=ed.handle,
        channel_url=ed.channel_url,
        voice_name=aud.default_voice_profile,
        default_title_fallback=ed.default_title_fallback,
        narration_style=ed.tone,
        intro_hook_template="Una presencia inexplicable comienza a manifestarse...",
        outro_cta_template="",
        tags=list(ed.tags),
        category_id=ed.category_id,
        primary_color=vis.palette.primary,
        accent_color=vis.palette.accent,
        watermark_text=vis.watermark_text or ed.handle,
        watermark_position={"x": 20, "y": 40, "opacity": 0.65},
    )
