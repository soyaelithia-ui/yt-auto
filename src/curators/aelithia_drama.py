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
        Builds a high-retention 35-45s Short narrative for Aelithia (Drama / AITA / Moral Dilemmas).
        Calibrated strictly to 120-180 words for optimal short pacing.
        Starts with a 0-3s direct hook framing the personal conflict.
        """
        actual_channel = kwargs.get("ch") or self.channel
        branding = get_channel_branding(actual_channel)
        ch_handle = branding.handle

        hook = f"¿Soy yo el malo por poner límites definitivos a mi propia familia para proteger mi patrimonio en torno a {topic}?"
        body = (
            "Tras diez años de trabajar turnos dobles y construir mis ahorros con estricta disciplina, mi familia organizó una cena sorpresa para exigirme que cediera una parte sustancial de mi dinero y saldara las deudas irresponsables de mi hermano. "
            "Cuando me negué con total serenidad diciendo que no estaba dispuesto a financiar malas decisiones ajenas, me acusaron de ser una persona fría y egoísta, amenazando con expulsarme de las próximas reuniones familiares. "
            "Incluso intentaron manipular a mis parientes lejanos para presionarme mediante llamadas insistentes a deshoras y mensajes de culpa."
        )
        outro = f"El dilema ético y las reflexiones sobre límites patrimoniales continúan en el canal de {ch_handle}."
        return f"{hook}\n\n{body}\n\n{outro}"

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
