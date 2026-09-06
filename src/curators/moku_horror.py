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
                "Cosquilleo bajo la piel: sal de esa celda. "
                "En el Sitio-19 de la Fundación, el anfitrión de SCP-027 no puede cerrar los ojos sin que miles de cucarachas, arañas venenosas y roedores broten espontáneamente a su alrededor en la oscuridad. "
                "Tres toneladas de vacío continuo incineran a las criaturas día y noche, pero las biopsias del personal médico revelaron lo peor: el enjambre no ataca al sujeto, sino que lo obedece como a una deidad viviente. "
                "Y si su corazón se detiene por un infarto o eutanasia profiláctica, la plaga saltará en un microsegundo al humano vivo más cercano en la habitación... "
                "por eso, la próxima vez que sientas algo caminar sobre tu cuello en la penumbra..."
            )

        # 2. SCP-001: El Dios Roto (Mekhane / Apocalipsis industrial / JOMOSU style)
        if "001" in top_lower or "001" in scp_id or "dios roto" in top_lower or "mekhane" in top_lower:
            return (
                "Este archivo borró una costa entera. "
                "En 1942, fanáticos de la Iglesia del Dios Roto ensamblaron un coloso biomecánico en las costas de Baja California "
                "creyendo resucitar a su deidad Mekhane para salvar a la humanidad. Pero cometieron un error fatal: el corazón instalado "
                "provenía de la infame Fábrica, una entidad corrupta que transformó la máquina en un titán insaciable devorador de metales "
                "y carne viva. La masa de engranajes hirvientes asimiló aldeas enteras, absorbiendo trenes, búnkeres y civiles en su torso "
                "de acero chirriante. Desesperada por evitar la aniquilación continental, la Fundación activó el cañón orbital de partículas "
                "para vaporizar la abominación en una detonación atómica clasificada... "
                "y la aterradora razón por la que el fondo marino aún emite pulsos mecánicos..."
            )

        # 3. Incident 096-1-A: La Fuga de los Cuatro Píxeles
        if "096-1-a" in top_lower or "incidente 096" in top_lower:
            return (
                "El incidente 096-1-A demostró que la Fundación jamás podrá contener lo inevitable. "
                "Veinte años después de unas vacaciones familiares en la montaña, un civil miró una vieja foto donde apenas cuatro píxeles "
                "borrosos revelaban el rostro de SCP-096. A miles de kilómetros de distancia, la criatura rompió su celda blindada en el Sitio-19 "
                "y comenzó una carrera frenética e imparable hacia el objetivo. Ni los ataques aéreos coordinados con misiles guiados, ni los proyectiles "
                "pesados de grueso calibre ni las unidades móviles de choque pudieron frenar el avance del monstruo. El escuadrón entero fue "
                "despedazado en segundos y la anomalía masacró al objetivo civil junto a todos los testigos del perímetro... "
                "y la inquietante advertencia de revisar cada rincón de tus fotografías antiguas..."
            )

        # 4. SCP-096: El Chico Tímido (Inevitabilidad / Terror cinético)
        if "096" in top_lower or "096" in scp_id or "tímido" in top_lower or "shy guy" in top_lower:
            return (
                "Cuatro píxeles en el fondo de una fotografía familiar bastaron para sentenciar a muerte a decenas de personas. "
                "SCP-096 parece un humanoide dócil y demacrado que pasa los días sollozando en posición fetal contra las paredes de su celda blindada. "
                "Pero en el instante exacto en que alguien observa sus rasgos faciales, ya sea en persona, video o mediante un reflejo insignificante, "
                "entra en una crisis homicida de pánico absoluto. La criatura emite alaridos inhumanos ensordecedores mientras rompe la contención a "
                "velocidades supersónicas, destrozando búnkeres de titanio, muros de hormigón y escuadrones fuertemente armados con un único objetivo: "
                "despedazar físicamente al observador sin dejar el menor rastro con vida... "
                "y la aterradora certeza de que jamás podrás esconderte de su mirada..."
            )

        # 5. SCP-1048: The Builder Bear (El Oso Constructor / LaloBeRoth style)
        if "1048" in top_lower or "1048" in scp_id or "oso" in top_lower or "builder bear" in top_lower:
            return (
                "Un tierno oso de peluche que se convirtió en la peor pesadilla biológica del Sitio-24 de la Fundación. "
                "Clasificado inicialmente como Seguro por deambular libremente abrazando con afecto a todo el personal, SCP-1048 comenzó "
                "a recolectar tejido humano en secreto durante las noches. La alarma general sonó cuando descubrieron en la cafetería a "
                "SCP-1048-A, una réplica grotesca construida enteramente con orejas humanas vivas amputadas. Al ser acorralada, la abominación "
                "emitió un chillido ultrasónico ensordecedor que hizo brotar cartílago de forma descontrolada dentro de los pulmones y gargantas "
                "de los guardias, asfixiándolos con su propia carne. El oso original continúa prófugo deslizándose por los conductos de ventilación "
                "subterráneos... "
                "por eso, si alguna vez encuentras un juguete de trapo mirándote desde la oscuridad..."
            )

        # 6. SCP-049: El Doctor de la Plaga (Locura quirúrgica)
        if "049" in top_lower or "049" in scp_id or "plaga" in top_lower or "peste" in top_lower:
            return (
                "Bajo su túnica negra y máscara de cuervo medieval no hay un salvador, sino la cura más atroz de la Fundación. "
                "SCP-049 insiste con fría y siniestra obsesión en que toda la humanidad padece una misteriosa enfermedad terminal llamada la Pestilencia. "
                "Un simple roce de sus manos enguantadas paraliza de golpe el sistema nervioso y detiene el corazón al instante sin causar dolor visible. "
                "Acto seguido, extrae de su maletín escalpelos e hilos oxidados para realizar brutales incisiones quirúrgicas en los tejidos, "
                "reanimando los cadáveres como criaturas desalmadas e hiperagresivas obedientes a sus órdenes. Los investigadores vigilan su celda "
                "tras mamparas blindadas armados con tranquilizantes pesados, conscientes de que para el doctor todos somos pacientes terminales... "
                "y la única señal de que su tratamiento ya comenzó en tus venas..."
            )

        # 7. SCP-3008: El IKEA Infinito (Supervivencia no euclidiana)
        if "3008" in top_lower or "3008" in scp_id or "ikea" in top_lower:
            return (
                "Entraste buscando muebles comunes para tu hogar, pero al darte la vuelta las puertas automáticas de cristal habían desaparecido para siempre en la nada absoluta. "
                "SCP-3008 es un almacén comercial infinito sin salida visible donde cientos de sobrevivientes atrapados construyen fortalezas defensivas con mesas y sofás para resistir el asedio nocturno. "
                "Al apagarse las luces a las diez de la noche, los empleados humanoides sin rostro patrullan los pasillos cazando a cualquiera que no esté refugiado tras las barricadas bajo la siniestra frase la tienda está cerrada. "
                "Nadie ha logrado escapar con vida de este laberinto infinito... "
                "y la razón por la que nunca debes entrar solo a una tienda desconocida..."
            )

        # 8. Incident Clef-Kondraki / SCP-239 (Crossover de personal mítico / LaloBeRoth style)
        if "clef" in top_lower or "kondraki" in top_lower or "239" in top_lower:
            return (
                "El incidente más caótico y desquiciado en la historia de la Fundación SCP ocurrió cuando el doctor Clef intentó eliminar a una niña con poderes de alteración de la realidad. "
                "Para detenerlo, el doctor Kondraki liberó a cientos de mariposas carnívoras y montó al mismísimo reptil inmortal 682 por los pasillos blindados del Sitio-17. "
                "La colosal batalla interna destruyó la mitad de las instalaciones del sector y casi provoca la fuga masiva de todas las anomalías Keter bajo custodia permanente del personal. "
                "Los registros de aquella masacre interna fueron censurados por el Consejo O5 para ocultar la verdad... "
                "por eso, cuando dos científicos legendarios entran en conflicto en el Sitio..."
            )

        # 9. SCP-173: La Escultura de Concreto
        if "173" in top_lower or "173" in scp_id or "escultura" in top_lower:
            return (
                "Bajo ninguna circunstancia apartes la vista ni parpadees frente a esta escultura de concreto y varillas de acero reforzado. "
                "Clasificado como Euclid por la Fundación, SCP-173 permanece completamente inmóvil mientras exista contacto visual directo e ininterrumpido con el sujeto. "
                "En la milésima de segundo en que cierras los ojos, se desplaza a velocidades imposibles y fractura las vértebras del cuello de sus observadores al instante. "
                "Para ingresar a limpiar su celda se necesitan tres operarios advirtiendo obligatoriamente en voz alta antes de cada parpadeo preventivo... "
                "y el motivo por el cual tus ojos comienzan a arder en este momento..."
            )

        # 10. Generic SCP Fallback (Dynamic, high retention, no boilerplate)
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

        # 11. General Horror / Creepypasta Short (High tension, visceral dread, seamless loop)
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
