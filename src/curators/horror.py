"""
Horror / SCP High-Retention Narrative Curator Strategy.
"""

from __future__ import annotations

from typing import Any, List
from src.curators.base import INarrativeCurator


class HorrorCurator(INarrativeCurator):
    """Curator strategy specialized in SCP containment lore, psychological horror, and creepypasta."""

    def __init__(self, channel: str = "horror") -> None:
        self._channel = channel

    @property
    def channel(self) -> str:
        return self._channel

    def build_short_narrative(self, topic: str, **kwargs: Any) -> str:
        """
        Builds a high-retention Short narrative for Horror/SCP.
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
            "Conforme avanzaba la noche en la estación solitaria,",
            "Al revisar los registros electromagnéticos de la guardia anterior,",
            "Una variación súbita en la presión atmosférica del perímetro reveló que",
            "Entre la estática intermitente de los receptores analógicos,",
            "Sin previo aviso ni señal de alerta en los sensores térmicos,",
        ]


# Backward-compatibility alias
MokuHorrorCurator = HorrorCurator
