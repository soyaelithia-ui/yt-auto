"""
Moku Horror / SCP Narrative Curator Strategy.
"""

from __future__ import annotations
from typing import Any, List, Optional
from src.curators.base import INarrativeCurator
from src.branding import get_channel_branding
from src.core.scp_lore import lookup_scp


class MokuHorrorCurator(INarrativeCurator):
    """Curator strategy specialized in SCP containment lore, psychological horror, and creepypasta."""

    @property
    def channel(self) -> str:
        return "moku"

    def build_short_narrative(self, topic: str, **kwargs: Any) -> str:
        """
        Builds a high-retention 40-55s Short narrative for Moku (Horror/SCP).
        Calibrated strictly to 120-180 words for optimal 45s pacing.
        Grounded in official canonical lore when an SCP is detected.
        Starts with a 0-3s direct hook without conversational greetings.
        """
        actual_channel = kwargs.get("ch") or self.channel
        branding = get_channel_branding(actual_channel)
        ch_handle = branding.handle

        scp_entry = lookup_scp(topic)
        if scp_entry:
            scp_id = scp_entry.get("scp_id", "")
            facts = scp_entry.get("key_facts", [])

            if "087" in scp_id:
                hook = f"Bajo una universidad ordinaria existe una escalera sin fin que devora la luz en {topic}."
                body = (
                    "Las linternas solo alcanzan a iluminar un tramo y medio antes de que la oscuridad absoluta devore cualquier haz luminoso. "
                    "A cientos de metros de profundidad se escuchan constantemente los sollozos desgarradores de un niño en agonía, pero por más que desciendas peldaño a peldaño, la distancia acústica jamás se reduce. "
                    "En la última expedición oficial, las cámaras térmicas registraron a SCP-087-1: un rostro humanoide pálido y flotante, sin boca ni pupilas visibles, observando fijamente desde la penumbra. "
                    "Tras aquel aterrador encuentro, los agentes sellaron la entrada principal con setenta y cinco centímetros de hormigón armado para siempre."
                )
            elif "173" in scp_id:
                hook = f"Nunca parpadees ni apartes la vista de esta escultura de concreto si valoras tu vida en {topic}."
                body = (
                    "Clasificado como Euclid por la Fundación, SCP-173 permanece completamente inmóvil mientras se mantenga bajo contacto visual directo e ininterrumpido. "
                    "En la milésima de segundo en que cierras los ojos, se desplaza a velocidades imposibles y fractura las vértebras del cuello de sus observadores en una fracción de segundo. "
                    "Para ingresar a limpiar su celda de contención se requieren tres personas: dos manteniendo la mirada fija y una advirtiendo obligatoriamente en voz alta antes de parpadear para evitar una tragedia inevitable."
                )
            elif "049" in scp_id:
                hook = f"Bajo una máscara de cerámica fusionada a su piel, este doctor medieval oculta una cura aterradora en {topic}."
                body = (
                    "SCP-049 afirma que la humanidad entera sufre una enfermedad terminal desconocida que él denomina la pestilencia. "
                    "Su toque biológico directo detiene las funciones del corazón al instante, para luego reanimar los cuerpos inertes mediante cirugías toscas transformándolos en marionetas obedientes sin voluntad propia ni memoria humana. "
                    "Cualquier intento de diálogo con esta entidad debe realizarse detrás de mamparas de seguridad reforzadas y bajo estricta vigilancia armada permanente."
                )
            elif "096" in scp_id:
                hook = f"Si alguna vez miras accidentalmente el rostro de esta criatura, absolutamente nada en este mundo podrá salvarte en {topic}."
                body = (
                    "Conocido como el Chico Tímido, SCP-096 entra en un estado de furia ciega e incontrolable en el preciso instante en que alguien observa sus rasgos faciales, ya sea en persona, en una fotografía antigua o en una grabación de video digital. "
                    "En ese momento, la entidad emite alaridos desgarradores y comienza una persecución implacable hacia la posición del observador a través de continentes enteros. "
                    "No importa dónde intentes esconderte ni qué blindaje de acero te proteja: derribará instalaciones subterráneas enteras a velocidades sobrehumanas hasta eliminar a su objetivo sin dejar escapatoria posible."
                )
            else:
                hook = f"El archivo clasificado de {scp_id} describe una de las anomalías más peligrosas de la Fundación en {topic}."
                f_text = " ".join(facts[:3]) if facts else "Contiene manifestaciones imposibles que desafían toda explicación científica conocida en el mundo actual."
                body = f_text + " Los protocolos de seguridad prohíben cualquier aproximación sin autorización formal previa de los mandos superiores bajo pena de aislamiento definitivo inmediato."

            outro = f"El expediente completo y las grabaciones clasificadas permanecen archivados bajo estricta custodia en {ch_handle}."
            return f"{hook}\n\n{body}\n\n{outro}"

        # General Creepypasta / Horror Short
        hook = f"A las tres de la madrugada, las alertas de seguridad registraron una anomalía imposible en los sensores en torno a {topic}."
        body = (
            "Las cámaras térmicas captaron una silueta tridimensional desplazándose en contra de las fuentes de luz artificial en el perímetro exterior de la zona restringida. "
            "Los sensores perimetrales se descalibraron mientras una modulación en los altavoces de la cabina comenzaba a repetir los nombres de los operadores de guardia en tiempo real. "
            "Al ingresar a inspeccionar, las puertas blindadas estaban intactas pero las grabaciones magnéticas habían sido borradas por completo, dejando un rastro helado sobre el piso de la instalación abandonada y una advertencia siniestra."
        )
        outro = f"El testimonio completo y los registros térmicos de la patrulla permanecen bajo custodia oficial en {ch_handle}."
        return f"{hook}\n\n{body}\n\n{outro}"

    def build_longform_narrative(
        self, topic: str, target_words: int = 1800, **kwargs: Any
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
