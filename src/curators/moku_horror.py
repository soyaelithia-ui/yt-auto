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
        Builds a high-retention 40-55s Short narrative for Moku (Horror/SCP).
        Calibrated strictly to 115-145 words for optimal 45-50s pacing @ 165 WPM.
        Grounded in LaloBeRoth & JOMOSU retention blueprints (0-2s hooks, micro-twists, no CTA).
        Enforces a seamless syntactic loop connector.
        """
        top_lower = topic.lower().strip()
        scp_entry = lookup_scp(topic)
        scp_id = scp_entry.get("scp_id", "") if scp_entry else ""

        # 1. SCP-027: El Dios de las Alimañas (Body horror visceral / JOMOSU style)
        if "027" in top_lower or "027" in scp_id or "alimañas" in top_lower or "vermin" in top_lower:
            return (
                "Si sientes un cosquilleo inexplicable bajo tu piel, aléjate de esta celda de inmediato. "
                "En el Sitio-19 de la Fundación, el anfitrión de SCP-027 no puede cerrar los ojos sin que miles de cucarachas, arañas venenosas y roedores broten espontáneamente a su alrededor en la oscuridad. "
                "Tres toneladas de vacío continuo incineran a las criaturas día y noche, pero las biopsias del personal médico revelaron lo peor: el enjambre no ataca al sujeto, sino que lo obedece como a una deidad viviente. "
                "Y si su corazón se detiene por un infarto o eutanasia profiláctica, la plaga saltará en un microsegundo al humano vivo más cercano en la habitación... "
                "por eso, la próxima vez que sientas algo caminar sobre tu cuello en la penumbra..."
            )

        # 2. SCP-001: El Dios Roto (Mekhane / Apocalipsis industrial / JOMOSU style)
        if "001" in top_lower or "001" in scp_id or "dios roto" in top_lower or "mekhane" in top_lower:
            return (
                "Este archivo clasificado provocó la destrucción de una costa entera y el nacimiento de un nuevo océano en el planeta. "
                "En 1942, fanáticos de la Iglesia del Dios Roto ensamblaron un coloso biomecánico en Baja California creyendo que resucitaban a su deidad Mekhane para salvar a la humanidad. "
                "Pero cometieron un error fatal: el corazón instalado provenía de la infame Fábrica, desatando un titán insaciable devorador de metales que asimiló ciudades enteras y casi aniquila por completo el continente. "
                "La Fundación tuvo que activar el rayo orbital del satélite 2399 para pulverizar la abominación en una explosión atómica colosal... "
                "y la razón por la que el mar sigue temblando hoy en día..."
            )

        # 3. Incident 096-1-A & SCP-096 (El Chico Tímido / Inevitabilidad / LaloBeRoth style)
        if "096" in top_lower or "096" in scp_id or "tímido" in top_lower or "shy guy" in top_lower:
            return (
                "Cuatro míseros píxeles en una fotografía antigua. Eso fue todo lo que necesitó esta criatura para aniquilar un batallón blindado entero a miles de kilómetros de distancia. "
                "Conocido como el Chico Tímido, SCP-096 entra en un estado de furia ciega incontrolable si alguien observa sus rasgos faciales, incluso en una grabación digital borrosa o el tenue reflejo de un cristal. "
                "En ese milisegundo, absolutamente nada en la Tierra puede detener su carrera: derriba búnkeres subterráneos de titanio a velocidades supersónicas hasta no dejar ningún rastro del observador con vida. "
                "Nadie sobrevive tras ver su cara en este mundo... "
                "y la prueba irrefutable de que no puedes escapar de su mirada..."
            )

        # 4. SCP-1048: The Builder Bear (El Oso Constructor / LaloBeRoth style)
        if "1048" in top_lower or "1048" in scp_id or "oso" in top_lower or "builder bear" in top_lower:
            return (
                "Imaginen un tierno oso de peluche que se pasea libre por la base haciéndose amigo de todos los guardias... hasta que descubren de qué construye sus réplicas. "
                "Clasificado inicialmente como Seguro, SCP-1048 comenzó a recolectar materiales biológicos en secreto por los pasillos subterráneos de la instalación. "
                "Una noche encontraron a su primera creación en la cafetería: un oso idéntico hecho enteramente con orejas humanas vivas que emitía chillidos ultrasónicos mortales capaces de reventar los órganos internos del personal de guardia al instante. "
                "El equipo de contención fue masacrado y el oso original sigue escondido en los conductos de ventilación... "
                "por eso, si alguna vez encuentras un juguete abandonado en la oscuridad..."
            )

        # 5. SCP-049: El Doctor de la Plaga (Locura quirúrgica)
        if "049" in top_lower or "049" in scp_id or "plaga" in top_lower or "peste" in top_lower:
            return (
                "Bajo una máscara de cerámica medieval fusionada directamente a su piel, este doctor oculta la cura más aterradora de toda la historia humana. "
                "SCP-049 insiste en que todos nosotros padecemos una enfermedad terminal desconocida llamada la Pestilencia. "
                "Su contacto biológico directo detiene las funciones del corazón al instante sin causar dolor, para luego reanimar los cadáveres mediante toscas cirugías quirúrgicas transformándolos en marionetas obedientes sin voluntad propia ni recuerdos. "
                "Cualquier intento de diálogo debe realizarse detrás de mamparas blindadas y bajo estricta vigilancia armada con rifles tranquilizantes de alto calibre para evitar una brecha biológica inminente... "
                "y la única señal de que la cura ya ha comenzado en tu cuerpo..."
            )

        # 6. SCP-3008: El IKEA Infinito (Supervivencia no euclidiana)
        if "3008" in top_lower or "3008" in scp_id or "ikea" in top_lower:
            return (
                "Entraste buscando muebles comunes para tu hogar, pero al darte la vuelta las puertas automáticas de cristal habían desaparecido para siempre en la nada absoluta. "
                "SCP-3008 es un almacén comercial infinito sin salida visible donde cientos de sobrevivientes atrapados construyen fortalezas defensivas con mesas y sofás para resistir el asedio nocturno. "
                "Al apagarse las luces a las diez de la noche, los empleados humanoides sin rostro patrullan los pasillos cazando a cualquiera que no esté refugiado tras las barricadas bajo la siniestra frase la tienda está cerrada. "
                "Nadie ha logrado escapar con vida de este laberinto infinito... "
                "y la razón por la que nunca debes entrar solo a una tienda desconocida..."
            )

        # 7. Incident Clef-Kondraki / SCP-239 (Crossover de personal mítico / LaloBeRoth style)
        if "clef" in top_lower or "kondraki" in top_lower or "239" in top_lower:
            return (
                "El incidente más caótico y desquiciado en la historia de la Fundación SCP ocurrió cuando el doctor Clef intentó eliminar a una niña con poderes de alteración de la realidad. "
                "Para detenerlo, el doctor Kondraki liberó a cientos de mariposas carnívoras y montó al mismísimo reptil inmortal 682 por los pasillos blindados del Sitio-17. "
                "La colosal batalla interna destruyó la mitad de las instalaciones del sector y casi provoca la fuga masiva de todas las anomalías Keter bajo custodia permanente del personal. "
                "Los registros de aquella masacre interna fueron censurados por el Consejo O5 para ocultar la verdad... "
                "por eso, cuando dos científicos legendarios entran en conflicto en el Sitio..."
            )

        # 8. SCP-173: La Escultura de Concreto
        if "173" in top_lower or "173" in scp_id or "escultura" in top_lower:
            return (
                "Bajo ninguna circunstancia apartes la vista ni parpadees frente a esta escultura de concreto y varillas de acero reforzado. "
                "Clasificado como Euclid por la Fundación, SCP-173 permanece completamente inmóvil mientras exista contacto visual directo e ininterrumpido con el sujeto. "
                "En la milésima de segundo en que cierras los ojos, se desplaza a velocidades imposibles y fractura las vértebras del cuello de sus observadores al instante. "
                "Para ingresar a limpiar su celda se necesitan tres operarios advirtiendo obligatoriamente en voz alta antes de cada parpadeo preventivo... "
                "y el motivo por el cual tus ojos comienzan a arder en este momento..."
            )

        # 9. Generic SCP Fallback (Dynamic, high retention, no boilerplate)
        if scp_entry:
            scp_name = scp_entry.get("name", "Anomalía")
            obj_class = scp_entry.get("object_class", "Euclid")
            facts = scp_entry.get("key_facts", [])
            fact_summary = " ".join(facts[:2]) if facts else "Manifiesta capacidades anómalas que distorsionan el espacio físico circundante."
            return (
                f"Archivo clasificado de la Fundación: ítem anómalo {scp_id}, catalogado bajo estricta clasificación {obj_class}. "
                f"Los protocolos de contención prohíben cualquier aproximación sin autorización formal previa de los mandos superiores Nivel 4. {fact_summary} "
                "Durante la última prueba oficial con sujetos Clase-D, los sensores térmicos registraron fluctuaciones críticas mientras la compuerta blindada comenzaba a ceder bajo una presión inexplicable y un descenso brusco de temperatura en el sector. "
                "El Sitio fue puesto bajo protocolo de aislamiento total y el expediente permanece clasificado... "
                "por eso, si alguna vez te encuentras frente a esta anomalía prohibida..."
            )

        # 10. General Horror / Creepypasta Short (High tension, visceral dread, seamless loop)
        clean_topic = re.sub(r"[""'']", "", topic).strip()
        return (
            f"A las tres de la madrugada, los sensores perimetrales de la estación registraron una presencia imposible alrededor de {clean_topic}. "
            "Las cámaras térmicas captaron una silueta tridimensional desplazándose en contra de las fuentes de luz artificial mientras un frío glacial congelaba los cristales blindados de la cabina de control. "
            "Una modulación distorsionada comenzó a repetir nuestros nombres por los altavoces de emergencia mientras los monitores perdían la señal de video uno a uno. "
            "Las compuertas de acero estaban selladas herméticamente, pero las huellas sobre el piso revelaron que la criatura ya estaba adentro con nosotros... "
            "y la razón por la que nunca debes mirar por la ventana en la noche..."
        )

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
