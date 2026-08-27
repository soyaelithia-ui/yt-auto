"""
Narrative synthesis templates for YouTube automation pipelines.
Provides channel-isolated narrative builders for Moku (Horror/SCP) and Aelithia (Drama/AITA),
free of vocalized structural headers, with rich first-person immersion, dialogue, and zero mechanical repetition.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from src.branding import get_channel_branding, resolve_channel_key
from src.core.scp_lore import lookup_scp


def build_moku_short_narrative(
    topic: str,
    channel: str = "moku",
    **kwargs: Any,
) -> str:
    """
    Build a high-retention 40-55s Short narrative for Moku (Horror/SCP).
    Calibrated strictly to 120-180 words for optimal 45s pacing.
    Grounded in official canonical lore when an SCP is detected.
    Starts with a 0-3s direct hook without conversational greetings.
    """
    actual_channel = kwargs.get("ch") or channel
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


def build_aelithia_short_narrative(
    topic: str,
    channel: str = "aelithia",
    **kwargs: Any,
) -> str:
    """
    Build a high-retention 35-45s Short narrative for Aelithia (Drama / AITA / Moral Dilemmas).
    Calibrated strictly to 120-180 words for optimal short pacing.
    Starts with a 0-3s direct hook framing the personal conflict.
    """
    actual_channel = kwargs.get("ch") or channel
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
    actual_channel = kwargs.get("ch") or channel
    branding = get_channel_branding(actual_channel)
    ch_handle = branding.handle

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
            "Encontré las libretas amarillentas de un técnico llamado Miller, fechadas a finales de los años ochenta, y lo que leí en sus páginas me heló la sangre por completo. "
            "Miller describía exactamente los mismos patrones acústicos, las mismas coordenadas en la ladera norte y una advertencia manuscrita en letras rojas: 'Si la frecuencia se sincroniza con tu voz, no respondas por radio'. "
            "El registro de Miller se interrumpía abruptamente en la tercera semana de octubre, con una última anotación desordenada que decía: 'Ya sabe mi nombre y está tocando la ventana'. "
            "La caligrafía temblorosa de aquellas últimas líneas reflejaba un pánico idéntico al que en ese preciso momento comenzaba a dominar mis propios pensamientos. "
            "Revisé los registros de personal posteriores a esa fecha y descubrí con horror que la compañía de telecomunicaciones nunca había reportado formalmente la renuncia ni el traslado de Miller. "
            "En su ficha de servicio simplemente figuraba una escueta nota administrativa que catalogaba su ausencia como abandono voluntario de puesto sin entrega de inventario."
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
        # Beat 12: Final Philosophical Conclusion
        (
            "El mundo que creemos conocer y controlar mediante la tecnología no es más que una delgada capa superficial sobre realidades mucho más antiguas y oscuras que escapan a nuestro entendimiento. "
            "Aprender a escuchar las advertencias del entorno y respetar los límites de lo desconocido es una lección que aprendí al borde del abismo y que jamás olvidaré mientras viva. "
            "Si alguna vez te encuentras en un camino solitario y escuchas que tu propio nombre resuena en una frecuencia muerta, no intentes buscar una explicación lógica: apaga el receptor y corre de inmediato. "
            "No permitas que la duda te paralice ni intentes averiguar quién está al otro lado de la línea, porque algunas transmisiones están diseñadas para atrapar tu mente antes de que puedas darte cuenta."
        ),
        # Beat 13: Outro & Community Conclusion
        (
            "Llegamos al final de este testimonio sobrecogedor y los registros de audio quedan archivados para el análisis de los investigadores en anomalías. "
            f"El expediente completo y las actualizaciones sobre este fenómeno en la estación de montaña permanecen custodiados en {ch_handle}."
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
    actual_channel = kwargs.get("ch") or channel
    branding = get_channel_branding(actual_channel)
    ch_handle = branding.handle

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
            "Recordar que proteger tu propio bienestar y tu estabilidad financiera es una responsabilidad personal ineludible te brindará la fuerza necesaria para sostener tus convicciones frente a cualquier intento de manipulación afectiva."
        ),
        # Beat 14: Outro & Community Perspective
        (
            f"El debate en torno a los límites personales, las herencias y los acuerdos patrimoniales continúa abierto para toda la comunidad de reflexiones éticas y relaciones en el espacio de {ch_handle}."
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
