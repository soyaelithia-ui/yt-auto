"""
src/curators/moku_horror.py - Moku Horror / SCP High-Retention Narrative Curator Strategy.
"""

from __future__ import annotations
import re
from typing import Any, List, Optional
from src.curators.base import INarrativeCurator
from src.core.scp_lore import lookup_scp


class MokuHorrorCurator(INarrativeCurator):
    """Curator strategy specialized in SCP containment lore, psychological horror, and creepypasta."""

    @property
    def channel(self) -> str:
        return "moku"

    def build_short_narrative(self, topic: str, **kwargs: Any) -> str:
        """
        Builds a high-retention Short narrative for Moku (Horror/SCP).
        Calibrated strictly to 180-320 words (>= 180 words) for optimal 65-115s pacing @ 165 WPM.
        Grounded dynamically in official canonical SCP lore or rich procedural dread generation.
        """
        from src.templates.narratives import build_moku_short_narrative
        return build_moku_short_narrative(topic, channel=self.channel, **kwargs)

    def build_longform_narrative(
        self, topic: str, target_words: int = 2600, **kwargs: Any
    ) -> str:
        from src.templates.narratives import build_moku_longform_narrative
        return build_moku_longform_narrative(topic, channel=self.channel, **kwargs)

    def get_organic_connectors(self) -> List[str]:
        return [
            "Conforme avanzaba la noche en la estación solitaria,",
            "Al revisar los registros electromagnéticos de la guardia anterior,",
            "Una variación súbita en la presión atmosférica del perímetro reveló que",
            "Entre la estática intermitente de los receptores analógicos,",
            "Sin previo aviso ni señal de alerta en los sensores térmicos,",
        ]
