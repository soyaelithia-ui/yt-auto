"""
Drama & Interpersonal Dilemmas Narrative Curator Strategy.
"""

from __future__ import annotations

from typing import Any, List
from src.curators.base import INarrativeCurator


class DramaCurator(INarrativeCurator):
    """Curator strategy specialized in relationship advice, family inheritance, and AITA dilemmas."""

    def __init__(self, channel: str = "drama") -> None:
        self._channel = channel

    @property
    def channel(self) -> str:
        return self._channel

    def build_short_narrative(self, topic: str, **kwargs: Any) -> str:
        """
        Builds a high-retention Short narrative for Drama / AITA / Moral Dilemmas.
        Calibrated strictly to 180-320 words for optimal 65-115s pacing @ 165 WPM.
        """
        from src.templates.narratives import build_channel_narrative
        return build_channel_narrative(topic, channel=self.channel, video_mode="short", **kwargs)

    def build_longform_narrative(
        self, topic: str, target_words: int = 2600, **kwargs: Any
    ) -> str:
        from src.templates.narratives import build_channel_narrative
        return build_channel_narrative(topic, channel=self.channel, video_mode="longform", target_words=target_words, **kwargs)

    def get_organic_connectors(self) -> List[str]:
        return [
            "Con el paso de los días y tras consultar con un asesor legal,",
            "Durante la siguiente conversación telefónica con mis padres,",
            "Para mi total sorpresa en la siguiente reunión familiar,",
            "Al reflexionar sobre el impacto emocional de esta decisión,",
            "Frente a las constantes recriminaciones del círculo cercano,",
        ]


# Backward-compatibility alias
AelithiaDramaCurator = DramaCurator
