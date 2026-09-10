"""
Aelithia Drama & Interpersonal Dilemmas Narrative Curator Strategy.
"""

from __future__ import annotations
from typing import Any, List, Optional
from src.curators.base import INarrativeCurator
from src.branding import get_channel_branding


class AelithiaDramaCurator(INarrativeCurator):
    """Curator strategy specialized in relationship advice, family inheritance, and AITA dilemmas."""

    @property
    def channel(self) -> str:
        return "aelithia"

    def build_short_narrative(self, topic: str, **kwargs: Any) -> str:
        """
        Builds a high-retention Short narrative for Aelithia (Drama / AITA / Moral Dilemmas).
        Calibrated strictly to 180-320 words (>= 180 words) for optimal 65-115s pacing @ 165 WPM.
        Starts with a 0-3s direct hook framing the moral dilemma with first-person confrontation.
        """
        from src.templates.narratives import build_aelithia_short_narrative
        return build_aelithia_short_narrative(topic, channel=self.channel, **kwargs)

    def build_longform_narrative(
        self, topic: str, target_words: int = 2600, **kwargs: Any
    ) -> str:
        from src.templates.narratives import build_aelithia_longform_narrative
        return build_aelithia_longform_narrative(topic, channel=self.channel, **kwargs)

    def get_organic_connectors(self) -> List[str]:
        return [
            "Con el paso de los días y tras consultar con un asesor legal,",
            "Durante la siguiente conversación telefónica con mis padres,",
            "Para mi total sorpresa en la siguiente reunión familiar,",
            "Al reflexionar sobre el impacto emocional de esta decisión,",
            "Frente a las constantes recriminaciones del círculo cercano,",
        ]
