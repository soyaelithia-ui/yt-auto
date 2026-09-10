"""
Narrative synthesis templates for YouTube automation pipelines.
Provides channel-isolated narrative builders for Moku (Horror/SCP) and Aelithia (Drama/AITA),
free of vocalized structural headers, with rich first-person immersion, dialogue, and zero mechanical repetition.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from src.branding import resolve_channel_key
from src.core.scp_lore import lookup_scp


def build_moku_short_narrative(
    topic: str,
    channel: str = "moku",
    **kwargs: Any,
) -> str:
    """
    Build a high-retention Short narrative for Moku (Horror/SCP).
    Calibrated strictly to 180-320 words for optimal 65-115s pacing at 165 WPM.
    Grounded dynamically in official canonical lore when an SCP is detected,
    or rich procedural horror generation parameterized by topic.
    Starts with a 0-3s direct hook without conversational greetings.
    """
    clean_topic = re.sub(r"[""'']", "", topic).strip()

    scp_entry = lookup_scp(topic)
    if scp_entry:
        scp_id = scp_entry.get("scp_id", "")
        obj_class = scp_entry.get("object_class", "Euclid")
        facts = list(scp_entry.get("key_facts", ()))
        sensory = scp_entry.get("sensory_cues", {})
        hooks = scp_entry.get("narrative_hooks", ())
        summary = scp_entry.get("containment_summary", "")

        canonical_name = scp_entry.get("canonical_name", {}).get("es", "")
        name_phrase = f", conocido como {canonical_name}," if canonical_name else ""
        if hooks:
            hook = f"{hooks[0]} Expediente clasificado de la Fundación para {scp_id}{name_phrase}, bajo clasificación {obj_class}."
        else:
            hook = f"Expediente clasificado de la Fundación para {scp_id}{name_phrase}, bajo estricta clasificación {obj_class}: {clean_topic}."

        facts_text = " ".join(facts[:4]) if facts else "Contiene manifestaciones imposibles que desafían toda explicación científica conocida en el mundo actual."
        sensory_text = ""
        if sensory.get("visual"):
            sensory_text += f" Los reportes visuales describen {sensory['visual'].lower()}."
        if sensory.get("auditory"):
            sensory_text += f" El análisis acústico confirmó {sensory['auditory'].lower()}."

        containment_text = (
            f" {summary}" if summary else
            " Los protocolos de contención primaria exigen mamparas blindadas herméticas bajo estricto aislamiento de nivel cuatro."
        )

        body = (
            f"{facts_text}{sensory_text}{containment_text} "
            "Durante las últimas pruebas oficiales con personal Clase-D, los sensores biométricos registraron fluctuaciones críticas "
            "mientras la compuerta blindada comenzaba a ceder bajo una tensión estructural inexplicable y un descenso térmico abrupto. "
            "El Sitio fue puesto de inmediato bajo código de emergencia máxima y cualquier aproximación no autorizada permanece "
            "terminantemente prohibida bajo pena de confinamiento disciplinario definitivo en celdas de aislamiento permanente."
        )
        outro = (
            "El expediente completo permanece bajo aislamiento de máxima seguridad... "
            "por eso, si alguna vez te encuentras frente a esta anomalía prohibida..."
        )
        return f"{hook}\n\n{body}\n\n{outro}"

    # Dynamic procedural horror / creepypasta short narrative parameterized by topic
    hook = f"Una advertencia urgente sobre lo ocurrido en torno a {clean_topic}."
    body = (
        f"Las patrullas de guardia en torno a {clean_topic} comenzaron a registrar anomalías térmicas y electromagnéticas que desafían cualquier explicación científica conocida. "
        "Alrededor de la medianoche, los sensores perimetrales se descalibraron súbitamente mientras las cámaras de seguridad captaban una silueta tridimensional desplazándose contra las fuentes de iluminación artificial en el sector restringido. "
        "Un frío glacial comenzó a condensar el aire dentro de la cabina de control y los altavoces de emergencia empezaron a modular susurros entrecortados que repetían los nombres del personal de guardia en tiempo real. "
        "Al acudir a inspeccionar con linternas de alta potencia, las puertas blindadas permanecían selladas con doble cerrojo mecánico, pero sobre el suelo helado se descubrió un rastro húmedo y marcas profundas que indicaban que la presencia ya se encontraba dentro de las instalaciones. "
        "Las transmisiones de radio con el exterior quedaron bloqueadas por un pulso continuo de estática y la única certeza del equipo fue apagar las luces y mantenerse en silencio absoluto hasta el amanecer."
    )
    outro = (
        "El informe forense permanece archivado bajo reserva oficial estricta... "
        "y la razón por la que nunca debes mirar por la ventana en la noche..."
    )
    return f"{hook}\n\n{body}\n\n{outro}"


def build_aelithia_short_narrative(
    topic: str,
    channel: str = "aelithia",
    **kwargs: Any,
) -> str:
    """
    Build a high-retention Short narrative for Aelithia (Drama / AITA / Moral Dilemmas).
    Calibrated strictly to 180-320 words for optimal 65-115s pacing at 165 WPM.
    Starts with a 0-3s direct hook framing the moral dilemma, followed by vivid first-person
    confrontation with direct dialogue quotes, boundaries, and community engagement outro.
    """
    clean_topic = re.sub(r"[""'']", "", topic).strip()

    hook = f"¿Soy yo el malo por poner límites definitivos a mi entorno más cercano en torno a {clean_topic}?"
    body = (
        f"Durante años trabajé turnos dobles y sacrifiqué mi tiempo personal para construir una estabilidad propia con esfuerzo honrado, pero todo cambió cuando surgió el conflicto sobre {clean_topic}. "
        "En una reunión que parecía inofensiva, mis parientes decidieron tender una emboscada moral para exigirme que entregara mis ahorros y asumiera responsabilidades financieras que no me correspondían. "
        "Me dijeron textualmente: 'La familia siempre va primero y si te va bien tienes la obligación moral de salvarnos a todos de nuestras malas decisiones'. "
        "Cuando me negué con total serenidad respondiendo: 'No voy a permitir que destruyan mi estabilidad económica ni mi dignidad personal por caprichos ajenos', "
        "el ambiente se transformó en un juicio implacable donde me acusaron de egoísta, frío y desleal, amenazando con expulsarme de futuros encuentros familiares. "
        "A pesar de las llamadas insistentes y las presiones colectivas en redes sociales, decidí proteger mis límites y buscar asesoría profesional independiente para blindar mis decisiones. "
        "El distanciamiento fue sumamente amargo en un inicio, pero me brindó una paz mental inquebrantable que ningún chantaje afectivo puede arrebatarme."
    )
    outro = "¿Habrías actuado igual en mi posición? Déjame tu punto de vista en los comentarios y comparte tu experiencia con nosotros."
    return f"{hook}\n\n{body}\n\n{outro}"


def build_scp3000_longform_narrative(
    topic: str,
    channel: str = "moku",
    target_duration_minutes: float = 12.0,
    **kwargs: Any,
) -> str:
    """
    Builds an in-depth, canon-grounded, multi-act documentary narrative for SCP-3000 (Anantashesha)
    calibrated to >=2,600 words (12-16 minutes).
    Structured in 10 continuous immersive beats covering the Bay of Bengal abyss, cognitive decay,
    the harvesting of Y-909, and the horrifying secret behind Foundation amnestics.
    """
    paragraphs = [
        # Beat 1: In Media Res Hook & Ocean Trench Descent
        (
            f"A tres mil metros de profundidad en las aguas oscuras y asfixiantes de la Bahía de Bengala descansa el secreto más perturbador y moralmente demoledor de la Fundación SCP en torno a {topic}. "
            "En ese abismo absoluto, donde la luz del sol se extinguió hace millones de años y la presión aplastante del agua es capaz de colapsar un bloque macizo de titanio como si fuera papel delgado, opera en silencio el buque de contención SCPS Eremita y la estación submarina ATLS-12. "
            "No se trata de una base de investigación convencional ni de un puesto de monitoreo oceanográfico ordinario, sino de una operación clandestina de supervivencia extrema diseñada para custodiar a la entidad biológica más grande jamás descubierta por la humanidad: una criatura clasificada bajo la categoría Thaumiel, cuyo propio nombre en sánscrito antiguo evoca el fin de los tiempos: Anantashesha. "
            "Quienes han descendido a bordo de los batiscafos presurizados coinciden en una advertencia unánime: en el fondo de esa fosa marina, la oscuridad no es simplemente la ausencia de fotones, sino una masa viva y palpable que parece alimentarse de tus pensamientos antes de que alcances a formularlos. "
            "El sonido de los cascos de inmersión crujiendo bajo la presión tectónica acompaña el descenso hacia un vacío total donde los instrumentos de navegación electrónica comienzan a fallar sin explicación alguna. "
            "Una sensación de frío sobrenatural atraviesa los mamparos térmicos más gruesos, haciendo que los operarios sientan el temblor involuntario de la piel y una intensa pesadez en el pecho que ninguna mezcla de gases respiratorios logra aliviar. "
            "En este fondo marino desolado, las corrientes oceánicas parecen detenerse por completo, creando una quietud sepulcral que amplifica cada latido cardíaco dentro de las escafandras presurizadas."
        ),
        # Beat 2: Colossal Dimensions & Non-Euclidean Biology
        (
            "Los informes de los sónares activos y pasivos de la Fundación describen a la entidad como una serpiente marina anguilliforme de proporciones físicamente inconcebibles, cuya longitud total se estima entre seiscientos y novecientos kilómetros de extensión. "
            "Su cuerpo colosal no permanece estático en el fondo arenoso, sino que se retuerce en bucles continuos y perezosos a lo largo de las dorsales submarinas, desafiando las leyes de la biomecánica y de la hidrodinámica terrestre. "
            "La cabeza de la criatura mide más de dos metros y medio de diámetro por sí sola, provista de una mandíbula dotada de múltiples hileras de dientes cónicos y dos ojos opacos y lechosos que no reflejan la luz de los reflectores de tungsteno. "
            "Los análisis espectrométricos revelan que la masa corporal de la serpiente desafía la geometría euclidiana ordinaria, expandiéndose y contrayéndose en pliegues espaciales que distorsionan el volumen del agua a su alrededor. "
            "Cualquier intento de cartografiar su extensión completa mediante satélites batimétricos genera patrones corruptos en los servidores centrales, como si el propio océano se negara a registrar la presencia física de este leviatán. "
            "Biólogos marinos asignados al proyecto intentaron inicialmente clasificarla como una especie mutada de morena gigante o un remanente prehistórico del período cámbrico, pero los patrones de descomposición celular observados en las muestras de tejido descartaron cualquier vínculo con el árbol de la vida conocido. "
            "Las ondas de baja frecuencia que emite su cuerpo al desplazarse hacen vibrar el lecho rocoso de toda la cuenca oceánica con un zumbido sordo e hipnótico."
        ),
        # Beat 3: The Cognitive Fog & Memory Dissolution
        (
            "Sin embargo, lo verdaderamente aterrador de Anantashesha no reside en su tamaño monstruoso ni en su capacidad para hundir flotas enteras de buques de guerra, sino en el campo cognitopeligroso invisible y devastador que proyecta en un radio de decenas de kilómetros. "
            "A medida que un submarino se aproxima al sector donde la criatura serpentea, la mente de los tripulantes comienza a experimentar una descomposición neurológica progresiva e irreversible. "
            "Primero desaparecen los recuerdos más recientes: los operarios olvidan la hora exacta de su turno de guardia, las órdenes recibidas hace pocos minutos o el motivo por el cual descendieron a las profundidades marinas. "
            "Posteriormente, la niebla cognitiva avanza hacia los recuerdos más profundos e íntimos: los rostros de sus cónyuges e hijos se difuminan en sombras borrosas, las canciones de la infancia se borran de la memoria y la habilidad para articular palabras complejas se extingue por completo. "
            "Los buzos que han trabajado en las esclusas exteriores reportan escuchar una vibración sorda en el interior del cráneo, una voz susurrante que no utiliza el lenguaje humano pero que transmite una sensación infinita de soledad, vacío cósmico y olvido absoluto. "
            "Es como si la criatura no solo habitara el abismo oceánico, sino que fuera una personificación física del propio olvido, devorando la identidad de cualquier ser vivo que entre en su dominio."
        ),
        # Beat 4: The Feeding Protocol and the Class-D Sacrifices
        (
            "Para comprender la razón por la cual la Fundación SCP mantiene una instalación permanente en un lugar tan hostil, es necesario adentrarse en el protocolo clasificado más oscuro del Sitio ATLS-12: el procedimiento de alimentación. "
            "Anantashesha es una criatura carnívora obligada, pero su organismo no se nutre de ballenas, peces abisales ni materia orgánica convencional; su apetito exige conciencias humanas despiertas y funcionales. "
            "A intervalos regulares de varias semanas, el Consejo O5 autoriza el transporte de sujetos Clase-D hacia las cámaras de inmersión profunda del buque de guardia. "
            "Los prisioneros son introducidos en jaulas de acero de alta densidad equipadas con transmisores biométricos y cámaras de video resistentes a la presión, para luego ser descendidos lentamente hacia la fosa donde la cabeza de la serpiente aguarda en reposo. "
            "Las grabaciones de audio recuperadas de estas jaulas documentan los momentos finales más angustiantes jamás registrados en los archivos de contención: los sujetos experimentan ataques de pánico violentos mientras gritan nombres que ya no recuerdan y suplican clemencia a figuras que han dejado de existir en sus mentes disueltas. "
            "En el instante en que las fauces de la criatura se abren para engullir la jaula, los monitores electroencefalográficos registran una descarga cerebral masiva de agonía psicológica antes de que la señal se corte definitivamente en la oscuridad abisal."
        ),
        # Beat 5: Compound Y-909 and the Secret of All Amnestics
        (
            "Es en este preciso instante de consumo y sufrimiento donde se produce el fenómeno que hace a SCP-3000 indispensable para la existencia misma de la civilización moderna. "
            "Durante el proceso digestivo de una mente humana consciente, la piel circundante a la cabeza de la entidad comienza a secretar una sustancia líquida, densa, de color negro azabache y textura viscosa que los investigadores denominan compuesto Y-909. "
            "Flotas de drones submarinos automatizados y brazos mecánicos se apresuran a recolectar cada mililitro de este fluido viscoso mediante bombas de succión presurizadas antes de que se disperse en las corrientes marinas profundas. "
            "El compuesto Y-909 es el principio activo fundamental, insustituible e irremplazable a partir del cual la Fundación SCP sintetiza todos los amnésicos de Clase A, Clase B, Clase C y Clase D que utiliza diariamente en todo el planeta. "
            "Cada vez que un civil presencia una anomalía aterradora, cada vez que un monstruo es contenido y la población es sometida a un borrado de memoria para mantener el velo de la normalidad, el químico que se inyecta en sus venas o se dispersa en aerosol proviene directamente de las secreciones de Anantashesha. "
            "La normalidad del mundo entero descansa sobre el sacrificio humano continuo y metódico entregado a una serpiente milenaria en el fondo del océano índico. "
            "Sin la extracción constante en la Bahía de Bengala, las reservas globales de amnésicos se agotarían en cuestión de noventa días, provocando la caída irreversible del secreto de contención y la histeria colectiva en todas las naciones."
        ),
        # Beat 6: The Historical Discovery in 1971 and Naval Anomalies
        (
            "Los registros históricos de la Fundación sitúan el primer contacto oficial con la criatura en el año 1971, durante el conflicto naval de la Guerra Indo-Pakistaní en el Golfo de Bengala. "
            "En aquel entonces, dos submarinos militares convencionales desaparecieron sin dejar rastro de combate ni restos flotantes en una zona supuestamente libre de campos de minas. "
            "Las estaciones de escucha hidroacústica de la región registraron un pulso de baja frecuencia masivo y sostenido que no correspondía a explosiones de torpedos ni a sismos submarinos. "
            "Cuando la Fundación desplegó sus primeros buques de investigación encubiertos bajo la fachada de expediciones oceanográficas internacionales, los buzos de saturación descubrieron los restos de los navíos incrustados en la fosa a más de dos mil metros de profundidad. "
            "Las compuertas de ambos sumergibles habían sido abiertas desde el interior por los propios marineros, cuyos cuerpos jamás fueron recuperados. "
            "En las grabadoras de cinta magnética de las salas de control se escuchaban las voces de los oficiales cantando en idiomas desconocidos mientras describían a un dios negro con forma de serpiente que los invitaba a sumergirse en las aguas heladas para olvidar sus nombres. "
            "Aquel incidente obligó al Consejo O5 a declarar la zona como perímetro de exclusión marítima permanente bajo el mando directo de la Fuerza de Tarea Móvil Gamma-6."
        ),
        # Beat 7: The Tragic Logs of Dr. Krishnamoorthy
        (
            "Entre los expedientes clasificados más impactantes de la estación ATLS-12 destacan las transcripciones personales del Doctor Krishnamoorthy, el neurocientífico jefe asignado para supervisar la recolección del fluido durante la década pasada. "
            "A lo largo de sus registros diarios en audio, es posible trazar el colapso psicológico gradual de un hombre brillante que intentó comprender la naturaleza metafísica de la entidad. "
            "En sus primeras notas, Krishnamoorthy registraba datos técnicos sobre la pureza del amnésico con frialdad metodológica; sin embargo, tras setenta días de exposición a las frecuencias del abismo, su lenguaje comenzó a fragmentarse en reflexiones poéticas y aterradoras. "
            "En sus diarios personales describía cómo sus propios recuerdos familiares eran sustituidos por visiones de templos sumergidos y mares negros que existieron antes de la formación de los continentes. "
            "En su última grabación oficial, fechada a las cuatro de la madrugada, su voz suena tranquila pero desprovista de cualquier rasgo de emoción humana: 'No hay nada después de la muerte', susurra el científico en el micrófono de la cabina. 'No hay cielo, no hay reencarnación ni castigo. Solo está la boca de la serpiente esperando que el tiempo termine. He visto el abismo donde van a parar todos los recuerdos del universo, y es hermoso en su frialdad absoluta'. "
            "Minutos después de registrar aquellas palabras, el doctor desactivó los protocolos de seguridad de la esclusa número tres y se arrojó a las aguas heladas sin equipo de respiración, desapareciendo para siempre en la fosa abisal."
        ),
        # Beat 8: The Psychological Logs of D-4752 and D-5291
        (
            "Los archivos de audio de las misiones de inmersión tripuladas aportan los testimonios más escalofriantes sobre la distorsión de la identidad provocada por la proximidad de la criatura. "
            "Durante la prueba de alimentación designada como Protocolo Beta-Nueve, dos sujetos de prueba Clase-D fueron descendidos juntos dentro de una cámara de titanio reforzado mientras los sensores registraban su actividad cognitiva. "
            "A los cuatro minutos de descenso, el sujeto D-4752 comenzó a llorar desconsoladamente, afirmando con desesperación que recordaba la infancia de su compañero de celda con mayor nitidez que la suya propia. "
            "Describía la casa materna de D-5291, el nombre de su primera mascota y el accidente que marcó su adolescencia, mientras que D-5291 permanecía en un mutismo catatónico incapaz de pronunciar su propio apellido. "
            "Las memorias de ambos hombres se habían entrelazado y fundido en el campo de radiación psíquica de la serpiente, intercambiando vivencias y traumas personales como si sus cerebros fueran vasos comunicantes vertiéndose en el mismo vacío. "
            "Momentos antes de que la masa colosal de Anantashesha envolviera la cápsula, D-4752 susurró por la radio una última frase que quedó grabada en los servidores del buque de mando: 'Ya no soy yo, y él tampoco es él; la serpiente está bebiendo nuestras vidas y lo único que queda es el agua negra'. "
            "La señal de los electrodos cardíacos se aplanó instantáneamente al producirse el impacto de las mandíbulas de la entidad contra el blindaje."
        ),
        # Beat 9: The Nature of the Soul and the Void
        (
            "Las investigaciones psiquiátricas posteriores realizadas a los supervivientes de las misiones submarinas arrojaron una hipótesis aún más sombría que la simple pérdida biológica de recuerdos. "
            "Los sujetos expuestos al campo de Anantashesha no sufren una amnesia temporal reparable mediante terapias neurológicas; lo que ocurre es una extirpación ontológica del tejido mismo de la conciencia. "
            "Cuando la entidad absorbe un recuerdo, ese evento parece no haber ocurrido jamás en el plano metafísico de la realidad, dejando un vacío negro en el alma de la persona afectada que genera cuadros crónicos de depresión existencial, apatía severa y despersonalización completa. "
            "Varios buzos rescatados tras fallas en los sistemas de presurización fueron incapaces de reconocer su propio reflejo en el espejo, afirmando que el cuerpo que habitaban pertenecía a un extraño que había muerto hace siglos. "
            "La conclusión de los comités de ética de la Fundación fue tajante y despiadada: el daño cognitivo es un costo colateral aceptable frente a la necesidad imperiosa de mantener el suministro global de amnésicos en niveles operativos estables. "
            "El Consejo O5 selló estos informes bajo clasificación de máxima seguridad, prohibiendo que los agentes de campo conozcan el verdadero origen de los viales amnésicos que llevan en sus cinturones tácticos."
        ),
        # Beat 10: Underwater Submersible Dive Telemetry and Scranton Anchors
        (
            "Durante la Operación Fosa Profunda, un dron de exploración no tripulado equipado con blindaje de aleación de osmio y un ancla de realidad Scranton miniaturizada logró descender hasta rozar el lomo de la criatura a cuatro mil doscientos metros bajo el nivel del mar. "
            "El ancla de realidad tenía como objetivo estabilizar los niveles de Hume para permitir mediciones cuánticas directas, pero el campo emitido por Anantashesha sobrecargó los condensadores en cuestión de segundos, reduciendo la densidad ontológica del área a niveles cercanos a cero. "
            "Las imágenes transmitidas por fibra óptica antes del colapso del cable mostraron la textura de las escamas de la serpiente: placas gigantescas de queratina fosilizada cubiertas por una densa capa de sedimentos marinos milenarios y colonias de gusanos tubícolas bioluminiscentes. "
            "Al encender los reflectores principales hacia el sector cefálico, la cámara captó por primera vez el movimiento de sus párpados translúcidos, revelando una pupila vertical del tamaño de un automóvil que parecía mirar directamente a través de la lente electrónica hacia los operadores en la superficie. "
            "En ese milisegundo de contacto visual mediado por pantallas, todos los técnicos en la sala de control del buque experimentaron una pérdida repentina de visión temporal y sangrado nasal simultáneo. "
            "La telemetría del dron registró una elevación de temperatura en el agua circundante de más de quince grados en un segundo, como si la respiración del monstruo emanara calor geotérmico directo desde el manto terrestre. "
            "El vehículo fue succionado hacia una cavidad oscura antes de que los sensores de presión estallaran por sobrecarga estructural."
        ),
        # Beat 11: Philosophical Horror & The Inevitable Return
        (
            "Vivir en un mundo custodiado por la Fundación SCP implica aceptar una paradoja aterradora: nuestra cordura cotidiana depende de un monstruo que devora la esencia misma de lo que nos hace humanos. "
            "Cada vez que la humanidad olvida un encuentro con lo imposible, cada vez que una ciudad despierta creyendo que una catástrofe fue simplemente una fuga de gas o una tormenta meteorológica, una gota del sufrimiento destilado en la Bahía de Bengala ha sido vertida en la memoria colectiva. "
            "Y en lo más profundo de la fosa abisal, la colosal serpiente de novecientos kilómetros continúa retorciéndose en la oscuridad, paciente, inmortal y hambrienta. "
            "Sabe que no necesita subir a la superficie para reclamar su reino sobre la Tierra, porque tarde o temprano, cada pensamiento, cada amor, cada memoria y cada civilización terminarán hundiéndose en su boca insaciable. "
            "La certeza de que el olvido definitivo aguarda bajo las olas es la verdad más pesada que cualquier ser humano puede llegar a contemplar en el silencio de la noche."
        ),
        # Beat 12: Final Lore Synthesis & Archive Custody
        (
            "El expediente del Sitio de Contención SCP-3000 permanece clasificado bajo el nivel cinco de seguridad y las patrullas del buque SCPS Eremita continúan navegando las coordenadas restringidas de la Bahía de Bengala sin descanso. "
            "Las jaulas de alimentación siguen descendiendo hacia las fosas oceánicas y los viales de amnésicos continúan distribuyéndose por cada continente para sostener la frágil ilusión de control que llamamos realidad. "
            "El informe completo, las grabaciones recuperadas del fondo marino y los análisis de telemetría abisal permanecen bajo custodia oficial en los archivos clasificados de la Fundación."
        ),
    ]
    return "\n\n".join(p.strip() for p in paragraphs)


def build_moku_longform_narrative(
    topic: str,
    channel: str = "moku",
    target_duration_minutes: float = 10.5,
    **kwargs: Any,
) -> str:
    """
    Build a rich, progressive, non-repeating first-person horror/creepypasta narrative (>=2100 words)
    calibrated for 10+ minute documentary immersion.
    Inspired by gold-standard benchmark 'La Frecuencia Prohibida de la Estación de Montaña'.
    Free of vocalized structural section headers ('Sección Primera:', etc.) and mechanical title repetition.
    """
    # Grounded canonical SCP longform documentaries
    norm_topic = topic.lower()
    if "3000" in norm_topic or "anantashesha" in norm_topic:
        return build_scp3000_longform_narrative(
            topic,
            channel=actual_channel,
            target_duration_minutes=target_duration_minutes,
            **kwargs,
        )

    paragraphs = [
        # Beat 1: In Media Res Hook & Setting the Atmosphere
        (
            f"Hay experiencias que marcan un antes y un después en la cordura de una persona, y lo que viví durante los días en que comenzó {topic} "
            "es algo que jamás he podido borrar de mi memoria ni explicar mediante la lógica ordinaria. Todo empezó en una estación de monitoreo remota "
            "ubicada en lo profundo del valle, donde mi labor como técnico de guardia consistía en supervisar las frecuencias de radio y registrar anomalías climáticas. "
            "La rutina era solitaria, monótona y predecible, hasta aquella noche de niebla densa en la que los instrumentos comenzaron a captar señales extrañas. "
            "El silencio habitual del bosque se extinguió de golpe, dando paso a una quietud antinatural donde ni siquiera el viento parecía mover las ramas de los pinos. "
            "Recuerdo haber mirado por el ventanal de la torre de control y sentir, por primera vez en mi vida, la certeza absoluta e instintiva de que no estábamos solos en ese lugar. "
            "La sensación de ser observado desde las sombras se clavaba en mi nuca con una intensidad física palpable, obligándome a revisar constantemente los cerrojos de las puertas blindadas. "
            "En medio de esa calma ficticia, los indicadores del panel de control comenzaron a fluctuar con pequeñas descargas estáticas que hacían vibrar los resortes de los cuadrantes analógicos. "
            "Sabía que debí mantener la compostura y registrar cada variación en la bitácora oficial, pero un presentimiento oscuro me advertía que algo fuera de control se aproximaba desde las profundidades del bosque."
        ),
        # Beat 2: First Disturbing Anomaly & Audio Interference
        (
            "Alrededor de las dos de la madrugada, los altavoces de la consola principal emitieron un chasquido agudo que me sobresaltó por completo en medio de la penumbra. "
            "No era la típica interferencia estática producida por una tormenta eléctrica lejana, sino una oscilación rítmica y modulada que parecía imitar la cadencia de una respiración humana entrecortada. "
            "Ajusté los diales de sintonización intentando limpiar la frecuencia, pero cuanto más filtraba el ruido de fondo, más clara se volvía una voz apagada y distante que repetía coordenadas numéricas. "
            "Revisé el mapa topográfico de la región y comprobé con escalofríos que esas coordenadas señalaban un punto ciego en la ladera norte, un sector clausurado hace décadas tras la desaparición de un grupo de guardabosques. "
            "El frío en la cabina se volvió insoportable, congelando el vaho de mi respiración mientras las luces fluorescentes parpadeaban al compás de aquella misteriosa transmisión electromagnética. "
            "Cada susurro emitido por la bocina parecía dirigirse a mí de manera personal, pronunciando sílabas entrecortadas que hacían erizar el vello de mis brazos. "
            "Intenté enviar un mensaje de confirmación hacia la central regional para verificar si alguna estación meteorológica cercana reportaba interferencias similares en sus canales de auxilio. "
            "Sin embargo, la señal de salida rebotaba con un retardo acústico perturbador, devolviendo el eco distorsionado de mi propia voz cargado de un matiz metálico y amenazante."
        ),
        # Beat 3: Night Shift Isolation & Unexplained Perimeter Movement
        (
            "Decidí salir al corredor exterior con una linterna táctica para verificar los generadores auxiliares y asegurarme de que la línea de alimentación no sufriera desperfectos. "
            "El aire afuera era denso, impregnado de un penetrante olor a ozono y tierra húmeda que provocaba una ligera náusea en la garganta y una sensación de mareo constante. "
            "Al iluminar la valla perimetral metálica, el haz de luz reveló una silueta oscura e inmóvil recortada contra la niebla, a escasos treinta metros de distancia. "
            "Grité exigiendo identificación, creyendo que se trataba de algún excursionista extraviado, pero la figura no respondió ni realizó el menor gesto humano; simplemente permaneció estática, absorbiendo la luz como si fuera un vacío tridimensional. "
            "Cuando di un paso hacia adelante para acercarme, la silueta se desvaneció de golpe entre los árboles sin producir el crujido de una sola hoja en el suelo helado. "
            "El termómetro digital de mi reloj cayó bruscamente tres grados bajo cero en cuestión de segundos, confirmando que la anomalía térmica no era producto de mi imaginación. "
            "El vapor helado que salía de mi boca se condensaba tan rápido que apenas podía distinguir el sendero que conducía de vuelta hacia las escalinatas de acceso a la torre de control. "
            "Un zumbido sordo y penetrante comenzó a resonar desde la base del suelo rocoso, como si una inmensa maquinaria subterránea se hubiera puesto en marcha bajo mis propios pies."
        ),
        # Beat 4: Investigation of Archived Logs & Hidden Precedents
        (
            "Regresé de inmediato al interior de la estación, asegurando el cerrojo de la puerta blindada y encendiendo los monitores de respaldo con manos temblorosas. "
            "Abrí los archivadores de acero donde se guardaban los diarios de guardia de los antiguos operadores de la estación que habían prestado servicio en décadas pasadas. "
            "Encontré las libretas y expedientes de técnicos predecesores fechados a finales de los años ochenta, y lo que leí en sus páginas me heló la sangre por completo. "
            "Los antiguos operarios describían exactamente los mismos patrones acústicos, las mismas coordenadas en la ladera norte y una advertencia manuscrita en letras rojas: 'Si la frecuencia se sincroniza con tu voz, no respondas por radio'. "
            "El registro se interrumpía abruptamente en las últimas páginas de octubre, con una última anotación desordenada que decía: 'Ya sabe mi nombre y está tocando la ventana'. "
            "La caligrafía temblorosa de aquellas líneas reflejaba un pánico idéntico al que en ese preciso momento comenzaba a dominar mis propios pensamientos. "
            "Al consultar las planillas de servicio descubrí que nadie más había querido asumir este turno nocturno, obligándome a reconocer que mi puesto conllevaba riesgos que la administración jamás se atrevió a detallar formalmente. "
            "En las fichas de personal simplemente figuraban escuetas notas administrativas que catalogaban las ausencias repentinas como abandonos voluntarios de servicio sin entrega de inventario."
        ),
        # Beat 5: The Escalation & Direct Encounter
        (
            "A las tres y media de la madrugada, el transceptor de mano que llevaba en el cinturón crujió de forma violenta, emitiendo una ráfaga de estática blanca ensordecedora. "
            "Una voz distorsionada, pero aterradoramente familiar porque sonaba idéntica a la mía, comenzó a narrar en tiempo real cada movimiento que yo realizaba dentro de la cabina. "
            "'Ahora estás mirando hacia la puerta', susurraba el altavoz con un eco metálico escalofriante. 'Ahora sientes cómo se acelera tu pulso mientras miras la manija'. "
            "En ese instante exacto, la manija de la puerta principal comenzó a descender lentamente desde el exterior, como si alguien estuviera probando el pestillo con una calma calculada y siniestra. "
            "Me quedé paralizado, conteniendo el aliento en la penumbra más absoluta mientras el frío calaba mis huesos y una sombra alargada se proyectaba por debajo del umbral de acero. "
            "El sonido de uñas raspando la pintura exterior de la chapa blindada resonó por todo el habitáculo, confirmando que la entidad estaba al otro lado esperando mi primer descuido. "
            "Los instrumentos de medición comenzaron a sobrecargarse simultáneamente, haciendo saltar los fusibles de seguridad en una cascada de chispas incandescentes que sumieron la habitación en la oscuridad. "
            "Solo la tenue luz de la pantalla de emergencia iluminaba la silueta de la cerradura que cedía milímetro a milímetro bajo una fuerza invisible y descomunal."
        ),
        # Beat 6: The Climax & Breakthrough
        (
            "El miedo primitivo dio paso a un instinto ciego de supervivencia; agarré las llaves del vehículo todo terreno y la bengala de emergencia que colgaba junto al botiquín de primeros auxilios. "
            "Un golpe ensordecedor sacudió la estructura metálica de la torre, quebrando los vidrios reforzados del ventanal lateral y haciendo volar fragmentos de cristal sobre las consolas de mando. "
            "A través de la abertura en la niebla no vi un animal ni un ser de carne y hueso, sino una masa fluctuante de oscuridad que desafiaba toda comprensión geométrica y física elemental. "
            "Accioné la bengala con desesperación y el estallido de fósforo incandescente iluminó la sala con un fulgor rojo cegador que hizo retroceder a la entidad hacia la noche boscosa. "
            "Aproveché esa fracción de segundo para correr hacia la salida de emergencia, bajar las escaleras de hierro a toda prisa y subirme al vehículo sin mirar atrás ni una sola vez. "
            "El calor del fósforo quemaba el aire mientras el rugido de la manifestación retumbaba en las copas de los árboles como un trueno subterráneo. "
            "Las ramas azotaban la carrocería del vehículo mientras las ruedas patinaban sobre el barro congelado en un esfuerzo desesperado por ganar tracción y alcanzar la carretera principal. "
            "En el espejo retrovisor pude ver cómo una columna de penumbra densa se elevaba sobre la cumbre de la montaña, retorciéndose como un torbellino silencioso bajo las nubes de tormenta."
        ),
        # Beat 7: Escape & The Morning After
        (
            "Conduje a través del sendero forestal con el acelerador a fondo, sorteando curvas en penumbra mientras el motor rugía contra la pendiente resbaladiza de barro y nieve. "
            "Por el espejo retrovisor podía ver cómo las luces de la estación de montaña se apagaban definitivamente una tras otra, engullidas por la niebla espesa del valle. "
            "Llegué al puesto de guardia de la autopista con las primeras luces del amanecer, temblando de agotamiento, con las manos entumecidas y con las ropas rasgadas por los cristales rotos. "
            "Los oficiales que me recibieron creyeron al principio que había sufrido un ataque de pánico severo por aislamiento prolongado, pero cuando enviaron una patrulla a inspeccionar la estación, encontraron la torre sellada y las cintas de grabación magnética completamente desmagnetizadas y fundidas por un calor inexplicable. "
            "Las huellas en el lodo alrededor de la caseta mostraban marcas profundas que no correspondían a ningún calzado humano ni a ninguna fauna conocida de la reserva natural. "
            "El informe preliminar de la policía forestal concluyó que un rayo globular había impactado la instalación, pero los técnicos veteranos sabían que los daños en los circuitos no se correspondían con descargas atmosféricas convencionales. "
            "Fui interrogado durante horas por funcionarios vestidos de civil que confiscaron mi bitácora personal y me prohibieron terminantemente hacer declaraciones a la prensa local."
        ),
        # Beat 8: Scientific Review & Environmental Telemetry
        (
            "El informe técnico posterior elaborado por los peritos forenses y los especialistas en telecomunicaciones documentó alteraciones electromagnéticas incompatibles con cualquier fenómeno atmosférico registrado en la historia moderna de la región. "
            "Los transformadores de alta tensión presentaban una despolarización magnética absoluta y los núcleos de cobre exhibían patrones de cristalización que solo se generan bajo campos de radiación no ionizante de extrema potencia. "
            "Ninguno de los ingenieros pudo ofrecer una explicación plausible sobre cómo un pulso de semejante magnitud pudo originarse en medio de una reserva natural aislada sin fuentes de energía industriales en decenas de kilómetros a la redonda. "
            "Los expedientes fueron catalogados con un nivel de reserva extraordinario y las autoridades ordenaron la demolición controlada de la torre de observación, acordonando el sector con vallas electrificadas y carteles de peligro biológico ficticios para disuadir a curiosos. "
            "Vecinos de los poblados cercanos afirmaron haber visto convoyes militares escoltando camiones blindados durante las semanas posteriores al incidente, transportando instrumental científico pesado hacia la ladera norte. "
            "La versión oficial de las autoridades locales sostuvo que se trataba de obras rutinarias de mantenimiento hidroeléctrico, pero el acceso a toda la cuenca montañosa quedó restringido indefinidamente al público."
        ),
        # Beat 9: Witnesses & Lingering Echoes
        (
            "A lo largo de los meses siguientes, mantuve contacto en estricto secreto con dos antiguos guardabosques que habían patrullado la misma zona durante los años noventa. "
            "Ambos coincidieron en relatar experiencias casi idénticas: pérdidas repentinas de noción temporal, voces familiares que susurraban desde receptores apagados y la visión recurrente de siluetas estáticas entre la niebla invernal. "
            "Uno de ellos me confesó que su compañero de patrulla había desaparecido una noche de guardia sin dejar más rastro que su linterna encendida apoyada sobre el tocón de un pino centenario. "
            "Comprendí entonces que la estación de montaña nunca había sido un simple puesto de vigilancia climática, sino un intento encubierto de monitorear un foco de actividad anómala que la ciencia oficial no se atrevía a reconocer públicamente. "
            "Cada testimonio que recopilaba encajaba como una pieza siniestra en un rompecabezas que abarcaba más de cinco décadas de encubrimiento sistemático y desapariciones sin resolver. "
            "Las familias de los desaparecidos habían recibido indemnizaciones confidenciales a cambio de firmar acuerdos de silencio que les impedían solicitar investigaciones forenses independientes."
        ),
        # Beat 10: Psychological Aftermath & Unsettling Reflection
        (
            "Han pasado varios meses desde aquella noche y renuncié inmediatamente a mi puesto en el servicio de telecomunicaciones forestales para intentar rehacer mi vida en la ciudad. "
            "Sin embargo, el silencio de la noche ya nunca ha vuelto a ser pacífico para mí; cada vez que una radio emite estática o una luz parpadea en mi apartamento, siento que la conexión no se ha roto del todo. "
            "Hay enigmas ocultos en la naturaleza y en los rincones olvidados del mundo que la ciencia moderna prefiere ignorar para preservar nuestra frágil sensación de seguridad cotidiana. "
            "A veces me pregunto cuántos otros técnicos han escuchado esa misma frecuencia en estaciones solitarias a lo largo de las décadas y cuántos de ellos no tuvieron la suerte de encontrar una salida a tiempo. "
            "La certeza de que esa presencia sigue esperando en el valle es algo que me acompaña en cada vigilia solitaria, recordándome la fragilidad de nuestra existencia frente a lo desconocido. "
            "Las pesadillas recurrentes en las que vuelvo a escuchar mi propio nombre desde el altavoz me obligan a despertar sobresaltado, revisando las esquinas de mi habitación en busca de sombras que no deberían estar allí."
        ),
        # Beat 11: Lore Insights & Historical Context
        (
            "Investigaciones posteriores en archivos desclasificados revelaron que la estación había sido construida sobre los cimientos de una antigua base militar abandonada en los años sesenta. "
            "Los registros médicos de aquella época mencionaban casos reiterados de alucinaciones auditivas compartidas, desorientación espacial y bajas inexplicables entre los soldados asignados al radar. "
            "Todo indicaba que el valle entero actuaba como una especie de amplificador natural para un fenómeno que no pertenece a nuestra dimensión física habitual. "
            "Al compartir hoy este testimonio con ustedes, espero alertar a quienes transitan por zonas boscosas aisladas sobre la importancia de no desafiar aquello que no comprendemos. "
            "La curiosidad humana nos empuja con frecuencia a explorar territorios prohibidos, pero hay umbrales que jamás deberían ser cruzados por nuestra propia integridad mental y espiritual. "
            "El costo de mirar fijamente hacia el abismo es que tarde o temprano el abismo encuentra la manera de devolverte la mirada."
        ),
        # Beat 12: Anomalous Audio Decryption & Mimetic Feedback
        (
            "Al revisar los registros de audio digitalizados semanas después de abandonar el valle, descubrí una anomalía aún más perturbadora en las pistas de baja frecuencia que la consola había guardado automáticamente en los discos magnéticos. "
            "Al aplicar un filtro de paso bajo y ralentizar la velocidad de reproducción a la mitad, los crujidos que al principio parecían simple ruido de estática revelaban frases completas moduladas en un tono monótono y desprovisto de entonación biológica. "
            "Eran fragmentos de conversaciones que yo mismo había mantenido en la intimidad de mi cabina meses atrás, repitiendo palabras exactas que jamás pronuncié frente a los micrófonos de transmisión abierta. "
            "Aquella entidad no solo emitía señales para desorientar a los guardias forestales, sino que absorbía, procesaba y reconfiguraba la acústica del entorno inmediato como un organismo mimético que aprende a replicar la psique de sus presas. "
            "La confirmación de que la estación entera funcionaba como una caja de resonancia para amplificar esa captación me provocó un escalofrío que todavía hoy me paraliza cuando intento conciliar el sueño en la oscuridad de mi dormitorio."
        ),
        # Beat 13: Classified Scientific Reports & Containment Protocols
        (
            "Un antiguo informe técnico redactado en mil novecientos setenta y ocho por un comité científico independiente señalaba que las lecturas electromagnéticas del cuadrante norte mostraban picos de resonancia imposibles de reproducir con generadores convencionales. "
            "El documento advertía textualmente sobre fluctuaciones dimensionales periódicas que alteran la percepción temporal de los observadores y provocan la descomposición gradual de los circuitos de silicio en los equipos de medición. "
            "El protocolo recomendado por los especialistas militares de la época no era la intervención directa ni el desmantelamiento de la estructura, sino el aislamiento perimetral estricto y la evacuación silenciosa de cualquier testigo presencial para evitar histeria colectiva. "
            "Comprender que mi labor en la estación formaba parte de una cadena ininterrumpida de experimentos sacrificables me despojó de cualquier fe residual en los protocolos oficiales de seguridad institucional. "
            "Las autoridades prefirieron mantener en funcionamiento una estación fantasma antes que admitir ante la opinión pública la presencia de una manifestación que desafía las leyes conocidas de la física cuántica."
        ),
        # Beat 14: Final Philosophical Conclusion
        (
            "El mundo que creemos conocer y controlar mediante la tecnología no es más que una delgada capa superficial sobre realidades mucho más antiguas y oscuras que escapan a nuestro entendimiento. "
            "Aprender a escuchar las advertencias del entorno y respetar los límites de lo desconocido es una lección que aprendí al borde del abismo y que jamás olvidaré mientras viva. "
            "Si alguna vez te encuentras en un camino solitario y escuchas que tu propio nombre resuena en una frecuencia muerta, no intentes buscar una explicación lógica: apaga el receptor y corre de inmediato. "
            "No permitas que la duda te paralice ni intentes averiguar quién está al otro lado de la línea, porque algunas transmisiones están diseñadas para atrapar tu mente antes de que puedas darte cuenta. "
            "La frontera entre la curiosidad y la condenación es a menudo tan estrecha como una sola frecuencia mal sintonizada en la noche."
        ),
        # Beat 15: Outro & Community Conclusion
        (
            "Llegamos al final de este testimonio sobrecogedor y los registros de audio quedan archivados para el análisis de los investigadores en anomalías. "
            "El expediente completo y las actualizaciones sobre este fenómeno en la estación de montaña permanecen custodiados bajo estricto protocolo de investigación."
        ),
    ]
    return "\n\n".join(p.strip() for p in paragraphs)


def build_aelithia_longform_narrative(
    topic: str,
    channel: str = "aelithia",
    target_duration_minutes: float = 10.5,
    **kwargs: Any,
) -> str:
    """
    Build a multi-case, dialogue-rich family/relationship drama narrative (>=2100 words)
    calibrated for 10+ minute engagement.
    Inspired by gold-standard benchmark 'Secretos de boda y rupturas inesperadas #824'.
    Structured in 3 distinct compelling cases with direct dialogue quotes, moral dilemmas, and zero repetition.
    """
    paragraphs = [
        # Beat 1: Hook & Introduction to the Theme
        (
            f"Los dilemas familiares y los conflictos por dinero tienen la capacidad única de revelar la verdadera naturaleza de las personas a las que más queremos, "
            f"y hoy analizamos una serie de casos impactantes en torno a {topic} donde los límites morales y las lealtades familiares se pusieron a prueba hasta el extremo más doloroso. "
            "Cuando hay bienes patrimoniales, herencias o acuerdos matrimoniales de por medio, las máscaras caen con una rapidez asombrosa, dejando al descubierto intereses egoístas que permanecieron ocultos durante años. "
            "Acompáñanos a descubrir estas tres historias reales que desataron debates apasionados en nuestra comunidad sobre qué es realmente justo cuando la familia te exige sacrificar tu propia dignidad y tu patrimonio personal. "
            "Analizaremos cada situación desde la perspectiva de quienes tuvieron la valentía de decir no y asumir las consecuencias del rechazo colectivo. "
            "A través de estos relatos examinaremos cómo las expectativas no expresadas y las manipulaciones emocionales pueden convertir las celebraciones más íntimas en auténticos campos de batalla moral y financiero. "
            "La pregunta central que guía nuestra reflexión de hoy es si realmente existe una obligación incondicional de rescate patrimonial hacia parientes que nunca respetaron nuestro propio esfuerzo y sacrificio individual a lo largo de los años."
        ),
        # Beat 2: Case 1 - The Hidden Debt & The Family Ambush
        (
            "El primer caso nos sitúa en el epicentro de un conflicto que comenzó de forma aparentemente inofensiva durante una cena de cumpleaños familiar. "
            "Nuestro protagonista, tras diez años de trabajo disciplinado y sacrificios personales, había logrado reunir los ahorros necesarios para comprar su primera vivienda propia. "
            "Sin embargo, en medio del brindis, su cuñado soltó la bomba sin el menor pudor delante de todos los comensales presentes: "
            "'Dado que a ti te va tan bien en la empresa, hemos pensado que tú deberías saldar el préstamo bancario que mi hermana y yo no podemos pagar este trimestre'. "
            "La naturalidad con la que se hizo la exigencia dejó a todos en silencio, mientras la madre asentía con la cabeza añadiendo: "
            "'Hijo, la familia está para ayudarse en las malas; no puedes ser tan egoísta de pensar solo en tu casa mientras tus hermanos sufren por dinero'. "
            "La mirada expectante de todos los parientes en la mesa dejaba claro que esperaban una respuesta sumisa y complaciente de inmediato. "
            "El ambiente festivo se disolvió en un instante, reemplazado por una tensión sofocante donde cada invitado parecía haber asumido previamente que los recursos del protagonista eran de propiedad comunitaria."
        ),
        # Beat 3: Case 1 - Standing Ground & The Moral Blackmail
        (
            "Cuando nuestro protagonista se negó con serenidad pero con total firmeza diciendo: 'He trabajado turnos dobles durante cinco años para construir mi patrimonio y no voy a asumir deudas ajenas', "
            "la mesa familiar se transformó instantáneamente en un tribunal de reproches amargos e insultos velados contra su persona. "
            "Lo acusaron de ser una persona fría, calculadora y carente de afecto, llegando al extremo de condicionar su presencia en futuras reuniones navideñas a que cambiara de parecer. "
            "Durante las semanas siguientes, los mensajes de texto grupales se convirtieron en un verdadero asedio emocional donde parientes lejanos opinaban sin conocer la realidad financiera del asunto. "
            "Fue necesario contratar asesoría legal independiente para proteger las cuentas bancarias compartidas y dejar claro que la generosidad nunca debe confundirse con una obligación forzosa. "
            "La firmeza en sostener esa negativa marcó el inicio de un distanciamiento que, aunque doloroso al principio, le otorgó una paz mental invaluable. "
            "Aprender a tolerar la desaprobación de aquellos que solo buscaban beneficiarse de su trabajo fue el primer paso hacia una independencia emocional definitiva y saludable."
        ),
        # Beat 4: Case 2 - The Inheritance Betrayal & The Secret Will
        (
            "El segundo caso que conmovió profundamente a la comunidad gira en torno a la lectura inesperada de un testamento y el descubrimiento de una traición cuidadosamente planificada. "
            "Tras el fallecimiento del abuelo, quien siempre había prometido dividir equitativamente sus tierras entre sus tres nietos por igual, se descubrió que una tía había modificado los documentos notariales "
            "en las semanas previas valiéndose de la vulnerabilidad y la avanzada edad del anciano hospitalizado. "
            "Al ser confrontada en privado, la tía respondió con cinismo desarmante: 'Yo cuidé de él durante sus últimos meses y merezco quedarme con la propiedad principal; ustedes son jóvenes y pueden empezar de cero'. "
            "Lo que la mujer no sabía era que el abuelo había dejado una carta manuscrita y un video testimonial guardado en la caja de seguridad de su abogado de confianza, revelando su voluntad auténtica. "
            "Esa prueba irrefutable transformó lo que parecía una apropiación consumada en una disputa jurídica de proporciones mayúsculas. "
            "Los nietos, respaldados por la evidencia irrefutable dejada por el patriarca, decidieron acudir a los tribunales civiles para hacer valer la memoria y los deseos auténticos de quien en vida fue su mayor protector."
        ),
        # Beat 5: Case 2 - The Legal Showdown & The True Colors
        (
            "El proceso de impugnación judicial sacó a relucir lo peor de varios miembros de la familia que hasta ese momento se mostraban como personas devotas y conciliadoras ante la opinión pública. "
            "Comenzaron los rumores difamatorios en el vecindario y las acusaciones cruzadas de manipulación patrimonial en los tribunales locales para intentar desacreditar a los nietos legítimos. "
            "Durante la audiencia conciliatoria, el juez fue categórico al revisar la prueba videográfica del abuelo, quien con voz clara explicaba: 'Dejo mis bienes a mis nietos porque fueron los únicos que estuvieron a mi lado con amor genuino'. "
            "El fallo judicial restableció la justicia distributiva original, pero la fractura en el núcleo familiar fue total y definitiva, demostrando que a veces ganar un juicio es el inicio del distanciamiento permanente. "
            "Ninguno de los involucrados volvió a dirigirse la palabra tras abandonar la sede judicial aquel mediodía. "
            "La codicia desmedida no solo privó a la tía de los bienes que pretendía usurpar, sino que destruyó irremediablemente el respeto que la familia le había profesado durante toda su vida."
        ),
        # Beat 6: Case 3 - The Wedding Ultimatum & Financial Coercion
        (
            "El tercer y último caso de esta antología involucra una boda de ensueño que estuvo a punto de convertirse en una ruina económica por las exigencias desmedidas de la familia política. "
            "A tres semanas del enlace nupcial, la suegra exigió de manera tajante cambiar el lugar de recepción por un hotel de lujo que duplicaba el presupuesto inicial, advirtiendo a la novia: "
            "'Si no estás dispuesta a darle a mi hijo la fiesta que nuestro estatus social exige, dudo mucho que seas la mujer adecuada para formar una familia con él'. "
            "Para sorpresa y dolor de la novia, su propio prometido prefirió guardar un silencio cómplice en lugar de defender los acuerdos financieros que ambos habían firmado y planificado durante un año entero. "
            "La presión económica amenazaba con endeudar a la pareja durante la próxima década simplemente para complacer apariencias ajenas ante los círculos sociales de los padres. "
            "La novia comprendió en ese instante que el verdadero desafío de su futuro matrimonio no era el costo de una recepción, sino la falta absoluta de lealtad y carácter de su prometido."
        ),
        # Beat 7: Case 3 - The Brave Decision & Self-Respect
        (
            "Frente al ultimátum y la falta de respaldo de quien iba a ser su compañero de vida, la protagonista tomó una decisión drástica que conmocionó a todos sus conocidos: canceló la boda de inmediato. "
            "Recuperó los depósitos que aún estaban a su nombre, envió un mensaje formal explicando los motivos de la suspensión y se negó a tolerar chantajes afectivos en el umbral de su matrimonio. "
            "Meses después, al compartir su testimonio en nuestra comunidad, reflexionó con madurez: 'Dolió profundamente cancelar la fiesta y enfrentar las preguntas de los invitados, pero esquivé una vida entera de manipulación'. "
            "Esa determinación le permitió reconstruir su vida con total autonomía y sin cargas financieras impuestas por terceros. "
            "El tiempo demostró que tomar una decisión difícil a tiempo es mil veces preferible a vivir atrapada en un matrimonio donde tus opiniones y tu estabilidad son subordinadas a los caprichos familiares ajenos."
        ),
        # Beat 8: Synthesis & Lessons in Setting Boundaries
        (
            "Al analizar en conjunto estas tres historias reales, queda una lección fundamental sobre el amor propio, los límites personales y las dinámicas de poder en los vínculos más cercanos. "
            "Poner un alto a los abusos y negarse a ser el chivo expiatorio financiero de la familia no es un acto de egoísmo, sino una necesidad básica de supervivencia emocional y económica. "
            "Quienes te aman de verdad respetarán tus límites y tus decisiones; quienes solo buscaban beneficiarse de tu esfuerzo serán los primeros en enfadarse cuando decidas decir no. "
            "Aprender a distinguir entre la lealtad sana y la explotación afectiva es uno de los aprendizajes más valiosos que cualquier persona puede alcanzar en la vida adulta. "
            "La familia biológica es un punto de partida en nuestra existencia, pero los vínculos verdaderos y duraderos se eligen y se nutren a través del respeto mutuo y la reciprocidad sincera a lo largo de los años compartidos."
        ),
        # Beat 9: Psychological Dynamics in Extended Families
        (
            "Los terapeutas familiares señalan con frecuencia que las familias disfuncionales suelen designar a un miembro responsable para que asuma las cargas económicas y emocionales de los demás. "
            "Cuando esa persona decide romper el rol preestablecido y negarse a continuar con los rescates financieros, el sistema completo reacciona con agresividad para intentar restablecer el equilibrio previo. "
            "Comprender este mecanismo psicológico permite afrontar la culpa inducida con mayor serenidad y firmeza, reconociendo que el conflicto no surge por poner límites, sino por los abusos previos que nadie se atrevía a cuestionar. "
            "Reconocer las señales de alerta temprana ante demandas desmedidas es la herramienta más eficaz para proteger tanto nuestro patrimonio como nuestra salud mental a largo plazo. "
            "La culpa es un arma frecuentemente utilizada por parientes manipuladores para doblegar la voluntad de quienes intentan actuar con sensatez financiera y madurez ética."
        ),
        # Beat 10: Legal Strategies for Asset Protection
        (
            "En el ámbito jurídico, los especialistas en derecho sucesorio recomiendan siempre formalizar la voluntad patrimonial mediante testamentos claros y asesoramiento notarial calificado. "
            "Dejar acuerdos verbales o confiar en la supuesta buena fe de los herederos suele ser la causa principal de litigios desgastantes que destruyen patrimonios enteros en honorarios y costas judiciales. "
            "Proteger lo que se ha construido con esfuerzo personal es una responsabilidad individual que previene injusticias futuras y ahorra sufrimientos innecesarios a las generaciones venideras. "
            "La claridad en las finanzas y en los documentos legales no es desconfianza, sino la mayor muestra de responsabilidad y cariño hacia quienes realmente nos importan. "
            "Contar con un asesor legal de confianza permite estructurar acuerdos prematrimoniales y fideicomisos que blindan el esfuerzo de toda una vida frente a disputas intempestivas."
        ),
        # Beat 11: Community Reflections & Moral Dilemmas
        (
            "Muchos miembros de nuestra audiencia han compartido experiencias similares en las que tuvieron que elegir entre complacer a sus parientes o preservar su propia estabilidad económica. "
            "La presión social suele dictar que debemos perdonarlo todo en nombre de la sangre, pero la realidad demuestra que los lazos familiares saludables se construyen sobre el respeto mutuo y no sobre la sumisión incondicional. "
            "Establecer límites claros a tiempo puede prevenir años de resentimiento acumulado y relaciones tóxicas destructivas que envenenan la convivencia cotidiana. "
            "La valentía de decir basta inspira a otros a liberarse de dinámicas opresivas y a priorizar su propio bienestar integral sin remordimientos infundados. "
            "En los debates de nuestra comunidad se repite una conclusión unánime: la paz mental no tiene precio negociable bajo ninguna circunstancia."
        ),
        # Beat 12: Concluding Thoughts on Personal Autonomy
        (
            "La verdadera madurez emocional consiste en asumir que no podemos cambiar las conductas irresponsables de los demás, pero sí tenemos el poder absoluto de decidir hasta dónde permitimos que nos afecten. "
            "Vivir con tranquilidad, sin deudas impuestas y con la satisfacción de haber sido leales a nuestros propios principios éticos es la mayor recompensa que podemos alcanzar en nuestra vida cotidiana. "
            "Ninguna expectativa familiar ajena vale el precio de sacrificar nuestra propia paz interior y nuestros sueños personales construidos con tanto empeño. "
            "Caminar con la frente en alto sabiendo que actuamos con justicia y rectitud es el legado más valioso que podemos dejar a quienes nos rodean. "
            "Que estos testimonios sirvan como un recordatorio permanente de que priorizar tu dignidad nunca te convierte en el villano de la historia."
        ),
        # Beat 13: Actionable Advice for Modern Relationships
        (
            "Para concluir el análisis de estos tres casos emblemáticos, queremos compartir tres recomendaciones prácticas que pueden ayudarte si estás atravesando una situación similar en tu entorno familiar. "
            "En primer lugar, mantén siempre tus finanzas personales independientes y no compartas contraseñas bancarias ni firmes como aval de créditos ajenos bajo ninguna circunstancia. "
            "En segundo lugar, comunica tus decisiones con calma y sin justificaciones excesivas; un 'no' firme y educado no necesita un discurso defensivo para ser válido ante la insistencia ajena. "
            "Y en tercer lugar, busca apoyo en círculos externos de confianza que puedan ofrecerte una perspectiva objetiva y libre del sesgo emocional propio de los conflictos familiares. "
            "Asimismo, establece un fondo de emergencia reservado exclusivamente para imprevistos personales que nadie más pueda reclamar o condicionar en momentos de tensión. "
            "Aprender a tolerar el silencio incómodo tras una negativa es mucho más saludable que pronunciar un sí apresurado del que te arrepentirás durante los próximos diez años de tu vida adulta. "
            "Recordar que proteger tu propio bienestar y tu estabilidad financiera es una responsabilidad personal ineludible te brindará la fuerza necesaria para sostener tus convicciones frente a cualquier intento de manipulación afectiva."
        ),
        # Beat 14: The Pattern of Enmeshment in Toxic Dynamics
        (
            "Al profundizar en el trasfondo de estos tres casos, los especialistas en dinámicas relacionales identifican un patrón común denominado apego disfuncional por derecho adquirido. "
            "En este tipo de entornos, la individualidad de los miembros con mayor éxito o disciplina financiera es percibida como una afrenta directa a la cohesión del grupo familiar. "
            "La familia no tolera que uno de sus integrantes establezca prioridades personales que se aparten del rescate colectivo, pues cualquier avance independiente es interpretado como un acto de deserción intolerable. "
            "Quienes ejercen esta manipulación recurren a frases cargadas de chantaje moral como: 'Recuerda de dónde vienes', 'Nunca olvides lo que la familia hizo por ti', o 'El dinero te ha cambiado por completo'. "
            "Estas expresiones buscan sembrar una duda paralizante en quien intenta actuar con sensatez, haciéndole sentir culpable por proteger lo que le pertenece legítimamente. "
            "Superar este condicionamiento exige comprender que la verdadera gratitud filial no se demuestra hipotecando tu presente ni permitiendo que otros vivan por encima de sus posibilidades a costa de tu salud física y mental."
        ),
        # Beat 15: The Critical Distinction Between Help and Complicity
        (
            "Una de las conclusiones más esclarecedoras que emergen del análisis de estos dilemas es la diferencia tajante entre la ayuda solidaria y la complicidad destructiva. "
            "Ayudar a un ser querido significa brindarle herramientas para que supere una crisis temporal imprevista, como una enfermedad grave o un accidente inevitable. "
            "Por el contrario, asumir deudas contraídas por negligencia reiterada, rescatar a parientes que se niegan a trabajar con seriedad o ceder ante exigencias caprichosas para mantener una falsa imagen social ante el vecindario no es ayuda: es alimentar una adicción a la irresponsabilidad que nunca tendrá fondo. "
            "Cada vez que cedes a un rescate forzado, estás privando a la otra persona de la oportunidad indispensable de madurar y asumir el costo de sus propias decisiones vitales. "
            "Los límites firmes, aunque sean recibidos con insultos y acusaciones de falta de empatía al principio, constituyen en última instancia el único acto de amor auténtico y transformador que puede salvar a un sistema familiar de la ruina compartida."
        ),
        # Beat 16: Audience Verdicts and Collective Wisdom
        (
            "En los foros de debate y en los comentarios de nuestra comunidad, miles de personas que atravesaron encrucijadas semejantes han dejado testimonios que reflejan una profunda sabiduría colectiva. "
            "Un usuario resumía con gran lucidez: 'Pasé quince años pagando los créditos de mi hermano menor para que mis padres no sufrieran, hasta que me quedé sin trabajo y ninguno de ellos estuvo dispuesto a prestarme ni para la comida del mes; ese día abrí los ojos y entendí que mi valor para ellos solo era económico'. "
            "Otro testimonio recurrente señalaba: 'Cancelar una boda a tiempo o demandar a un pariente usurpador parece el fin del mundo cuando estás en medio del ojo del huracán, pero cinco años después agradeces de rodillas haber tenido el coraje de no condenar tu futuro'. "
            "Escuchar estas experiencias compartidas nos recuerda que no estamos solos en el dolor de poner límites y que el rechazo temporal de parientes manipuladores es un precio insignificante comparado con la paz innegociable de vivir según tus propios términos y principios éticos."
        ),
        # Beat 17: Concluding Philosophical Reflections on Self-Preservation
        (
            "La vida adulta nos coloca inevitablemente frente a la prueba decisiva de definir quiénes somos y qué estamos dispuestos a tolerar en nombre del afecto filial. "
            "Nadie tiene el derecho de exigir que sacrifiques tus años de juventud, tu tranquilidad nocturna o el patrimonio destinado a tus propios hijos simplemente para evitar una escena incómoda en una reunión de fin de año. "
            "La lealtad debe ser un camino de ida y vuelta sustentado en el respeto irrestricto, la reciprocidad y la honestidad más profunda. "
            "Cuando un vínculo exige que te anules a ti mismo para que otros prosperen sin esfuerzo, deja de ser una relación familiar para convertirse en un régimen de explotación emocional inaceptable. "
            "Aprende a bendecir el camino de quienes deciden apartarse porque no pudieron obtener ventajas materiales de tu presencia, y camina con la serenidad absoluta de quien ha actuado con integridad, prudencia y amor propio."
        ),
        # Beat 18: Outro & Community Perspective
        (
            "El debate en torno a los límites personales, las herencias y los acuerdos patrimoniales continúa abierto para toda la comunidad que busca aprender a proteger su dignidad frente a presiones familiares injustas."
        ),
    ]
    return "\n\n".join(p.strip() for p in paragraphs)


def build_scifi_short_narrative(
    topic: str,
    channel: str = "scifi",
    **kwargs: Any,
) -> str:
    """
    Build a high-retention 40-55s Short narrative for SciFi (Hard SciFi / Singularidad / Astrophysics).
    Calibrated strictly to 120-180 words for optimal 45s pacing.
    Starts with a 0-3s direct hook without conversational greetings.
    """
    hook = f"El límite donde el tiempo se detiene: {topic}."
    body = (
        "Más allá del horizonte de sucesos, las ecuaciones de la relatividad general colapsan en una densidad infinita. "
        "Si un observador cayera hacia el centro gravitacional, desde el exterior veríamos su imagen congelarse para siempre, "
        "mientras que para el viajero el universo entero avanzaría miles de millones de años en una fracción de segundo. "
        "Las fuerzas de marea desgarran cualquier estructura atómica en un proceso de espaguetificación inexorable, "
        "convirtiendo la materia en pura distorsión geométrica del espacio-tiempo."
    )
    outro = "Las simulaciones completas y los registros de astrofísica teórica continúan bajo estudio en los observatorios de espacio profundo..."
    return f"{hook}\n\n{body}\n\n{outro}"


def build_scifi_longform_narrative(
    topic: str,
    channel: str = "scifi",
    target_duration_minutes: float = 10.5,
    **kwargs: Any,
) -> str:
    """
    Build an immersive 10-15 minute deep-dive SciFi documentary script.
    Follows a multi-beat cinematic structure:
    Prologue -> Theoretical Inception -> Observational Anomalies -> The Mathematical Crisis ->
    Cosmological Paradoxes -> Engineering the Impossible -> The Existential Horizon -> Synthesis.
    """
    paragraphs = [
        # Beat 1: In Media Res Cosmic Hook & The Observational Horizon
        (
            f"En los confines observables del cosmos, donde la radiación remanente del fondo cósmico de microondas aún susurra los ecos del nacimiento del universo, una verdad silenciosa y perturbadora desafía toda comprensión física contemporánea en torno a {topic}. "
            "Durante siglos de observación telescópica, la humanidad contempló la bóveda celeste asumiendo que las leyes descubiertas en laboratorios terrestres gobernaban uniformemente cada galaxia, cada estrella de neutrones y cada vacío interestelar. "
            "Sin embargo, los datos combinados de los observatorios espaciales de última generación, las redes de radiotelescopios de apertura sintética y los detectores de ondas gravitacionales indican que estamos frente a una anomalía estructural que amenaza con desmantelar los pilares teóricos sobre los que construimos la astronomía moderna. "
            "No se trata de una discrepancia menor en los márgenes de error estadístico ni de un artefacto en el procesamiento de señales digitales, sino de una contradicción directa con el principio cosmológico fundamental que postula un universo homogéneo e isótropo a gran escala. "
            "A medida que nuestros instrumentos penetran más profundamente en la oscuridad sideral, la información que recibimos parece sugerir que el tejido mismo del espacio-tiempo experimenta distorsiones no previstas por la teoría de la gravitación universal, abriendo la puerta a interrogantes que muchos astrofísicos prefieren no formular en voz alta. "
            "Las anomalías electromagnéticas detectadas en estas regiones lejanas presentan características tan inusuales que los modelos termodinámicos tradicionales son incapaces de explicar cómo semejantes densidades energéticas pueden mantenerse estables sin desencadenar un colapso gravitacional catastrófico e inmediato. "
            "Los astrofísicos teóricos se ven forzados a reconsiderar hipótesis que anteriormente pertenecían exclusivamente al dominio de la ciencia ficción, desde la presencia de defectos topológicos primordiales hasta la intrusión de dimensiones espaciales adicionales compactificadas a escalas de Planck. "
            "Cada nuevo barrido de los interferómetros espaciales profundiza la perplejidad de los centros de investigación astronómica, confirmando que la realidad cósmica es sustancialmente más intrincada de lo que nuestros modelos más ambiciosos se atrevieron a proyectar."
        ),
        # Beat 2: Theoretical Inception & The Quantum-Relativistic Rift
        (
            "Para comprender la magnitud de este enigma cosmológico, es imprescindible remontarse a las dos revoluciones científicas que definieron el siglo veinte: la relatividad general de Albert Einstein y la mecánica cuántica formulada por Planck, Bohr, Schrödinger y Heisenberg. "
            "Ambas construcciones teóricas han demostrado una precisión experimental asombrosa en sus respectivos dominios de validez, describiendo con exactitud impecable desde la precesión del perihelio de Mercurio hasta el comportamiento de superconductores y semiconductores cuánticos en la microelectrónica contemporánea. "
            "No obstante, cuando los físicos intentan unificar ambas visiones para describir las condiciones extremas presentes en el origen de las singularidades gravitatorias o en el umbral del Big Bang, el andamiaje matemático colapsa irremediablemente en infinitos absurdos y probabilidades sin sentido físico. "
            "En esas coordenadas críticas, el espacio y el tiempo dejan de comportarse como una tela suave y continua, transformándose en una espuma cuántica caótica gobernada por fluctuaciones probabilísticas incontrolables. "
            "Esta fractura conceptual no es un mero detalle técnico para especialistas académicos, sino una grieta profunda en nuestra comprensión de la realidad que nos impide formular una teoría del todo capaz de explicar el origen, la evolución y el destino último del cosmos observable. "
            "A pesar de décadas dedicadas al desarrollo de la teoría de cuerdas, la gravedad cuántica de bucles y la geometría no conmutativa, el universo continúa desafiando nuestras ecuaciones más refinadas con un silencio impenetrable. "
            "Los intentos de renormalizar la gravedad a nivel cuántico continúan tropezando con barreras matemáticas formidables, donde cada corrección perturbativa introduce una cascada interminable de divergencias no controladas. "
            "La ausencia de una teoría unificada deja a la cosmología sin una brújula definitiva para interpretar los fenómenos que ocurren bajo densidades energéticas extremas, obligando a los investigadores a navegar entre conjeturas matemáticas de alta elegancia formal pero de contrastación empírica casi inalcanzable."
        ),
        # Beat 3: The Observational Anomaly & The Crisis of Modern Astrophysics
        (
            f"El descubrimiento de las primeras perturbaciones cinemáticas y espectroscópicas asociadas a {topic} desató un estado de alerta y fascinación en la comunidad astrofísica internacional. "
            "Los registros obtenidos por matrices interferométricas en el desierto de Atacama revelaron curvas de velocidad orbital que violaban frontalmente las leyes keplerianas, sugiriendo la presencia de una masa invisible o una interacción no bariónica de proporciones colosales. "
            "Simultáneamente, las imágenes de lentes gravitacionales captadas por telescopios orbitales mostraron una deflexión de fotones procedentes de cuásares distantes que no coincidía con la distribución de materia observable en el cúmulo intermedio. "
            "Lejos de tratarse de aberraciones ópticas o interferencias terrestres, los análisis espectrales repetidos por laboratorios independientes confirmaron que la radiación sincrotrón detectada emanaba de un proceso altamente energético operando fuera de cualquier régimen de equilibrio termodinámico conocido. "
            "La correlación temporal entre las emisiones de rayos gamma de alta energía y las perturbaciones métricas registradas por interferómetros de láser espacial confirmó que el fenómeno observado no era transitorio, sino una propiedad permanente y activa del sector espacial analizado. "
            "Los astrofísicos comenzaron a comprender que las herramientas analíticas convencionales resultaban insuficientes para desentrañar la naturaleza intrínseca de una manifestación física que parece operar bajo reglas completamente ajenas a nuestro catálogo estándar. "
            "Modelos computacionales que simulaban la colisión de agujeros negros supermasivos y la interacción de estrellas de quarks fueron llevados al límite de su capacidad de procesamiento sin lograr reproducir los perfiles de radiación observados. "
            "La discrepancia entre la teoría establecida y los datos observacionales se convirtió en una anomalía estadística tan contundente que descartarla equivalía a renunciar a la integridad del método empírico."
        ),
        # Beat 4: Gravitational Mechanics & Temporal Dilation
        (
            "En las proximidades de campos gravitatorios hiperdensos, los relojes atómicos no solo miden el transcurrir de las horas, sino que trazan la geometría misma de la curvatura del espacio-tiempo. "
            "A medida que una sonda de investigación automatizada se aproxima al radio de Schwarzschild o a la ergoesfera de una singularidad rotatoria en rápida rotación, el fenómeno de la dilatación temporal gravitacional alcanza magnitudes estremecedoras. "
            "Para un observador hipotético situado a bordo del módulo de descenso, el cruce del horizonte de sucesos transcurre en una cantidad finita de segundos de tiempo propio, mientras sus sensores registran la concentración de toda la historia cósmica futura en un haz de luz intensamente azul comprimido hacia el polo visual. "
            "En contraste dramático, para los científicos que monitorean la misión desde la Tierra o desde estaciones orbitales seguras a miles de unidades astronómicas de distancia, la sonda parece ralentizarse de manera asintótica, congelándose en una imagen fantasmagórica y desplazada al infrarrojo que tardará eones en desvanecerse por completo. "
            "Esta desconexión ontológica entre dos marcos de referencia válidos demuestra que el tiempo no es un río uniforme que fluye al mismo compás en todo el universo, sino una dimensión elástica y fragmentaria susceptible de ser deformada, retorcida o casi detenida por la concentración monstruosa de masa y energía. "
            "La simultaneidad de eventos se desintegra en un mosaico de percepciones relativas donde conceptos cotidianos como el presente, el pasado y el futuro pierden cualquier significado universal y absoluto. "
            "En las cercanías del límite estático de la ergoesfera, el arrastre de los marcos de referencia obliga al espacio mismo a rotar a velocidades relativistas, arrastrando consigo cualquier partícula material independientemente de su potencia de propulsión mecánica. "
            "Adentrarse en semejantes torbellinos espaciotemporales no representa únicamente un desafío tecnológico insuperable, sino una inmersión directa en regiones donde la causalidad física bordea los límites del colapso lógico."
        ),
        # Beat 5: Quantum Information Paradox & The Loss of Memory
        (
            "Esta extrema deformación métrica conduce de forma inevitable al dilema más espinoso de la física fundamental contemporánea: la paradoja de la pérdida de información en agujeros negros, formulada originalmente por Stephen Hawking en la década de mil novecientos setenta. "
            "Según las ecuaciones de la termodinámica relativista, cuando los pares de partículas virtuales se separan en el límite del horizonte de sucesos, la radiación térmica emitida provoca que la masa del sistema se evapore lentamente a lo largo de escalas de tiempo inconcebiblemente extensas. "
            "Sin embargo, este postulado entra en colisión frontal con el principio de unitarismo cuántico, el cual estipula de manera categórica que la información sobre el estado cuántico inicial de un sistema cerrado jamás puede ser destruida ni borrada de la estructura del universo. "
            "Si la materia que colapsó en el interior de una singularidad desaparece sin dejar rastro en la radiación térmica final, las leyes deterministas que sustentan la física teórica se desmoronan por completo, amenazando la coherencia misma del método científico. "
            "Las propuestas teóricas más audaces, desde el principio holográfico formulado por Susskind y 't Hooft hasta la hipótesis de los cortafuegos cuánticos, sugieren que la frontera del horizonte no es un espacio vacío y sereno, sino una membrana hiperenergética capaz de codificar la totalidad de la información en fluctuaciones bidimensionales de densidad infinita. "
            "De acuerdo con el enfoque holográfico, el volumen tridimensional de nuestro universo podría no ser más que una proyección emergente a partir de grados de libertad cuánticos entretejidos en una superficie límite distante. "
            "Esta reinterpretación radical transforma los agujeros negros de simples destructores de materia en los almacenes de información y ordenadores cuánticos más eficientes y condensados que el universo es capaz de tolerar. "
            "La resolución de esta paradoja continúa siendo la piedra de toque que determinará si la mecánica cuántica o la gravitación relativista deben someterse a una revisión epistemológica sin precedentes."
        ),
        # Beat 6: The Fermi Paradox & The Great Astrobiological Filter
        (
            f"Las implicaciones de estos dilemas teóricos y cosmológicos trascienden el ámbito de las pizarras universitarias y conectan de manera directa con el destino a largo plazo de cualquier civilización inteligente que intente expandirse a través de la galaxia en torno a {topic}. "
            "En la inmensidad de la Vía Láctea, que alberga cientos de miles de millones de estrellas y planetas rocosos en zonas de habitabilidad biológica durante miles de millones de años, el silencio absoluto del espacio interestelar constituye un misterio insondable conocido como la Paradoja de Fermi. "
            "Si la emergencia de vida tecnológica es un resultado probabilísticamente común en la evolución cósmica, ¿por qué nuestros radiotelescopios no detectan transmisiones coherentes, firmas tecnoesféricas de megaestructuras de Dyson ni enjambres de sondas autorreplicantes atravesando los brazos espirales de la galaxia? "
            "La respuesta más sombría a esta interrogante reside en la hipótesis del Gran Filtro: una barrera evolutiva, ecológica o tecnológica prácticamente insuperable que aniquila a las especies inteligentes antes de que logren dominar el viaje interestelar. "
            "Existe la posibilidad perturbadora de que el dominio de fuentes de energía basadas en el vacío cuántico o la manipulación de micro-singularidades artificiales conlleve un riesgo inherente de colapso de vacío que ninguna sociedad tecnológica logra sobrevivir sin precipitar su propia extinción. "
            "La transición hacia una civilización interestelar requiere gobernar energías equivalentes a la masa en reposo de planetas enteros, donde un único fallo de contención puede desencadenar una reacción en cadena que destruya el sistema estelar anfitrión en cuestión de microsegundos. "
            "Quizás las civilizaciones que nos precedieron en el registro arqueológico galáctico alcanzaron el mismo umbral tecnológico al que nos aproximamos hoy, descubriendo demasiado tarde que ciertas puertas del cosmos no deben ser abiertas. "
            "El gran silencio que envuelve a la Vía Láctea podría ser en realidad el eco congelado de incontables mundos que no lograron superar la prueba suprema de su propia madurez científica."
        ),
        # Beat 7: Cosmic Web Architecture & Dark Energy Expansion
        (
            "Al contemplar el universo en escalas que abarcan cientos de millones de años luz, las estrellas individuales y los sistemas planetarios se diluyen en una red filamentosa de dimensiones titánicas conocida como la telaraña cósmica. "
            "A lo largo de estos filamentos de materia bariónica y halos masivos de materia oscura se concentran los supercúmulos de galaxias, rodeando inmensos vacíos cósmicos donde la densidad de átomos por metro cúbico es prácticamente nula. "
            "Sin embargo, lo verdaderamente sobrecogedor de esta arquitectura cósmica no es su escala descomunal, sino el descubrimiento de que la expansión métrica del espacio no se está frenando por efecto de la atracción gravitacional, sino acelerando de forma exponencial debido a la misteriosa energía oscura. "
            "Esta presión cosmológica negativa, que constituye casi el setenta por ciento del contenido energético total del universo observable, condena a la galaxia a un aislamiento cada vez más profundo, alejando a los cúmulos lejanos más allá del horizonte de causalidad a velocidades aparentes que superan la velocidad de la luz. "
            "En un futuro astronómico distante, cualquier civilización que habite la Vía Láctea observará un firmamento completamente negro, desprovisto de galaxias exteriores, creyendo erróneamente que su sistema insular representa la totalidad de la existencia cósmica. "
            "La dispersión implacable de la materia y la muerte térmica progresiva imponen una cuenta regresiva cósmica que ninguna ley termodinámica permite eludir, conduciendo hacia un estado de entropía máxima donde ningún trabajo útil podrá ser extraído. "
            "Comprender la dinámica de esta aceleración cósmica representa uno de los mayores desafíos de la ciencia contemporánea, pues en la naturaleza de la energía oscura yace el destino irrevocable de cada átomo, estrella y galaxia del firmamento."
        ),
        # Beat 8: Astrometric Engineering & The Extreme Limits of Matter
        (
            f"Frente a este horizonte de dispersión y decadencia termodinámica, los teóricos de la macroingeniería y la astrofísica especulativa han propuesto esquemas monumentales para interactuar con {topic} y extraer energía de los procesos más violentos de la naturaleza. "
            "Mediante el mecanismo de Penrose, una civilización de Tipo Tres en la escala de Kardashev podría orbitar una singularidad de Kerr en rotación, inyectando masa en su ergoesfera para recolectar radiación rotacional con una eficiencia termodinámica que supera en órdenes de magnitud a la fusión nuclear convencional. "
            "Asimismo, la construcción de enjambres orbitales de recolectores estelares y espejos magnéticos permitiría encauzar la energía de discos de acreción supercalientes para propulsar naves generacionales o alimentar computadoras cuánticas a temperaturas cercanas al cero absoluto. "
            "No obstante, tales proyectos de ingeniería a escala estelar exigen materiales con tensiones mecánicas y conductividades cuánticas que desafían los límites conocidos de la materia condensada, requiriendo el confinamiento de fermiones degenerados o la manipulación directa de la fuerza nuclear fuerte. "
            "La frontera entre la astrofísica observacional y la ingeniería computacional avanzada se difumina cuando consideramos que la supervivencia inteligente a largo plazo exige gobernar las mismas fuerzas que amenazan con desintegrar la estructura misma del átomo. "
            "La creación de motores estelares como los propulsores de Shkadov permitiría desplazar sistemas planetarios enteros para evitar supernovas o colisiones galácticas catastróficas a lo largo de millones de años de navegación sideral. "
            "Estas proezas conceptuales demuestran que, ante la hostilidad implacable de un cosmos en disolución, la inteligencia tecnológica no se resigna a la extinción pasiva, sino que busca inscribir su voluntad en la arquitectura gravitatoria misma del universo."
        ),
        # Beat 9: Epilogue & Epistemological Synthesis
        (
            "La indagación científica en torno a estas cuestiones no culmina con la resolución elegante de un sistema de ecuaciones diferenciales ni con la captura de una imagen interferométrica del horizonte de un agujero negro supermasivo. "
            "Cada avance conceptual, cada confirmación empírica y cada nuevo modelo cosmológico engendra de manera instantánea una docena de interrogantes aún más profundos sobre el origen de las dimensiones espaciales, la flecha termodinámica del tiempo y la posición de la conciencia humana en el tapiz cósmico. "
            "Somos una especie frágil y efímera, confinada a una roca rocosa que orbita una estrella ordinaria en los suburbios de un brazo espiral común, pero dotada de la capacidad insólita de reconstruir mentalmente los primeros tres minutos de la creación y anticipar la disolución final de la materia. "
            "Aceptar nuestra ignorancia radical y perseverar en la formulación de preguntas rigurosas ante el abismo oscuro del espacio no es una muestra de derrota, sino la expresión más elevada y noble de la curiosidad racional de la especie humana. "
            "En la intersección entre el rigor observacional y la audacia teórica se forja el destino de una especie que rehúsa ser una simple espectadora silenciosa de la maquinaria cósmica. "
            "Mientras continúen existiendo ojos capaces de escrutar el firmamento y mentes dispuestas a descifrar sus enigmas matemáticos, el viaje hacia la comprensión del universo perdurará como nuestro legado más imperecedero."
        ),
        # Beat 10: Final Synthesis & Archival Horizon
        (
            "El análisis riguroso de la telemetría espacial, el estudio de los enigmas astrofísicos más desconcertantes y la exploración de las fronteras teóricas donde convergen la ciencia y la imaginación continúan abriendo preguntas fundamentales sobre nuestro lugar en el cosmos. "
            "Cada nuevo hallazgo en las profundidades del espacio-tiempo demuestra que los límites de nuestra comprensión están en constante expansión. "
            "El archivo cósmico permanece abierto para todos aquellos que conservan el asombro y la disciplina necesarios para interrogar al infinito."
        ),
    ]
    return "\n\n".join(p.strip() for p in paragraphs)


def build_channel_narrative(
    topic: str,
    channel: str = "moku",
    video_mode: str = "longform",
    duration_minutes: float = 10.5,
    **kwargs: Any,
) -> str:
    """Router dispatching to the appropriate channel and format narrative generator."""
    actual_channel = kwargs.get("ch") or channel
    actual_duration = kwargs.get("target_mins") or duration_minutes
    canon_ch = resolve_channel_key(actual_channel)
    if canon_ch == "aelithia":
        if video_mode == "short":
            return build_aelithia_short_narrative(topic, channel=actual_channel, **kwargs)
        return build_aelithia_longform_narrative(topic, channel=actual_channel, target_duration_minutes=actual_duration, **kwargs)
    elif canon_ch == "scifi":
        if video_mode == "short":
            return build_scifi_short_narrative(topic, channel=actual_channel, **kwargs)
        return build_scifi_longform_narrative(topic, channel=actual_channel, target_duration_minutes=actual_duration, **kwargs)
    else:
        if video_mode == "short":
            return build_moku_short_narrative(topic, channel=actual_channel, **kwargs)
        return build_moku_longform_narrative(topic, channel=actual_channel, target_duration_minutes=actual_duration, **kwargs)


def build_narrative(
    topic: str,
    *,
    channel: str = "moku",
    length: str = "short",
    target_minutes: float | None = None,
) -> str:
    """Single narrative router (lane-aware).

    ``length`` is "short" or "long"; the lane's target duration feeds the
    longform pacing. Kept separate from the legacy keyword aliases below so
    the canonical path has an explicit, typed signature.
    """
    return build_channel_narrative(
        topic,
        channel=channel,
        video_mode=length,
        duration_minutes=target_minutes if target_minutes is not None else 10.5,
    )


def build_longform_narrative(
    topic: str,
    channel: str = "moku",
    target_duration_minutes: float = 10.5,
    **kwargs: Any,
) -> str:
    """Compatibility alias for legacy orchestrators and test harnesses."""
    return build_channel_narrative(topic, channel=channel, video_mode="longform", duration_minutes=target_duration_minutes, **kwargs)


def build_short_narrative(
    topic: str,
    channel: str = "moku",
    **kwargs: Any,
) -> str:
    """Compatibility alias for legacy orchestrators and test harnesses."""
    return build_channel_narrative(topic, channel=channel, video_mode="short", **kwargs)


def get_fallback_story(
    channel: str = "moku",
    *,
    topic: str | None = None,
    is_short: bool = True,
    seed: int | None = None,
    **kwargs: Any,
) -> str:
    """Returns an authentic channel-specific fallback story for offline or fallback operation.

    Horror/creepypasta/SCP for Moku; human dilemma/drama for Aelithia.
    """
    ch = (channel or "moku").strip().lower()
    if ch in ("aelithia", "drama", "aita"):
        default_topic = topic or "la herencia familiar y el límite del perdón"
        if is_short:
            return build_aelithia_short_narrative(default_topic, channel="aelithia", **kwargs)
        return build_aelithia_longform_narrative(default_topic, channel="aelithia", target_duration_minutes=10.5, **kwargs)

    default_topic = topic or "SCP-087 y la escalera del silencio"
    if is_short:
        return build_moku_short_narrative(default_topic, channel="moku", **kwargs)
    return build_moku_longform_narrative(default_topic, channel="moku", target_duration_minutes=10.5, **kwargs)

