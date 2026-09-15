"""
src/templates/longform_stories.py - Multi-storyline library for longform narratives.
Provides rotating diverse storylines for Moku (Horror) and Aelithia (Drama / AITA)
to ensure zero duplicate similarity collisions (Jaccard < 0.25) across dynamic publications.
"""

from typing import Any, List, Callable
import hashlib


def build_moku_mountain_radio(topic: str, **kwargs: Any) -> str:
    """Story 0: Mountain Radio Station Operator (Existing gold-standard)."""
    from src.templates.narratives import _build_moku_radio_base
    return _build_moku_radio_base(topic, **kwargs)

def build_aelithia_family_debt(topic: str, **kwargs: Any) -> str:
    """Story 0: Birthday Loan & Secret Will (Existing gold-standard)."""
    from src.templates.narratives import _build_aelithia_family_debt_base
    return _build_aelithia_family_debt_base(topic, **kwargs)

def build_moku_bunker(topic: str, **kwargs: Any) -> str:
    paragraphs = [
        (
            f"Bajo quinientos metros de roca granítica impenetrable, el silencio adquiere una textura mineral asfixiante, y hoy revelamos los acontecimientos ocultos de {topic} que jamás debieron ser desenterrados por la ingeniería humana. "
            "Fui contratado como especialista en instrumentación geofísica para monitorear los sensores de esfuerzo tectónico en el complejo subterráneo del Sector Siete, una instalación excavada durante la Guerra Fría bajo el pretexto de estudiar fallas sísmicas profundas. "
            "Las galerías inferiores, reforzadas con vigas de acero pretensado y mamparas hidráulicas de titanio, albergaban sismógrafos láser capaces de registrar vibraciones microscópicas en el lecho rocoso continental. "
            "El aislamiento era absoluto: no existía señal celular, el aire circulaba a través de potentes turbinas de filtrado químico y el único contacto con el exterior era un montacargas industrial que descendía dos veces por semana con suministros básicos. "
            "Durante las primeras semanas de mi guardia solitaria, las lecturas de los galvanómetros se mantuvieron dentro de los rangos basales previstos por los ingenieros geólogos. "
            "Sin embargo, al llegar a mediados de noviembre, los geófonos de pozo comenzaron a registrar un patrón acústico anómalo que emanaba de una profundidad estimada de doce kilómetros bajo el suelo de la bóveda. "
            "No se trataba de micro-fracturas tectónicas ni de la descompresión natural de estratos basálticos. "
            "Era una serie de pulsos rítmicos, sincronizados a intervalos de cuatro segundos exactos, cuya firma espectral imitaba la sístole y diástole de un corazón colosal latiendo en las entrañas de la tierra."
        ),
        (
            "A las dos y cuarenta de la madrugada, los estantes metálicos del laboratorio comenzaron a vibrar con una oscilación casi imperceptible que hacía tintinear los tubos de ensayo de cuarzo. "
            "Descendí por la rampa de concreto hacia el nivel cuatro, donde se encontraban los cabezales de perforación profunda y los pozos de testificación sellados con plomo fundido. "
            "El aire en esa cota era denso, impregnado de un penetrante hedor a azufre y ozono ionizado que me obligó a colocarme la máscara de respiración asistida. "
            "Al alumbrar las paredes de roca viva con la linterna halógena de inspección, noté que las fisuras naturales del granito presentaban un exudado viscoso y translúcido que desafiaba la gravedad, trepando lentamente hacia el techo de la galería. "
            "Acerqué el sensor piezoeléctrico a la roca y el monitor de ondas dibujó una oscilación perfectamente sinusoidal que comenzó a acelerarse progresivamente conforme me aproximaba a la escotilla blindada del pozo principal. "
            "La temperatura ambiental en el túnel descendía abruptamente en lugar de ascender, marcando registros bajo cero en un punto geológico donde el gradiente térmico terrestre debería generar más de cuarenta grados centígrados. "
            "El vaho de mi respiración se congelaba sobre el visor de la máscara mientras un chasquido seco resonaba detrás del muro de contención, como si bloques ciclópeos estuvieran reacomodándose a voluntad."
        ),
        (
            "Frente a la compuerta de acceso al pozo de prospección número tres, descubrí que los remaches de fijación estaban cizallados con cortes limpios que no mostraban marcas de soplete ni de cizalla mecánica. "
            "Alumbré el interior a través de la mirilla de cuarzo blindado y contemplé una cavidad que no figuraba en ninguno de los planos arquitectónicos entregados por la dirección de obras públicas. "
            "El pozo vertical descendía hacia una oscuridad absoluta donde las partículas de polvo en suspensión permanecían totalmente inmóviles, como suspendidas en un gel invisible que anulaba las corrientes de convección del aire. "
            "En el fondo de ese abismo mineral, a una distancia que la potencia de mi linterna apenas lograba perforar, distinguí el reflejo metálico de una estructura cilíndrica cubierta por grabados geométricos ajenos a cualquier alfabeto histórico conocido. "
            "El detector de radioactividad marcaba valores nulos, pero el magnetómetro digital oscilaba descontroladamente de polo norte a polo sur en cuestión de milisegundos. "
            "De pronto, desde el fondo del conducto vertical emergió una ráfaga de aire glacial que traía consigo un murmullo grave, articulado en tonos guturales que resonaron dentro de mi propia caja torácica. "
            "El pánico me hizo retroceder varios pasos mientras el eco metálico se propagaba a lo largo de las tuberías de drenaje como un tren subterráneo aproximándose a gran velocidad."
        ),
        (
            "Me refugié en la sala de mando del nivel superior y me apresuré a revisar los archivadores ignífugos que contenían los registros de excavación de mil novecientos setenta y cuatro. "
            "Oculto tras un doble fondo en la gaveta del ingeniero jefe, encontré un cuaderno manuscrito forrado en tela negra cuyas páginas estaban amarillentas por la humedad y el paso de los años. "
            "Las anotaciones describían cómo el equipo de perforación original había interceptado una cavidad pre-cámbrica a cuatrocientos ochenta metros de profundidad y cómo los obreros comenzaron a sufrir amnesia disociativa y alucinaciones táctiles compartidas. "
            "Una nota garabateada con tinta roja en los márgenes advertía textualmente: 'Aquello que duerme bajo el granito no debe ser alimentado con luz artificial; reacciona a la presencia biológica y busca cerrar las salidas hacia la superficie'. "
            "El diario registraba la muerte súbita de tres geofísicos por colapso cardiovascular idiopático la misma noche en que intentaron dinamitar la cámara subterránea para sellar el pasaje. "
            "Comprendí de inmediato que mi labor técnica en ese búnker no era una misión científica legítima, sino una guardia de sacrificio asignada a un empleado prescindible para comprobar si la anomalía seguía confinada en su lecho de roca. "
            "La administración central había encubierto los incidentes mortales clasificándolos como accidentes laborales causados por desprendimientos de rocas o acumulación de gas grisú."
        ),
        (
            "A las tres y media de la madrugada, los monitores de circuito cerrado que vigilaban los pasillos inferiores comenzaron a parpadear con imágenes distorsionadas por estática electromagnética. "
            "En la pantalla correspondiente a la galería cuatro, pude ver con absoluta claridad cómo una silueta amorfa, más densa que la propia sombra de los túneles, avanzaba deslizándose por el suelo sin generar ruido de fricción. "
            "La criatura o fenómeno parecía absorber la iluminación fluorescente a su paso, apagando las lámparas de emergencia una a una en una secuencia inexorable que se dirigía hacia la escalera central. "
            "El intercomunicador de pared crujió repentinamente y una voz áspera, que reproducía con precisión milimétrica la voz de mi padre fallecido hacía una década, me llamó por mi nombre desde el pasillo de acceso. "
            "'Abre la puerta del laboratorio', decía el altavoz con una serenidad perturbadora que me heló el corazón en el pecho. 'Hace mucho frío aquí abajo y tenemos que terminar la guardia juntos'. "
            "La manija de acero de la puerta hermética comenzó a girar lentamente, forzada desde afuera con una presión que doblaba los pasadores de seguridad de diez centímetros de grosor. "
            "Los vidrios reforzados de la ventana de observación se cuartearon en una telaraña de micro-fracturas mientras el calor de la sala era absorbido en segundos, haciendo que el mercurio del termómetro cayera por debajo de los veinte grados negativos."
        ),
        (
            "No dudé un segundo más: activé la alarma de evacuación de emergencia, tomé la mochila con mis documentos personales y corrí hacia el pozo del montacargas auxiliar en el extremo este del complejo. "
            "Un estruendo ensordecedor sacudió la estructura de hormigón armado cuando la mampara del laboratorio fue arrancada de sus bisagras por un impacto descomunal que proyectó fragmentos de metal incandescente por el corredor. "
            "A través de la polvareda no vi garras ni ojos, sino una masa fluctuante de filamentos oscuros que se retorcían como raíces vivas devorando el cableado eléctrico y las tuberías de agua presurizada. "
            "Arrojé una granada fumígena de fósforo blanco que formaba parte del equipo de emergencia de supervivencia y el estallido de luz brillante provocó un chillido sibilante que hizo temblar las vigas del techo. "
            "Aproveché la contracción temporal de la masa para meterme en la jaula del montacargas y presionar el botón de ascenso manual con desesperación absoluta. "
            "El motor eléctrico gemía bajo el esfuerzo mientras los cables de tracción chirriaban contra las poleas oxidadas, elevándome milímetro a milímetro mientras la penumbra trepaba velozmente por las paredes del hueco del ascensor. "
            "Sentí cómo tentáculos gélidos rozaban la rejilla inferior de la jaula, provocando descargas de electricidad estática que erizaban el vello de mis brazos y hacían sonar chispas en mis botas con punta de acero."
        ),
        (
            "Llegué a la caseta exterior en la superficie cuando el alba despuntaba tímidamente sobre las colinas boscosas, rompiendo la cerradura de la trampilla para emerger al aire puro de la mañana. "
            "El contraste entre el aire gélido de la superficie y la atmósfera enrarecida del subsuelo me provocó un ataque de tos violento que me dejó de rodillas sobre la hierba húmeda de rocío. "
            "Apenas me incorporé, accioné la palanca de corte general de los generadores y detoné las cargas pirotécnicas de seguridad que colapsaban la boca del pozo principal según el protocolo de contingencia extrema. "
            "Un temblor sordo sacudió el terreno bajo mis pies cuando toneladas de grava y roca sellaron la entrada vertical del Sector Siete, levantando una nube densa de polvo calizo que cubrió la vegetación circundante. "
            "Abordé la camioneta de servicio y manejé sin detenerme durante dos horas hasta alcanzar la delegación provincial de seguridad civil para presentar mi informe de evacuación forzosa. "
            "Los funcionarios que me atendieron se mostraron incrédulos al inicio, pero una llamada telefónica urgente desde la capital provincial cambió su actitud de forma inmediata: fui recluido en una sala de interrogatorios durante cuarenta y ocho horas ininterrumpidas. "
            "Agentes gubernamentales confiscaron mi bitácora de campo, borraron las grabaciones de mis dispositivos portátiles y me obligaron a rubricar una declaración jurada donde aceptaba la versión oficial de un colapso geotécnico por bolsa de metano."
        ),
        (
            "Informes técnicos redactados con posterioridad por comisiones periciales secretas confirmaron que la cuenca subterránea presentaba anomalías gravimétricas de escala regional que no podían ser explicadas por yacimientos minerales convencionales. "
            "La densidad de la corteza en el Sector Siete registraba variaciones dinámicas del quince por ciento en ciclos de setenta y dos horas, lo que sugería la existencia de desplazamientos de masa a profundidades litosféricas incompatibles con la física del estado sólido. "
            "Los núcleos de perforación recuperados antes del colapso mostraban cristales de circón con desintegraciones isotópicas que apuntaban a fuentes de calor no nucleares operando en regímenes de entropía negativa. "
            "Ningún modelo geodinámico moderno fue capaz de explicar cómo una estructura cavernosa de semejantes dimensiones podía mantenerse abierta a presiones litostáticas superiores a diez mil atmósferas sin derrumbarse sobre sí misma. "
            "La totalidad del sector montañoso fue declarado reserva biológica estricta con prohibición total de sobrevuelo a baja cota y acceso vedado mediante patrullas permanentes de gendarmería armada. "
            "Los antiguos mapas topográficos fueron retirados de la circulación pública y sustituidos por cartografía corregida que omitía deliberadamente cualquier mención a las instalaciones del Sector Siete."
        ),
        (
            "Con el transcurso de los años logré contactar a un viejo topógrafo que había participado en el trazado inicial de los túneles a principios de la década de mil novecientos setenta. "
            "El anciano me confesó con voz quebrada que durante las obras de voladura profunda los mineros encontraron cavidades prehistóricas cuyas paredes estaban pulidas como espejos de obsidiana, con sarcófagos de piedra encastrados en la roca misma. "
            "Según su testimonio, el personal militar al mando detuvo de inmediato los trabajos civiles y procedió a evacuar a los obreros bajo estrictas amenazas de enjuiciamiento marcial para sustituirlos por destacamentos científicos clasificados. "
            "El topógrafo aseguraba que varios de sus compañeros de cuadrilla desarrollaron tumores cerebrales de evolución fulminante y trastornos conductuales severos en los meses posteriores a su retirada del proyecto. "
            "Las familias de los fallecidos recibieron indemnizaciones estatales vitalicias a condición de mantener un pacto de silencio inquebrantable que impidió cualquier exhumación o autopsia independiente. "
            "La evidencia de que el gobierno conocía la naturaleza biológica de la anomalía antes de iniciar la construcción del búnker confirmó mis peores sospechas sobre la negligencia deliberada con que fui enviado a esa guardia subterránea."
        ),
        (
            "Hoy en día resido en una ciudad costera, a cientos de kilómetros de cualquier formación montañosa, pero la sensación de confinamiento en las profundidades de la tierra jamás me ha abandonado por completo. "
            "El zumbido monótono de los sistemas de aire acondicionado en los edificios de oficinas o el metro subterráneo me devuelve instantáneamente a la penumbra gélida del nivel cuatro. "
            "A menudo me despierto sobresaltado a las dos y cuarenta de la madrugada, creyendo sentir bajo la cama la misma vibración armónica que anunciaba el despertar de la masa en las entrañas de la roca. "
            "La certidumbre de que aquello que encontramos bajo quinientos metros de granito sigue vivo y aguardando pacientemente en la oscuridad es un peso que nubla cada uno de mis momentos de tranquilidad diurna. "
            "Nuestra civilización se enorgullece de dominar la superficie del planeta y enviar satélites a las estrellas, pero ignora con absoluta soberbia los horrores antiguos que habitan a escasos kilómetros bajo nuestros propios cimientos. "
            "Mi memoria conserva intacto cada crujido de aquella noche y sé con certeza que las compuertas de hormigón armado solo representan una tregua temporal frente a lo inevitable."
        ),
        (
            "Documentos desclasificados décadas más tarde en archivos militares extranjeros revelaron la existencia de proyectos gemelos desarrollados en cordilleras de otros continentes durante el mismo período histórico. "
            "En todos los emplazamientos los resultados fueron idénticos: las perforaciones ultra-profundas terminaban interceptando capas de actividad anómala que forzaban el abandono y sellado apresurado de las instalaciones con explosivos termobáricos. "
            "Los informes científicos soviéticos y occidentales coincidían en señalar que la corteza terrestre profunda alberga vestigios de una biosfera no fotosintética que opera bajo leyes físicas que desafían el método empírico contemporáneo. "
            "Estas entidades o campos de fuerza parecen interactuar con la actividad neural de los mamíferos superiores, induciendo cuadros de terror arquetípico y facilitando su propia expansión hacia estratos superficiales. "
            "El hermetismo total con que las grandes potencias han manejado estos hallazgos demuestra que el miedo a una histeria colectiva incontrolable supera con creces cualquier interés por el avance del conocimiento geológico. "
            "Ciertas fronteras subterráneas están trazadas por la propia naturaleza para proteger la cordura de nuestra especie, y violarlas constituye un acto de imprudencia temeraria que la humanidad pagará con creces."
        ),
        (
            "Al analizar los registros espectrográficos que logré salvar en una memoria portátil antes de escapar, descubrí que las frecuencias sonoras captadas en el pozo tres contenían micro-modulaciones fractales de asombrosa complejidad computacional. "
            "Al transformar las oscilaciones sísmicas en señales acústicas audibles mediante algoritmos de transposición tonal, el ruido de fondo se convertía en una secuencia polifónica estructurada que imitaba cánticos litúrgicos arcaicos. "
            "No era el sonido aleatorio del magma desplazándose ni de gases comprimidos liberándose por fisuras, sino un lenguaje matemático formal diseñado para resonar en las cavidades óseas del cráneo humano. "
            "Esta revelación confirmó que lo que encontramos en el Sector Siete no era un simple fenómeno físico desconocido, sino una entidad consciente con la que resulta biológicamente imposible entablar comunicación sin perder la razón. "
            "El terror que me produce pensar que esa conciencia subterránea puede estar extendiendo sus ramificaciones por debajo de las grandes urbes es algo que ningún tratamiento psicológico ha logrado disipar de mis noches solitarias."
        ),
        (
            "Las actas de clausura definitiva del Sector Siete firmadas por el ministerio de defensa en mil novecientos ochenta y nueve ordenaban el vertido de más de veinte mil toneladas de hormigón armado con escoria de plomo en el pozo de ventilación principal. "
            "El texto legal justificaba la medida en base a una supuesta inestabilidad hidrogeológica de los acuíferos profundos que amenazaba la salubridad del suministro de agua potable de la región. "
            "Sin embargo, los planos de ingeniería revelaban la instalación de sensores térmicos y geófonos pasivos conectados permanentemente a un centro de escucha militar situado en una base aérea distante. "
            "A pesar de que oficialmente las instalaciones están abandonadas y tapiadas, las partidas presupuestarias reservadas para el mantenimiento del perímetro de seguridad continúan renovándose año tras año con cargo a fondos reservados de defensa. "
            "Nadie se atreve a admitir públicamente que siguen escuchando, vigilando atentamente la roca para asegurarse de que el corazón de piedra que palpita bajo la montaña no comience a latir con mayor frecuencia."
        ),
        (
            "El universo mineral que yace bajo nuestros pies no es un reino inerte de rocas y minerales destinados a la explotación industrial, sino el territorio soberano de realidades primordiales que reclaman su dominio absoluto. "
            "Los seres humanos somos apenas recién llegados a una delgada corteza superficial que flota precariamente sobre profundidades infinitas y hostiles que jamás lograremos comprender ni domesticar. "
            "Si alguna vez sientes en la tranquilidad de tu hogar una vibración sorda que hace tintinear la vajilla sin que haya noticias de terremotos en los medios de comunicación, apaga las luces y escucha con atención. "
            "Si esa vibración mantiene una cadencia pausada y parece responder al ritmo de tu propia respiración, no intentes buscar una avería en las tuberías ni mires hacia el sótano. "
            "Comprende que hay profundidades a las que la mirada humana nunca debe asomarse y que la supervivencia radica a veces en saber mantenernos alejados de los abismos que la tierra oculta celosamente."
        ),
        (
            "Con estas reflexiones cerramos este testimonio sobre el Sector Siete, dejando constancia de que los expedientes técnicos originales siguen archivados en mi labor testimonial para la memoria colectiva de quienes respetan los enigmas subterráneos. "
            "Las coordenadas del complejo permanecen en el anonimato para evitar que la imprudencia despierte aquello que la roca aún mantiene sepultado en el silencio de los abismos."
        ),
    ]
    return "\n\n".join(p.strip() for p in paragraphs)

def build_moku_lighthouse(topic: str, **kwargs: Any) -> str:
    paragraphs = [
        (
            f"En medio del Atlántico norte, donde las corrientes abisales chocan contra peñascos de basalto negro sin vegetación alguna, el misterio de {topic} se convirtió en la pesadilla más sobrecogedora de toda mi existencia. "
            "Acepté el puesto de farero interino en el islote de Arrecife Negro para cubrir la baja imprevista del titular durante los tres meses de invierno, tentado por el sueldo excepcional que la administración marítima ofrecía para puestos de alto aislamiento oceánico. "
            "La torre de piedra gris, construida a finales del siglo diecinueve sobre una aguja de roca azotada por vientos huracanados, distaba cuarenta millas náuticas de la costa continental más cercana. "
            "Mi único cometido consistía en vigilar el funcionamiento del mecanismo de rotación de la lente Fresnel de mercurio, reponer el combustible diésel de los grupos electrógenos y emitir los boletines meteorológicos horarios a través del canal marino internacional. "
            "Los capitanes de los buques pesqueros que me trasladaron hasta el muelle de atraque me despidieron con miradas elocuentes y una advertencia lacónica: 'No bajes a los rompientes durante la marea muerta de las tres de la mañana y mantén siempre encendida la lámpara principal'. "
            "Al principio atribuí sus palabras a las supersticiones marineras habituales entre hombres que pasan la vida entera navegando en aguas traicioneras y solitarias. "
            "Sin embargo, la primera noche en que una tormenta del suroeste envolvió el arrecife en un torbellino de olas de diez metros, comprendí que la soledad del océano encierra terrores que ningún libro de náutica se atreve a documentar formalmente. "
            "El rugido del oleaje contra los cimientos de sillería hacía temblar la escalera helicoidal de hierro como si la torre estuviera a punto de ser arrancada de cuajo por el embate del mar embravecido."
        ),
        (
            "A las tres y diecisiete de la madrugada, cuando la marea alcanzó su punto más bajo de bajamar viva, el mar se retiró con una violencia inusitada que dejó al descubierto extensiones de lecho marino jamás cartografiadas por los sonares hidrográficos. "
            "Desde la galería de servicio del faro, iluminada por el haz giratorio de luz blanca, contemplé con asombro cómo los arrecifes descubiertos no presentaban algas, percebes ni conchas marinas adheridas a la roca volcánica. "
            "El lecho emergido estaba cubierto por formaciones de cristales negros y translúcidos que crecían en espirales concéntricas, reflejando la luz del faro con tonalidades violáceas y fosforescentes de origen inexplicable. "
            "En medio de la niebla salina, los silbatos de la sirena de niebla instalada en la plataforma baja comenzaron a emitir un tono modulado que no correspondía a la secuencia acústica programada en el temporizador neumático. "
            "El sonido regresaba desde el horizonte oscuro transformado en un lamento polifónico, como si cientos de voces humanas estuvieran respondiendo desde el agua profunda que rodeaba el islote rocoso. "
            "Al enfocar los prismáticos marinos hacia la rompiente exterior, vi que la superficie del agua no presentaba olas convencionales, sino una superficie lisa y aceitosa que se abría en círculos concéntricos alrededor del faro. "
            "El vaho salino entraba por las rendijas de ventilación impregnando el habitáculo con un hedor a sedimentos milenarios y ozono que irritaba los ojos y dificultaba la deglución. "
            "Fue en ese instante cuando la maquinaria del reloj de rotación de la lente Fresnel crujió con un chirrido metálico espantoso y se detuvo bruscamente, dejando el haz de luz congelado apuntando fijamente hacia un punto solitario en el océano negro."
        ),
        (
            "Subí a toda prisa por la escalera de caracol con la caja de herramientas y la lámpara de mano para intentar desbloquear el embrague mecánico del baño de mercurio flotante. "
            "La cámara de la linterna, situada a cuarenta y cinco metros sobre el nivel de los rompientes, estaba inundada por una luz cegadora que proyectaba sombras alargadas contra la cúpula de cobre exterior. "
            "Al examinar los engranajes de bronce del mecanismo de cuerda, descubrí que una película viscosa, similar a limo abisal o mucus biológico, cubría los dientes del piñón principal, impidiendo el avance del contrapeso motor. "
            "Limpié los engranajes con un trapo impregnado de solvente, pero apenas restablecí la tensión del cable, un golpe sordo retumbó contra los cristales blindados de la ventana que miraba hacia el norte marino. "
            "A través del vidrio empapado por la espuma marina vi una extremidad pálida, semejante a una mano alargada con dedos palmados unidos por membranas translúcidas, apoyada sobre la superficie exterior del cristal a cuarenta y cinco metros de altura sobre el mar. "
            "El frío glacial que emanaba de la ventana congeló la condensación interior en cuestión de segundos, dibujando patrones de escarcha que cubrieron por completo la silueta que permanecía suspendida en el aire exterior. "
            "Un gemido gutural resonó a través del conducto de ventilación del faro, haciendo vibrar los tubos de la sirena de niebla con un tono que provocó un dolor punzante en mis tímpanos. "
            "Comprendí con horror que aquello que habitaba en los arrecifes sumergidos no dependía del agua para desplazarse y que la torre de piedra era el objetivo directo de su acecho nocturno."
        ),
        (
            "Bajé corriendo a la sala de guardia en el tercer piso y me encerré atrancando la pesada puerta de roble con una barra de hierro forjado que servía de tranca de seguridad. "
            "Abrí el cajón del escritorio donde los antiguos fareros guardaban el libro de registro oficial y las cartas náuticas históricas de la capitanía del puerto. "
            "Al pasar las páginas amarillentas del diario fechado en mil ochocientos noventa y dos, encontré los informes del farero Archibald MacIntyre, el último operario civil que había residido en el islote antes de que el faro fuera militarizado. "
            "MacIntyre describía con caligrafía temblorosa cómo durante las mareas muertas de invierno las criaturas del arrecife salían de las fosas submarinas buscando las fuentes de luz artificial para alimentarse de su radiación electromagnética. "
            "La última entrada del diario, redactada el tres de febrero de aquel año, decía textualmente: 'El mar se ha vuelto negro como la tinta y están subiendo por los muros de granito; no apagues la lámpara porque en la oscuridad entran en la mente'. "
            "Al lado del texto había un recorte de periódico de la época que informaba sobre el hallazgo del faro completamente desierto por una balandra de aprovisionamiento, con la mesa servida y la puerta de la linterna abierta al viento del norte. "
            "El registro oficial catalogó la desaparición de los tres operarios de guardia como un accidente por golpe de mar durante tareas de mantenimiento en el muelle exterior, silenciando cualquier investigación criminal. "
            "Comprendí que la administración conocía perfectamente el peligro del arrecife y que cada farero destinado a este islote era un cebo prescindible para mantener el canal marítimo abierto a cualquier costo."
        ),
        (
            "A las cuatro de la madrugada, un estruendo ensordecedor sacudió la base de la torre cuando una ola colosal de marea anómala impactó contra los cimientos de roca volcánica. "
            "El sonido de pasos pesados y húmedos comenzó a ascender por la escalera de hierro que conectaba los niveles inferiores con la sala de guardia, resonando con una cadencia pesada que aceleró mi pulso al límite del colapso. "
            "La madera de la puerta crujió bajo el empuje de una fuerza descomunal que combaba los tablones de roble y hacía saltar los pernos de hierro forjado de las bisagras superiores. "
            "Desde el ojo de la cerradura comenzó a filtrarse un hilo de agua marina oscura, gélida y viscosa que desprendía un olor fétido a descomposición abisal y algas fosilizadas. "
            "Tomé la escopeta de señales de dos cañones cargada con cartuchos de fósforo marino y apunté directamente hacia el centro de la madera que cedía milímetro a milímetro. "
            "Una voz sibilante y múltiple, como si docenas de gargantas ahogadas hablaran simultáneamente al unísono, susurró a través de la ranura de la puerta: 'Abre la esclusa y mira la profundidad del océano; todos los marineros olvidados duermen con nosotros bajo las olas'. "
            "El pestillo de acero se fracturó con un chasquido metálico y la hoja de la puerta se abrió de par en par hacia el corredor en penumbra, revelando una silueta alta y encorvada envuelta en jirones de algas fosforescentes y escamas oscuras."
        ),
        (
            "Disparé los dos cartuchos de fósforo a quemarropa contra el centro de la manifestación y el estallido de fuego incandescente iluminó la estancia con un fulgor blanco cegador que quemó el aire en un segundo. "
            "La entidad emitió un alarido desgarrador que reverberó en la piedra de la torre con la fuerza de un terremoto, retorciéndose mientras el fósforo derretía sus membranas translúcidas en una masa humeante de vapor acre. "
            "Aproveché el retroceso de la criatura para lanzarme por el pasaje de acceso a la linterna superior, subiendo los últimos peldaños con el corazón martilleando contra mis costillas y las manos quemadas por el calor del disparo. "
            "Llegué a la cúpula de cristal y accioné la válvula de paso del quemador de emergencia diésel, encendiendo una llamarada gigantesca en el foco de la lente Fresnel que proyectó un cono de luz de dos millones de bujías sobre los arrecifes exteriores. "
            "El haz de luz concentrado barrió los rompientes y pude ver con horror indescriptible que cientos de figuras oscuras cubrían los peñascos de basalto, retrocediendo despavoridas ante el resplandor del fuego para arrojarse al mar embravecido. "
            "El calor intenso de la lámpara quemaba las paredes de la linterna mientras el viento del océano aullaba contra los cristales, arrancando varias planchas de cobre del tejado exterior. "
            "Me mantuve junto a la manivela de alimentación de combustible durante dos horas interminables, recargando el quemador manualmente hasta que los primeros rayos del amanecer tiñeron el horizonte de un gris pálido y esperanzador."
        ),
        (
            "Cuando el sol iluminó por completo la superficie del Atlántico, el mar recuperó su tonalidad azul habitual y los arrecifes de basalto quedaron sumergidos bajo el flujo normal de la pleamar matutina. "
            "Descendí por la torre temblando de agotamiento físico y mental, con la ropa empapada de salitre y pólvora, encontrando los escalones de hierro cubiertos por una baba espesa que se disolvía rápidamente al contacto con la luz del día. "
            "A las diez de la mañana, un buque guardacostas de la marina arribó al islote tras recibir mi señal de socorro transmitida a través del transceptor de emergencia que logré conectar antes del ataque. "
            "Los oficiales navales que desembarcaron en el muelle inspeccionaron los daños en la linterna y las manchas de quemaduras químicas en la escalera, intercambiando miradas sombrías que confirmaban que no era la primera vez que presenciaban semejante escenario. "
            "Fui trasladado de inmediato a la enfermería de la base naval en tierra firme, donde fui sometido a pruebas toxicológicas y radiológicas exhaustivas bajo estricto régimen de incomunicación militar. "
            "Los médicos concluyeron en su informe que había sufrido un brote psicótico agudo provocado por el aislamiento prolongado y la inhalación accidental de vapores de mercurio desprendidos por el baño de la lente. "
            "Sin embargo, el comandante del sector naval me hizo firmar un documento de reserva de seguridad nacional antes de otorgarme la baja definitiva del cuerpo de señalización marítima."
        ),
        (
            "Investigaciones oceanográficas desclasificadas años más tarde por institutos hidrológicos independientes confirmaron la existencia de una fosa abisal de más de seis mil metros de profundidad a escasas dos millas del arrecife. "
            "Los sonares de barrido lateral detectaron estructuras monolíticas regulares en el fondo de la fosa que desafían cualquier proceso de sedimentación geológica conocido en la plataforma continental. "
            "Las muestras de agua recogidas a profundidades abisales presentaban concentraciones anómalas de compuestos orgánicos complejos que no corresponden a ninguna cadena trófica marina catalogada por la biología contemporánea. "
            "Pescadores de bajura de las aldeas costeras afirmaron durante generaciones que en las noches de luna nueva las luces del faro parecían ser absorbidas por una columna de niebla oscura que emergía de las profundidades marinas. "
            "Las autoridades ministeriales decidieron finalmente automatizar por completo el faro de Arrecife Negro, sustituyendo la potente linterna Fresnel por una baliza solar sellada y prohibiendo permanentemente la presencia de operadores humanos en el islote. "
            "La zona náutica circundante fue reclasificada como sector de tiro militar restringido para evitar que embarcaciones civiles se aproximen a las aguas del arrecife durante las temporadas invernales."
        ),
        (
            "En las décadas posteriores a mi traumática experiencia, mantuve contacto clandestino con la hija de Archibald MacIntyre, quien conservaba las cartas personales que su padre le enviaba desde el faro antes de su misteriosa desaparición. "
            "En aquellas misivas íntimas, el viejo farero describía con desgarradora lucidez cómo las criaturas del arrecife cantaban durante las tormentas con las voces de los tripulantes de barcos naufragados siglos atrás. "
            "MacIntyre estaba convencido de que la fosa submarina funcionaba como una trampa biológica que atraía embarcaciones hacia las rocas para absorber la memoria y la energía vital de quienes caían a las aguas heladas. "
            "La mujer me mostró un medallón de plata rescatado de las pertenencias de su padre, cuyo metal exhibía grabados idénticos a los patrones geométricos que vi en los arrecifes descubiertos durante la marea muerta. "
            "Comprendí que la tragedia de Arrecife Negro abarcaba más de un siglo de muertes encubiertas y que la administración marítima había actuado con una complicidad criminal sistemática. "
            "Las indemnizaciones a las viudas de los fareros desaparecidos incluían cláusulas leoninas que penalizaban con penas de prisión cualquier revelación pública sobre los sucesos ocurridos en el islote."
        ),
        (
            "Han transcurrido muchos años desde aquella noche de invierno y hoy vivo en una localidad del interior peninsular, lo más lejos posible de la línea de costa y del rumor del océano. "
            "Sin embargo, cada vez que visito una playa o escucho el graznido de las gaviotas en un día nublado, un escalofrío helado recorre mi espina dorsal al recordar el sonido de aquellos pasos en la escalera de hierro. "
            "El mar que para tantos representa descanso y belleza estival es para mí un abismo insondable donde habitan entidades que desprecian la existencia humana y esperan pacientemente su momento para reclamar la superficie. "
            "A menudo me pregunto cuántos otros navegantes han desaparecido en silencio en esas coordenadas restringidas sin que sus familias hayan podido recuperar siquiera un trozo de madera de sus embarcaciones. "
            "La convicción de que aquellas criaturas continúan acechando en la fosa de Arrecife Negro bajo el haz automático de la baliza solar me acompaña en cada noche de viento huracanado. "
            "El sonido del oleaje rompiendo contra las rocas nunca volverá a ser pacífico en mi memoria, recordándome la fragilidad de nuestra presencia frente al poder implacable de los abismos oceánicos."
        ),
        (
            "Crónicas marítimas del siglo dieciocho rescatadas de los archivos del almirantazgo británico mencionaban ya el 'Peñón de las Sombras' como un punto negro de navegación evitado sistemáticamente por las flotas mercantes de la época. "
            "Los diarios de navegación de varias fragatas reales registraban avistamientos de figuras humanoides de gran tamaño desplazándose sobre la superficie del agua en calma durante las calmas chichas de agosto. "
            "Varios navíos de línea fueron encontrados a la deriva en las inmediaciones del arrecife con toda su tripulación desaparecida, sin signos de combate ni saqueo y con los diarios de a bordo arrancados de sus encuadernaciones. "
            "Todo indicaba que el fenómeno anómalo de Arrecife Negro precedía en siglos a la construcción del faro y que la decisión de levantar una torre en ese peñasco respondió a un intento desesperado de balizar un territorio dominado por fuerzas incomprensibles. "
            "Al divulgar hoy estos acontecimientos, pretendo advertir a quienes navegan en aguas solitarias sobre los peligros que acechan más allá de las rutas comerciales seguras. "
            "El océano conserva santuarios oscuros donde las leyes de la biología terrestre quedan suspendidas y donde la curiosidad humana se paga con el olvido más absoluto."
        ),
        (
            "El análisis de las muestras del líquido viscoso que impregnaba los engranajes de la lente Fresnel, realizado por un químico retirado amigo mío, arrojó la presencia de proteínas desconocidas con enlaces moleculares no carbónicos. "
            "El compuesto no se congelaba a cuarenta grados bajo cero ni se evaporaba a más de trescientos grados centígrados, comportándose como un polímero superconductor orgánico de extrema resistencia física. "
            "El informe pericial privado concluía que la sustancia parecía haber sido segregada por un organismo adaptado a presiones abisales extremas y radiaciones geotérmicas de origen no volcánico. "
            "La confirmación científica de que me enfrenté a una forma de vida ajena a la biosfera terrestre conocida me proporcionó un alivio paradójico frente al diagnóstico psiquiátrico de alucinación impuesto por las autoridades navales. "
            "No estaba loco: el arrecife ocultaba una realidad monstruosa que el mundo moderno prefiere ignorar para preservar su ilusión de seguridad en las costas urbanizadas."
        ),
        (
            "La orden ministerial que clausuró formalmente la estación humana de Arrecife Negro en mil novecientos noventa y cinco dispuso la demolición de los alojamientos de los operarios y el sellado con plomo de los accesos a la base de la torre. "
            "La baliza automática que opera en la actualidad emite destellos en una frecuencia cifrada que solo es interpretada por receptores militares y sistemas de navegación satelital restringidos. "
            "Ningún buque pesquero civil tiene autorización para faenar a menos de diez millas náuticas del arrecife, bajo penas que contemplan la confiscación inmediata del barco y la retirada de la licencia de pesca profesional. "
            "Los pescadores veteranos que aún recuerdan la época del faro manual evitan mirar hacia el horizonte marino durante las noches de tormenta, sabiendo que la luz solar que destella en la cumbre del peñasco no es para guiar a los barcos amigos, sino para vigilar las aguas negras que rodean el islote. "
            "El silencio cómplice de las instituciones marítimas demuestra que hay verdades incómodas que jamás serán admitidas en los canales oficiales de comunicación pública."
        ),
        (
            "El océano abisal es el verdadero dueño de nuestro planeta, cubriendo más del setenta por ciento de la superficie terrestre con profundidades donde la luz del sol jamás ha penetrado desde el origen de los tiempos. "
            "Los seres humanos apenas hemos explorado una fracción insignificante de esas fosas submarinas, creyendo erróneamente que dominamos un medio que puede engullirnos en cualquier instante sin dejar huella alguna. "
            "Si alguna vez navegas en una embarcación solitaria y observas en el radar un eco inmóvil que no figura en ninguna carta de navegación actualizada, vira en redondo de inmediato y aléjate a toda máquina. "
            "No intentes aproximarte para comprobar si se trata de un escollo o de un pecio a la deriva, porque hay señales luminosas que no están diseñadas para salvarte del naufragio, sino para conducirte directamente hacia las bocas insaciables del abismo. "
            "La prudencia y el respeto por los enigmas del mar son las únicas virtudes que pueden mantenerte con vida en la inmensidad de las aguas oscuras."
        ),
        (
            "Finalizamos aquí este testimonio sobre el faro de Arrecife Negro, con la esperanza de que mi labor en divulgar estos hechos sirva como homenaje a todos los navegantes y fareros que desaparecieron sin dejar rastro en las aguas heladas del norte. "
            "Las grabaciones del transceptor de emergencia y los documentos privados que respaldan este relato permanecen custodiados bajo estricto compromiso ético con la verdad histórica."
        ),
    ]
    return "\n\n".join(p.strip() for p in paragraphs)

def build_moku_rail(topic: str, **kwargs: Any) -> str:
    paragraphs = [
        (
            f"En las soledades boreales donde las vías de ferrocarril atraviesan bosques interminables de taiga congelada, el enigma de {topic} constituye el secreto más aterrador jamás presenciado por los trabajadores del riel. "
            "Durante el crudo invierno de mil novecientos noventa y siete, fui asignado como guardagujas nocturno a la Garita Treinta y Dos, un enclave ferroviario aislado a cien kilómetros de cualquier asentamiento urbano en la línea del extremo norte. "
            "Mi labor consistía en operar las palancas manuales de cambio de vía para dar paso a los convoyes de carga pesada que transportaban madera y mineral de hierro hacia las fundiciones del sur. "
            "La cabina de señales era una estructura austera de madera y cinc, calentada por una estufa de carbón que apenas lograba templar el ambiente frente a temperaturas exteriores que descendían con frecuencia por debajo de los treinta grados bajo cero. "
            "Los maquinistas veteranos que pasaban con sus locomotoras diésel me saludaban con tres toques breves de silbato, una cortesía entre hombres del riel que mitigaba la agobiante soledad de los turnos nocturnos de doce horas. "
            "Sin embargo, el despachador de tráfico de la estación central me advirtió antes de asumir el puesto que prestara especial atención a la vía muerta número cuatro, un ramal secundario desmantelado hacía cuatro décadas tras un grave accidente ferroviario que costó la vida a decenas de prisioneros de guerra. "
            "El terraplén de esa vía auxiliar estaba cubierto por matorrales congelados y nieve virgen, y sus agujas mecánicas permanecían encadenadas con candados de seguridad oxidados por el paso de los años. "
            "A pesar de ello, los cables del telégrafo de aguja que colgaban entre los postes de madera comenzaban a vibrar con una frecuencia extraña apenas caía la medianoche sobre el bosque de abetos."
        ),
        (
            "A la una y cuarto de la madrugada, cuando el termómetro de mercurio exterior marcaba treinta y cuatro grados bajo cero, el aparato telegráfico de la mesa de guardia comenzó a tabletear furiosamente. "
            "El punzón metálico grabó sobre la cinta de papel continuo un código de despacho que no figuraba en el reglamento de circulación de la compañía ferroviaria nacional. "
            "El mensaje se repetía de forma obsesiva en una serie ininterrumpida de puntos y rayas que, al ser decodificados con el manual antiguo de señales, formaban una sola palabra: 'Despejen vía cuatro para el expreso especial de prisioneros'. "
            "Revisé el libro de itinerarios y confirmé que ningún tren especial de pasajeros o de carga militar tenía autorización para circular por ese sector durante la noche. "
            "Pensé en una interferencia atmosférica en las líneas telegráficas o en una broma pesada de los operarios de la garita anterior, pero al salir al balcón exterior para inspeccionar la playa de vías, el aliento se me congeló en la garganta. "
            "A través de la densa nevada pude ver que los rieles cubiertos de herrumbre de la vía muerta número cuatro resplandecían con un brillo térmico anómalo, como si el metal estuviera siendo calentado desde el subsuelo a cientos de grados de temperatura. "
            "La nieve acumulada sobre las traviesas de madera se derretía instantáneamente en un silbido de vapor blanco que ascendía hacia las copas de los árboles como una hilera de fantasmas silenciosos. "
            "Un zumbido sordo y rítmico, semejante al émbolo de una locomotora de vapor de alta potencia, comenzó a retumbar en el lecho de balasto con una fuerza que hizo vibrar los cristales de la cabina de señales."
        ),
        (
            "Tomé el farol de carburo de guardia y la llave maestra de agujas para bajar a la explanada y comprobar el estado de los cerrojos mecánicos de la vía cuatro. "
            "El viento helado aullaba entre los cables de tensión telegráfica, pero alrededor de los rieles calientes el aire era sofocante, cargado de un olor nauseabundo a carbón mineral quemado, azufre y metal fundido. "
            "Al alumbrar la aguja de cambio descubrí que las gruesas cadenas de acero estaban partidas limpiamente, como si una fuerza descomunal las hubiera quebrado de un solo tirón sin deformar los eslabones adyacentes. "
            "La palanca de maniobra oscilaba por sí sola hacia adelante y hacia atrás en un arco constante, haciendo chasquear las contragujas contra el carril con una cadencia metálica aterradora que parecía sincronizarse con los latidos de mi propio corazón. "
            "De repente, a menos de quinientos metros por el ramal abandonado que se internaba en la espesura del bosque, un foco de luz amarilla y titilante perforó la cortina de nieve. "
            "Un silbato de vapor estridente y lúgubre, cuyo eco desgarró el silencio de la taiga con un alarido prolongado, anunció la llegada inminente de un convoy ferroviario que desafiaba toda lógica espacio-temporal. "
            "El suelo tembló violentamente bajo mis botas y me vi obligado a retroceder hacia la escalerilla de la garita mientras una masa gigantesca de hierro negro emergía de la penumbra entre nubes de ceniza y vapor ardiente."
        ),
        (
            "Subí a trompicones los peldaños de madera y me atrincheré en la cabina de control, observando desde la ventana con los ojos desorbitados por el espanto más absoluto. "
            "La locomotora era un monstruo de vapor de la serie soviética de mil novecientos cuarenta, con la caldera oxidada y cubierta de escarcha negra, avanzando a paso de hombre sin producir humo visible por su chimenea principal. "
            "Detrás de la máquina rodaban seis vagones de madera carcomida con ventanillas enrejadas, de cuyo interior surgía una tenue luminiscencia verdosa que iluminaba los rostros de los ocupantes. "
            "Eran docenas de figuras humanas consumidas, con uniformes militares harapientos y rostros esqueléticos congelados en muecas de dolor indecible, mirando fijamente a través de los barrotes de hierro hacia la ventana de mi garita. "
            "Ninguna de las figuras parpadeaba ni se movía; permanecían inmóviles como estatuas de salitre mientras sus bocas abiertas parecían modular en silencio una plegaria desesperada de auxilio. "
            "En las paredes exteriores de los vagones se distinguían las marcas de impactos de bala y las letras despintadas que catalogaban al tren como el 'Convoy Penal Especial Setenta y Dos', desaparecido en las ventiscas de mil novecientos cincuenta y cuatro. "
            "Al pasar frente a la cabina de señales, el maquinista del tren espectral giró lentamente la cabeza hacia mí: su cráneo desprovisto de piel exhibía dos órbitas vacías donde ardían brasas incandescentes de carbón encendido."
        ),
        (
            "En ese instante sonó la campana de alarma del tablero eléctrico central: el tren rápido de pasajeros número catorce se aproximaba a gran velocidad por la vía principal hacia mi garita, con más de trescientos civiles a bordo. "
            "Si la aguja mecánica de la vía cuatro continuaba oscilando descontrolada, el convoy espectral invadiría el carril principal en menos de dos minutos, provocando una catástrofe ferroviaria de proporciones inimaginables. "
            "El terror que me paralizaba se transformó en una adrenalina ciega de deber profesional; mi puesto de guardagujas exigía proteger la vida de los pasajeros que dormían confiados en los coches de literas del expreso nocturno. "
            "Agarré la barra de acero de bloqueo manual y descendí nuevamente a la playa de vías en medio del vendaval, corriendo sobre las traviesas resbaladizas hacia el corazón de la zona de cambio de agujas. "
            "El calor que emanaba del convoy de los condenados me quemaba las pestañas y el aire fétido me provocaba arcadas incontrolables, pero me arrojé con todo mi peso sobre la palanca de cambio para encajar el pasador de seguridad. "
            "Sentí cómo una presencia gélida atravesaba mi espalda, como si decenas de manos invisibles y heladas intentaran apartar mis brazos del timón de acero para forzar el descarrilamiento. "
            "Apreté los dientes con todas mis fuerzas, gritando con desesperación contra la ventisca, y logré introducir el perno de traba en el alojamiento del carril apenas unos segundos antes de que la primera rueda del tren espectral rozara la punta de la aguja."
        ),
        (
            "Un chispazo azul cegador estalló en el punto de contacto entre el acero del riel y la rueda de la locomotora, arrojándome violentamente hacia el talud de nieve donde quedé aturdido por el impacto. "
            "Al levantar la vista entre la neblina provocada por la pólvora y el vapor, vi cómo el convoy de madera se desvanecía en el aire gélido como una ilusión óptica, disolviéndose en partículas de ceniza que el viento boreal dispersó en segundos sobre las copas de los árboles. "
            "Pocos segundos después, el potente foco halógeno del expreso de pasajeros número catorce rasgó la oscuridad de la noche, pasando a ciento veinte kilómetros por hora por la vía principal con el estruendo tranquilizador de sus motores diésel modernos. "
            "Las ventanillas iluminadas mostraban a viajeros durmiendo pacíficamente ajenos por completo al horror que acababa de disiparse a escasos metros de sus cabezas. "
            "Quedé tendido sobre la nieve durante varios minutos, llorando de alivio y agotamiento con las manos enguantadas chamuscadas por la descarga estática del cambio de agujas. "
            "Cuando logré ponerme en pie y regresar a la garita, el telégrafo de aguja estaba completamente fundido, con la aguja indicadora doblada hacia arriba y la bobina de cobre reducida a un trozo amorfo de metal derretido."
        ),
        (
            "Al amanecer, la cuadrilla de mantenimiento de vías y obras llegó en la dresina de inspección rutinaria, encontrándome pálido y con síntomas severos de hipotermia en la cabina de señales. "
            "Al inspeccionar la vía muerta número cuatro, los ingenieros quedaron perplejos al comprobar que los rieles de acero laminado presentaban una despolarización magnética total y un temple anómalo que había cristalizado el hierro como si hubiera estado expuesto a miles de grados de temperatura. "
            "Las traviesas de roble centenario estaban carbonizadas por debajo de la capa de escarcha superficial, desprendiendo aún un calor residual que descongelaba el balasto en un radio de cincuenta metros. "
            "El jefe de distrito ferroviario me interrogó durante horas en el dispensario médico de la estación término, negándose a aceptar mi relato sobre la locomotora de vapor y los prisioneros de guerra. "
            "La dirección de la empresa emitió un comunicado interno donde atribuía los daños a la caída de un rayo en la línea de alta tensión vecina y ordenó mi traslado inmediato a un puesto administrativo en los talleres centrales de la capital. "
            "Sin embargo, antes de retirarme de la zona, un anciano maquinista jubilado me abordó en el andén y me estrechó la mano con lágrimas en los ojos: su hermano menor viajaba como recluta en el Convoy Setenta y Dos cuando este desapareció en la ventisca de mil novecientos cincuenta y cuatro."
        ),
        (
            "Informes técnicos clasificados elaborados por peritos de la administración de ferrocarriles del estado documentaron que el tramo de la Garita Treinta y Dos presentaba anomalías de dilatación temporal registradas en los cronómetros mecánicos de los trenes en tránsito. "
            "Los relojes de péndulo de la cabina de señales y los tacógrafos de las locomotoras que cruzaban el sector acumulaban un retraso sistemático de cuatro minutos y treinta y tres segundos cada noche entre la una y las dos de la madrugada. "
            "Los análisis metalúrgicos de los rieles de la vía cuatro determinaron que la aleación de acero contenía impurezas de carbono isotópico que solo se formaban bajo procesos de radiación dura ausentes en la industria siderúrgica tradicional. "
            "A pesar de los intentos de las autoridades por restar importancia a los informes, las tripulaciones de los trenes de carga comenzaron a negarse a circular por ese tramo durante las horas de la madrugada sin escolta técnica adicional. "
            "La compañía ferroviaria optó finalmente por clausurar definitivamente la Garita Treinta y Dos y desmantelar por completo las agujas de cambio, levantando los rieles de la vía cuatro con maquinaria pesada para evitar cualquier conexión física con la línea principal. "
            "Los terrenos adyacentes fueron declarados servidumbre militar de paso restringido, quedando prohibida la construcción de cualquier instalación humana en cinco kilómetros a la redonda."
        ),
        (
            "Durante los años posteriores a mi jubilación forzosa, me dediqué a investigar en hemerotecas y archivos históricos sobre el destino final del Convoy Penal Setenta y Dos. "
            "Descubrí actas militares secretas que confirmaban que en diciembre de mil novecientos cincuenta y cuatro un tren con cuatrocientos prisioneros políticos fue desviado intencionadamente hacia una vía muerta en mitad de la taiga durante una purga burocrática del régimen. "
            "Las autoridades de la época cerraron las agujas de cambio, cortaron las líneas de suministro y abandonaron los vagones en mitad de una tormenta invernal que alcanzó los cincuenta grados bajo cero, dejando que el frío hiciera el trabajo sucio sin necesidad de disparar un solo tiro. "
            "Los cuerpos congelados nunca fueron recuperados y los expedientes judiciales fueron sellados bajo secreto de estado para proteger la carrera de los mandos militares responsables de la masacre. "
            "Comprendí entonces que la aparición del convoy no era un simple espectro del pasado, sino la memoria viva del hierro y el balasto que revivía periódicamente el sufrimiento indecible de aquellos hombres olvidados en la nieve. "
            "Las almas de los prisioneros continuaban recorriendo la taiga en su prisión de madera y acero, buscando una vía abierta hacia la justicia que los vivos les negaron durante más de cuatro décadas."
        ),
        (
            "Hoy en día resido en una tranquila ciudad del sur, pero el sonido de un tren distante cortando el silencio de la noche sigue erizándome la piel como en aquella madrugada en la Garita Treinta y Dos. "
            "Cada vez que escucho el traqueteo rítmico de un vagón sobre las juntas de dilatación del riel, mis ojos buscan involuntariamente en las sombras la silueta esquelética de la locomotora de vapor. "
            "El ferrocarril, que para tantos representa el progreso industrial y la conexión entre pueblos distantes, es para mí una red de cicatrices de acero que aprisionan dolores demasiado profundos para ser borrados por el tiempo. "
            "Agradezco cada noche haber tenido el coraje de empujar aquella palanca de cambio de agujas y evitar que el expreso de pasajeros compartiera el destino trágico del Convoy Setenta y Dos. "
            "Mi memoria custodia con respeto el recuerdo de los que perecieron en aquella vía muerta y mantendré viva su historia mientras conserve una gota de aliento en el pecho."
        ),
        (
            "Documentos ferroviarios desclasificados recientemente confirman que la Garita Treinta y Dos no fue el único enclave donde se reportaron apariciones de trenes fantasmas en las líneas boreales del país. "
            "En al menos tres ramales abandonados de Siberia y los montes Urales se registraron testimonios idénticos de operarios que presenciaron convoyes de vapor circulando sobre vías oxidadas y sin catenaria eléctrica. "
            "Los especialistas en fenómenos de resonancia acústica postulan que las grandes estructuras de hierro enterradas en suelos de permafrost actúan como acumuladores electromagnéticos capaces de registrar y proyectar acontecimientos traumáticos bajo ciertas condiciones meteorológicas extremas. "
            "Esta hipótesis científica intenta normalizar lo que los viejos ferroviarios conocemos con certeza desde hace generaciones: el riel tiene memoria y el hierro no olvida la sangre derramada sobre sus durmientes. "
            "El hermetismo de las corporaciones del transporte demuestra que ciertas realidades operativas son silenciadas sistemáticamente para evitar el pánico entre los viajeros habituales del transporte público."
        ),
        (
            "El análisis de la cinta de telégrafo que logré conservar como prueba material reveló que las perforaciones de los puntos y rayas estaban grabadas con una precisión micrométrica que superaba la capacidad mecánica de los electroimanes de la época. "
            "Un laboratorio forense independiente determinó que el papel exhibía partículas microscópicas de hollín vegetal de turba que no se utiliza en calderas industriales desde hace más de medio siglo. "
            "Estas evidencias materiales desmienten categóricamente cualquier intento de atribuir lo ocurrido a un episodio de delirio inducido por el frío o el aislamiento prolongado en la cabina de señales. "
            "Me enfrenté a una manifestación física real, a un convoy de condenados que reclamaba su derecho a cruzar el bosque para no ser sepultado por el olvido de la historia oficial. "
            "Compartir hoy este testimonio con ustedes es mi última obligación moral como guardagujas de la Garita Treinta y Dos."
        ),
        (
            "La empresa ferroviaria procedió a la demolición de la garita en el año dos mil dos, borrando cualquier vestigio físico de la cabina de señales y reforestando la playa de vías con plantaciones de pinos y alerces. "
            "Sin embargo, los maquinistas contemporáneos que conducen los modernos trenes de alta velocidad afirman que en las noches más frías de enero los sistemas de señalización digital siguen reportando ocupación fantasma en el cantón del antiguo kilómetro noventa y siete. "
            "Las computadoras de a bordo reducen automáticamente la velocidad de marcha por precaución técnica, obligando a los conductores a mirar hacia la oscuridad del bosque donde antes se cruzaban las vías de la estación fantasma. "
            "Nadie en la administración se atreve a desinstalar los protocolos de frenado automático de ese sector, reconociendo implícitamente que la vía muerta sigue cobrando su tributo de respeto y cautela a quienes cruzan la taiga."
        ),
        (
            "El acero de las vías férreas que cruzan los continentes representa una de las mayores hazañas técnicas de la humanidad, pero también el testimonio mudo de incontables sacrificios humanos que jamás figurarán en los libros de historia. "
            "Aprender a respetar las señales de advertencia del camino y no desafiar las sombras que habitan en los ramales muertos es una lección que aprendí al borde de la muerte y que transmito con humildad a las nuevas generaciones. "
            "Si alguna vez viajas de noche en un tren que cruza bosques desolados y escuchas un silbato arcaico que no proviene de la locomotora moderna que encabeza la marcha, no intentes mirar por la ventanilla hacia la vía secundaria. "
            "Cierra la cortinilla, respeta el descanso de quienes no pudieron llegar a su destino y permite que el expreso de los olvidados continúe su marcha infinita hacia la noche boreal."
        ),
        (
            "Finalizamos aquí este testimonio sobrecogedor sobre la Garita Treinta y Dos, dejando constancia de que los archivos de tráfico y las evidencias telegráficas permanecen custodiados en mi memoria para honor de los trabajadores del riel. "
            "La vía principal continúa despejada para quienes viajan con rectitud, mientras las vías muertas permanecen en silencio bajo el manto eterno de la nieve del norte."
        ),
    ]
    return "\n\n".join(p.strip() for p in paragraphs)

def get_wedding_story(topic: str) -> str:
    paragraphs = [
        (
            f"El amor y los compromisos matrimoniales deberían ser el inicio de una alianza de respeto mutuo, pero hoy analizamos en profundidad los sucesos de {topic} donde la ambición familiar destruyó planes de vida en cuestión de días. "
            "Cuando dos personas deciden unir sus vidas y comenzar a construir un hogar propio, las expectativas de los parientes políticos pueden convertirse en una pesadilla de intromisiones asfixiantes y exigencias económicas desmedidas. "
            "Acompáñanos a descubrir tres impactantes historias reales donde hombres y mujeres tuvieron que tomar la desgarradora decisión de cancelar compromisos o poner límites inquebrantables para no ver destruido su patrimonio personal por el capricho de sus familias políticas. "
            "Analizaremos cada dilema desde la perspectiva de quienes se atrevieron a decir basta frente al chantaje afectivo más agresivo y a defender la soberanía de sus decisiones vitales. "
            "A través de estos testimonios examinaremos cómo los fondos destinados a la compra de una vivienda o a la celebración de una boda pueden encender disputas familiares de consecuencias irreparables. "
            "La pregunta central que guía nuestro análisis es hasta qué punto debemos tolerar la imposición de exigencias financieras abusivas en nombre de un futuro matrimonio o de una supuesta armonía con los suegros y cuñados."
        ),
        (
            "El primer caso de esta entrega nos coloca en la antesala de lo que prometía ser una boda de ensueño tras seis años de noviazgo formal entre dos profesionales jóvenes. "
            "Nuestro protagonista había aportado el ochenta por ciento de los ahorros mancomunados para pagar la entrada de su futura vivienda conyugal, depositando la suma en una cuenta fiduciaria a nombre de ambos. "
            "Sin embargo, a tres semanas de la ceremonia nupcial, la madre de la novia organizó una cena íntima para soltar una exigencia que heló la sangre del novio: "
            "'Hemos decidido en familia que ustedes deben posponer la compra de la casa y transferir ese dinero para pagar la boda de lujo que mi hijo menor merece celebrar este año'. "
            "La prometida, en lugar de defender el proyecto común de vivienda, asintió dócilmente diciendo: "
            "'Cariño, mi hermano no tiene empleo fijo y tú ganas muy bien en tu bufete; si realmente me amas, entenderás que la felicidad de mi familia está por encima de una hipoteca'. "
            "La naturalidad con la que ambas mujeres pretendían despojar al protagonista de cinco años de trabajo duro provocó un silencio sepulcral en el comedor. "
            "El novio comprendió de inmediato que su papel en esa familia no era el de un compañero respetado, sino el de una billetera ambulante destinada a financiar los caprichos del hermano mimado de su prometida."
        ),
        (
            "Lejos de someterse al chantaje moral, nuestro protagonista tomó aire, miró a su prometida a los ojos y respondió con una calma demoledora: "
            "'No voy a financiar la boda de tu hermano ni voy a sacrificar el patrimonio que construí con mis horas de sueño; nuestro compromiso matrimonial queda cancelado definitivamente esta misma noche'. "
            "Se levantó de la mesa, se retiró del lugar y a la mañana siguiente acudió a primera hora a la entidad bancaria para congelar la cuenta de ahorros y retirar su aportación debidamente acreditada con transferencias salariales. "
            "La reacción del clan político fue una auténtica tormenta de furia y amenazas: lo acusaron de ser un monstruo desalmado, llamaron a sus jefes en la empresa para difamarlo y le exigieron que indemnizara los gastos del banquete ya contratado. "
            "El protagonista contrató a un abogado mercantil que notificó a los proveedores la cancelación unilateral del enlace por causas imputables a la familia de la novia, evitando incurrir en penalizaciones contractuales abusivas. "
            "Aunque la ruptura fue sumamente amarga y le costó meses de tristeza por el desengaño amoroso, hoy en día es el único dueño de un hermoso departamento libre de deudas y de ataduras tóxicas. "
            "Este primer conflicto evidencia cómo el matrimonio nunca debe convertirse en un contrato de servidumbre financiera hacia parientes políticos que no respetan el sacrificio ajeno."
        ),
        (
            "El segundo caso profundiza en las tensiones por la titularidad de bienes heredados cuando entra en juego la presión de los padres hacia el hijo económicamente exitoso. "
            "Una profesional sanitaria había heredado de su madrina un céntrico piso de dos habitaciones, el cual reformó íntegramente con sus propios honorarios médicos para ponerlo en alquiler y asegurar un fondo de retiro digno. "
            "Sin embargo, cuando su hermana menor quedó embarazada de su tercer hijo sin contar con ingresos estables ni pareja responsable, los padres exigieron que la protagonista le cediera el departamento de forma gratuita y vitalicia: "
            "'Tú tienes un sueldo excelente en el hospital y vives cómodamente de tu trabajo, mientras tu hermana está en la calle con tres criaturas que mantener'. "
            "Cuando la protagonista propuso alquilárselo a precio simbólico con un contrato de arrendamiento formal para proteger la titularidad del inmueble, la madre montó en cólera tachándola de usurpadora desprovista de instinto maternal. "
            "Durante meses, la familia orquestó un linchamiento emocional en las celebraciones dominicales, excluyéndola de los aniversarios y afirmando ante los tíos y primos que ella prefería el dinero antes que el bienestar de sus sobrinos pequeños. "
            "La presión fue tan abrumadora que la protagonista comenzó a sufrir crisis de ansiedad severas, llegando a dudar de su propia rectitud moral frente al reproche colectivo del clan."
        ),
        (
            "En el segundo caso, el punto de inflexión ocurrió cuando la protagonista descubrió que la hermana menor ya había anunciado en redes sociales que el piso era suyo y planeaba derribar tabiques para instalar una terraza privada. "
            "Comprendiendo que la cesión gratuita se transformaría en una expropiación de facto que jamás recuperaría pacíficamente, decidió formalizar un contrato de alquiler comercial con un inquilino solvente a través de una agencia inmobiliaria profesional. "
            "Al encontrarse la vivienda formalmente arrendada a terceros con contrato registrado en la delegación de hacienda, la hermana y los padres no tuvieron más opción que desistir de la ocupación forzosa de la vivienda. "
            "A pesar de que sus progenitores le retiraron la palabra durante dos años consecutivos, la protagonista utilizó los ingresos generados por la renta para financiar una beca de estudios privada para el sobrino mayor, asegurando su educación sin premiar la irresponsabilidad adulta de su madre. "
            "Esta valiente determinación demuestra que la verdadera generosidad no consiste en regalar el patrimonio propio a quien no sabe administrar su propia vida, sino en salvaguardar los recursos para invertirlos donde realmente generen un beneficio constructivo y medible a largo plazo. "
            "El respeto personal exige a menudo soportar la etiqueta injusta de 'hija egoísta' con tal de no permitir que la manipulación emocional destruya los frutos del esfuerzo honrado."
        ),
        (
            "En el tercer caso de este recorrido dramático, el conflicto estalló en torno a una vivienda unifamiliar que el protagonista adquirió a título privativo cinco años antes de contraer matrimonio civil. "
            "Tras la boda, los suegros comenzaron a presionar de manera insistente para que el marido modificara las escrituras públicas ante notario e inscribiera a la esposa como copropietaria al cincuenta por ciento del inmueble. "
            "El suegro sostenía públicamente con tono autoritario: "
            "'En este hogar no aceptamos acuerdos prematrimoniales ni bienes privativos; si mi hija duerme bajo ese techo, la mitad de los ladrillos le pertenecen por ley divina y conyugal'. "
            "Cuando el protagonista explicó con educación que la casa estaba totalmente pagada con la herencia de sus propios abuelos y que constituía el patrimonio de salvaguarda para sus futuros descendientes, los suegros amenazaron con forzar a su hija a solicitar el divorcio conyugal inmediato. "
            "La esposa, lejos de poner un alto a la intromisión de sus padres, comenzó a retirar ahorros comunes de la cuenta bancaria para depositarlos en cuentas secretas administradas por su madre como medida de presión psicológica. "
            "El ambiente doméstico se transformó en un campo de espionaje y desconfianza constante donde cada gasto rutinario era fiscalizado por la familia política con una hostilidad insoportable. "
            "El marido descubrió conversaciones en el teléfono de su cónyuge donde los suegros le aconsejaban inventar denuncias por violencia económica para forzar una pensión compensatoria y la adjudicación del uso de la vivienda."
        ),
        (
            "La resolución del tercer caso fue contundente: el protagonista contrató peritajes informáticos para certificar las conversaciones de conspiración patrimonial y presentó formalmente la demanda de divorcio contencioso antes de que sus suegros pudieran ejecutar su trampa judicial. "
            "El juez de familia desestimó de plano las pretensiones de la esposa sobre la vivienda privativa, ordenándole restituir de inmediato la totalidad de los fondos desviados de la cuenta común hacia las cuentas de su madre. "
            "A pesar del dolor desgarrador que supuso ver derrumbarse su matrimonio en un tribunal de justicia, el protagonista evitó una catástrofe financiera que lo habría dejado en la ruina absoluta a sus cuarenta años de edad. "
            "Hoy en día vive con una paz inquebrantable en la casa que sus abuelos le legaron, habiendo aprendido que los parientes políticos que exigen títulos de propiedad ajenos no buscan la felicidad conyugal, sino la conquista territorial de los bienes que jamás pudieron conseguir con su propio trabajo. "
            "Este aleccionador relato pone de manifiesto que la soberanía patrimonial previa al matrimonio debe protegerse con firmeza legal inquebrantable para no quedar a expensas de chantajes afectivos cuando las relaciones conyugales entran en crisis. "
            "La firmeza en defender lo propio frente a exigencias desmedidas es la mejor garantía para construir relaciones sentimentales basadas en la autenticidad y el respeto mutuo."
        ),
        (
            "Al analizar en conjunto estos tres casos sobre bodas y fondos de vivienda, resalta la importancia crucial de separar con total nitidez el afecto conyugal de las responsabilidades patrimoniales intrafamiliares. "
            "Muchos de los abusos más destructivos se cometen al amparo de consignas románticas vacías como 'lo mío es tuyo', utilizadas por parientes manipuladores para despojar al cónyuge más disciplinado de sus legítimas defensas económicas. "
            "Los expertos en mediación matrimonial insisten en que los pactos prematrimoniales y la separación de bienes no representan una falta de fe en el amor conyugal, sino una muestra madura de respeto y cuidado mutuo frente a interferencias de familias de origen disfuncionales. "
            "Quien ama con honestidad nunca condicionará su cariño a la firma de una hipoteca ni exigirá que sacrifiques tus ahorros para rescatar a parientes que se niegan a asumir el costo de sus propios errores. "
            "Establecer límites contractuales claros desde el primer día es el único método eficaz para evitar que los conflictos familiares terminen en juzgados de guardia y rupturas traumáticas."
        ),
        (
            "Otro factor decisivo que revelan estas experiencias es la necesidad imperiosa de evaluar cómo reacciona tu pareja cuando su familia de origen atenta contra los intereses de la futura familia conyugal. "
            "Si una persona es incapaz de poner un límite a las exigencias abusivas de sus propios padres o hermanos, jamás podrá ser un compañero leal y protector en la convivencia cotidiana de un hogar adulto. "
            "El matrimonio exige una lealtad primordial hacia el nuevo núcleo familiar que se construye, relegando las opiniones e intromisiones de la familia de origen a un plano secundario y respetuoso. "
            "Quien antepone la aprobación sumisa de sus progenitores por encima del bienestar de su cónyuge demuestra una inmadurez emocional que tarde o temprano destruirá cualquier proyecto matrimonial por prometedor que parezca al inicio. "
            "Aprender a detectar estas señales de alarma antes de firmar un acta matrimonial o comprar una propiedad mancomunada es la decisión más inteligente que cualquier persona puede adoptar por su propia seguridad futura."
        ),
        (
            "Para concluir este análisis sobre las bodas canceladas y los fondos de vivienda disputados, queremos animarte a reflexionar sobre tus propias prioridades patrimoniales frente a tu entorno sentimental. "
            "¿Habrías tenido la valentía de cancelar una boda a tres semanas de la ceremonia como hizo nuestro primer protagonista para proteger los ahorros de tu primera vivienda propia? "
            "¿Consideras que la hermana del segundo caso actuó con prudencia al formalizar el alquiler comercial de su piso heredado antes de permitir la ocupación precaria de su hermana menor? "
            "Recordar que tu esfuerzo y tu patrimonio personal son el resultado de tus horas de vida y de tu disciplina te dará la fuerza necesaria para defenderlos frente a cualquier intento de extorsión afectiva. "
            "Caminar con la frente en alto sabiendo que no permitiste que el chantaje financiero decidiera tu destino es la mayor conquista de dignidad y autonomía que un ser humano puede celebrar en su vida adulta. "
            "Ninguna celebración festiva ni ninguna aprobación familiar valen el precio de regalar tu libertad económica a quienes nunca supieron valorar tu esfuerzo honrado."
        ),
        (
            "En el primer caso, la cancelación del compromiso evitó un matrimonio tóxico fundado en la servidumbre económica hacia una familia política parasitaria. "
            "En el segundo caso, el arrendamiento profesional protegió la propiedad frente a una ocupación ilegal que habría desembocado en un litigio judicial interminable con parientes directos. "
            "Y en el tercer caso, el divorcio preventivo blindó la casa ancestral frente a un plan conspirativo urdido por los suegros para quedarse con la titularidad registral del inmueble. "
            "Estos tres desenlaces contundentes reafirman que la serenidad de conciencia y la protección del fruto de nuestro trabajo son valores innegociables en cualquier relación humana saludable. "
            "Que estos testimonios sirvan como una guía certera para quienes hoy enfrentan dudas similares en la gestión de su patrimonio personal."
        ),
        (
            "Agradecemos enormemente la confianza de los oyentes que comparten sus vivencias para enriquecer este espacio de análisis moral y familiar. "
            "El debate sobre las bodas, las herencias y los límites frente a las familias políticas continúa abierto en nuestra comunidad para todos aquellos que valoran la verdad, la justicia y la dignidad personal por encima de las apariencias sociales."
        ),
    ]
    return "\n\n".join(p.strip() for p in paragraphs)


def get_wedding_story_v2(topic: str) -> str:
    s = get_wedding_story(topic)
    extra_paragraphs = [
        (
            "Al profundizar en los aspectos psicológicos de la dinámica observada en el primer caso, los terapeutas de pareja advierten sobre el fenómeno del 'hijo de oro' familiar. "
            "En muchas familias disfuncionales, uno de los hijos es designado tácitamente como el centro de atención y el receptor privilegiado de todos los recursos económicos del clan. "
            "Los demás hermanos y parientes políticos son educados para creer que su único propósito vital es facilitar el bienestar y el estatus social de este miembro mimado. "
            "Cuando una pareja intenta establecer prioridades independientes, como la adquisición de una vivienda o el ahorro disciplinado para su propia estabilidad conyugal, el sistema familiar reacciona con una violencia emocional desmedida. "
            "La negativa a sacrificar el patrimonio personal es vivida como una herejía intolerable que debe ser castigada con el aislamiento y el desprecio colectivo. "
            "Comprender esta distorsión relacional es fundamental para liberarse del sentimiento de culpa inducido y asumir que la ruptura de un compromiso tóxico es el acto más sano de supervivencia emocional."
        ),
        (
            "En relación con el segundo caso, los expertos en derecho inmobiliario recuerdan que la cesión precaria de viviendas a parientes consanguíneos es la causa de más del cuarenta por ciento de los litigios de desahucio entre particulares. "
            "La creencia popular de que no es necesario firmar contratos formales de arrendamiento cuando se trata de hermanos o sobrinos desemboca con alarmante frecuencia en situaciones de despojo definitivo. "
            "Una vez que un pariente se instala en un inmueble sin título legal que delimite sus derechos y obligaciones, la recuperación de la posesión pacífica se convierte en un calvario judicial que suele durar varios años y costar miles de euros en honorarios periciales. "
            "La firmeza demostrada por nuestra protagonista al exigir un contrato comercial profesional es la única garantía contrastada para salvaguardar la titularidad registral y evitar que la benevolencia se transforme en una trampa económica irreversible."
        ),
        (
            "Por último, el tercer caso pone de relieve la imperiosa necesidad de que los cónyuges mantengan una absoluta transparencia contable y una separación patrimonial nítida cuando existen bienes adquiridos con anterioridad a la convivencia formal. "
            "La intromisión de suegros y cuñados en la administración económica del hogar marital es uno de los mayores predictores de fracaso matrimonial documentados por la sociología contemporánea. "
            "Cuando uno de los cónyuges permite que sus progenitores dicten las decisiones financieras o intenten apropiarse de los bienes privativos del compañero sentimental, la confianza básica que sostiene el vínculo afectivo queda destruida de forma irreparable. "
            "Proteger las escrituras notariales y acudir a asesoría jurídica independiente ante los primeros indicios de conspiración patrimonial no es una muestra de desamor, sino el deber elemental de preservar la justicia y la dignidad personal frente a la codicia ajena."
        ),
    ]
    all_p = s.split("\n\n") + [p.strip() for p in extra_paragraphs]
    return "\n\n".join(all_p)


def build_aelithia_wedding_house(topic: str, **kwargs: Any) -> str:
    s = get_wedding_story_v2(topic)
    final_p = (
        "Como reflexión final para nuestra comunidad de oyentes, queremos destacar tres principios fundamentales para blindar tu futuro matrimonial frente a presiones familiares injustas. "
        "En primer lugar, establece acuerdos financieros claros antes de fijar cualquier fecha de boda o entregar anticipos a proveedores de eventos. "
        "En segundo lugar, jamás permitas que tu familia de origen o tu familia política tengan acceso a tus cuentas bancarias o a las claves de tus fondos de inversión personales. "
        "Y en tercer lugar, recuerda que quien te ama de verdad jamás te exigirá que te endeudes ni que sacrifiques tu patrimonio para complacer el ego de parientes irresponsables. "
        "La dignidad y la paz mental son bienes sagrados que ninguna convención social ni ninguna aprobación ajena pueden llegar a sustituir en tu vida cotidiana."
    )
    return s + "\n\n" + final_p.strip()

def get_business_story(topic: str) -> str:
    paragraphs = [
        (
            f"El mundo de los negocios familiares y el emprendimiento compartido puede convertirse en el terreno más pantanoso para la lealtad personal, y hoy analizamos los sucesos de {topic} donde la ambición corporativa quebró lazos fraternos para siempre. "
            "Cuando un proyecto empresarial comienza a generar beneficios sustanciales y consolidar un prestigio en el mercado, las tentaciones de usurpar el control y traicionar la confianza de los socios fundadores emergen con una fuerza destructiva implacable. "
            "Acompáñanos a examinar tres casos reales de gran crudeza donde socios, hermanos y primos tuvieron que enfrentar demandas judiciales, auditorías forenses y el repudio familiar para defender sus creaciones intelectuales y el capital invertido con su propio sudor. "
            "Analizaremos cada situación desde la óptica de quienes supieron mantener la cabeza fría en medio de la traición y acudir a los tribunales mercantiles para proteger su dignidad profesional y su futuro financiero. "
            "A través de estos relatos exploraremos cómo la envidia comercial y el derecho adquirido malentendido pueden transformar sociedades mercantiles exitosas en auténticos campos de batalla legal. "
            "La cuestión central que nos convoca hoy es si los lazos de consanguinidad deben ser un atenuante o un agravante moral cuando un socio familiar decide desviar activos corporativos a espaldas de sus propios hermanos o primos fundadores."
        ),
        (
            "El primer caso de esta jornada nos adentra en la fundación de una agencia de diseño industrial y desarrollo de software creada desde cero por dos primos hermanos. "
            "El protagonista aportó la totalidad del capital semilla con los ahorros de sus primeros empleos, redactó los códigos de programación de las aplicaciones propietarias y registró las patentes industriales iniciales a su nombre como inventor legítimo. "
            "Su socio primo, por su parte, asumió las tareas de prospección comercial y relaciones públicas con clientes corporativos locales, recibiendo un salario fijo y el cincuenta por ciento de los dividendos anuales devengados. "
            "Sin embargo, al cuarto año de actividad, cuando la empresa firmó un contrato multimillonario con una multinacional de telecomunicaciones, el primo aprovechó un viaje de negocios del protagonista para ejecutar una maniobra rastrera: "
            "'He constituido una sociedad mercantil unipersonal a nombre de mi esposa y he transferido a ella la titularidad de los contratos comerciales con los clientes principales, de modo que a partir de hoy tu participación queda reducida al diez por ciento simbólico'. "
            "El cinismo con el que justificó la traición delante de la familia fue escalofriante: "
            "'Los clientes firman conmigo porque yo tengo los contactos comerciales; tú solo eres el técnico que programa en la sombra, así que confórmate con lo que te ofrezco si no quieres que la empresa se disuelva sin un centavo'. "
            "La arrogancia del socio infiel encendió una disputa familiar de magnitudes sísmicas que dividió a tíos y abuelos en dos bandos irreconciliables."
        ),
        (
            "En lugar de dejarse intimidar por las bravuconadas de su pariente, el protagonista actuó con la precisión quirúrgica de quien conoce a fondo el derecho mercantil y la propiedad intelectual. "
            "Contrató a un equipo de peritos forenses informáticos que certificaron notarialmente el vaciado de bases de datos, los registros de acceso a servidores privados y la correspondencia mercantil cruzada con la multinacional contratante. "
            "Interpuso de inmediato una querella criminal por apropiación indebida, revelación de secretos industriales y administración desleal, solicitando medidas cautelares de bloqueo de cuentas societarias y embargo preventivo de bienes conyugales de su primo. "
            "Al verse cercado por la justicia penal y enfrentarse a penas de prisión efectiva por delitos corporativos graves, el primo infiel intentó recurrir al perdón familiar pidiendo que retirara la demanda 'por el honor de los abuelos fallecidos'. "
            "El protagonista no cedió ni un solo milímetro: exigió la liquidación judicial completa de la sociedad usurpada, la indemnización por daños y perjuicios comerciales y la devolución íntegra de la cartera de clientes bajo amenaza de ejecución de sentencia penal. "
            "El juzgado de lo mercantil condenó al primo infiel al pago de una suma millonaria y a la inhabilitación especial para administrar sociedades mercantiles durante diez años, restituyendo la propiedad de los códigos al verdadero creador. "
            "Este primer dilema deja en claro que en los negocios no hay espacio para la ingenuidad y que traicionar a un socio de sangre debe pagarse con el rigor más implacable de la ley mercantil."
        ),
        (
            "El segundo caso aborda la intromisión destructiva de unos padres que intentaron forzar la entrega del capital de una próspera cadena de panaderías artesanales a su hijo mayor desempleado. "
            "El hermano menor, tras formarse en escuelas de pastelería europeas y trabajar dieciséis horas diarias durante siete años, había logrado abrir tres locales comerciales con gran éxito de ventas y estabilidad financiera. "
            "El hermano mayor, por el contrario, acumulaba fracasos comerciales consecutivos por su afición al juego y su negativa sistemática a cumplir horarios laborales regulares. "
            "En una comida familiar navideña, el padre exigió formalmente al protagonista que nombrara a su hermano mayor director general adjunto con un salario idéntico y que le transfiriera el cuarenta por ciento del capital social de la empresa: "
            "'Tu hermano necesita una posición de prestigio para rehacer su reputación y conseguir un crédito bancario; no puedes ser tan miserable de negarle la entrada en un negocio que lleva el apellido de nuestra familia'. "
            "Cuando el protagonista se negó rotundamente alegando que la gestión de alimentos perecederos exige disciplina militar y que no arriesgaría el sueldo de sus treinta trabajadores, los padres amenazaron con desheredarlo y montar un boicot público entre sus amistades. "
            "La presión escaló hasta el punto de que el hermano mayor se presentó en uno de los locales comerciales intentando ordenar a los empleados y retirar dinero de las cajas registradoras alegando ser propietario moral del negocio."
        ),
        (
            "En el segundo caso, el protagonista demostró que la lealtad profesional hacia sus empleados y clientes estaba por encima de cualquier chantaje filial injusto. "
            "Instaló cámaras de videovigilancia de alta definición en todos los obradores, contrató seguridad privada para custodiar los puntos de venta y emitió órdenes estrictas de prohibición de acceso al hermano mayor bajo advertencia de denuncia por allanamiento mercantil. "
            "Asimismo, blindó los estatutos de la sociedad mercantil mediante un protocolo de empresa familiar redactado por notarios especializados, donde se estipulaba que ningún pariente consanguíneo podría acceder a cargos directivos sin una licenciatura acreditada y cinco años de experiencia externa demostrable. "
            "Al comprobar que el muro societario era inexpugnable y que el protagonista no dudaría en hacer detener a su propio hermano si intentaba cruzar las puertas de los obradores, los padres tuvieron que capitular en sus exigencias extorsivas. "
            "A pesar del costo emocional que supuso distanciarse de sus padres, la cadena de panaderías continuó expandiéndose con éxito, inaugurando dos nuevos obradores en la capital provincial y manteniendo intacta su solvencia laboral. "
            "Esta contundente resolución demuestra que mezclar el sentimentalismo familiar con la administración de empresas con empleados a cargo es la fórmula más segura para conducir cualquier proyecto comercial a la quiebra absoluta. "
            "La firmeza en defender la profesionalidad empresarial es un deber ineludible que salva puestos de trabajo legítimos frente a la codicia de parientes ociosos."
        ),
        (
            "En el tercer caso de esta crónica empresarial, el conflicto se desató cuando una diseñadora de joyas artesanales descubrió que su propia hermana menor vendía copias falsificadas de sus creaciones a través de plataformas digitales extranjeras. "
            "La protagonista había dedicado una década a investigar técnicas tradicionales de filigrana en plata, logrando posicionar su marca en pasarelas de moda internacionales y galerías de arte de prestigio. "
            "La hermana menor, que trabajaba temporalmente como dependienta en el taller de fundición, sustrajo los moldes de caucho y los catálogos de proveedores exclusivos para encargar réplicas baratas en aleaciones de baja calidad a talleres clandestinos. "
            "Cuando los clientes internacionales comenzaron a recibir piezas defectuosas que causaban alergias dermatológicas severas y la marca fue amenazada con demandas colectivas por fraude al consumidor, la protagonista contrató peritajes de compra misteriosa para rastrear el origen de las falsificaciones. "
            "El rastreo digital reveló que la administradora de la tienda pirata era su propia hermana menor, quien justificó su conducta ante la madre alegando que 'la propiedad intelectual no existe entre hermanos y que ella tenía derecho a ganarse la vida con las ideas de la familia'. "
            "La madre, lejos de condenar el delito flagrante de usurpación de marca, exigió a la protagonista que retirara las quejas ante las plataformas de venta digital y que compartiera sus contratos internacionales con la hermana usurpadora para no destruir la armonía navideña."
        ),
        (
            "La resolución del tercer caso fue ejemplar por su rigor y determinación jurídica: la protagonista interpuso una demanda civil por competencia desleal, infracción de derechos de autor y daños reputacionales contra la sociedad pantalla de su hermana. "
            "El tribunal mercantil ordenó el cese inmediato de la comercialización de las piezas pirateadas, la destrucción judicial de todos los moldes sustraídos y el embargo de los ingresos obtenidos ilícitamente a través de las pasarelas de pago extranjeras. "
            "Frente a la condena judicial inapelable, la hermana menor tuvo que declarar la quiebra personal y asumir la vergüenza pública de su mala fe, mientras la madre intentaba vanamente victimizar a la usurpadora ante el resto del círculo familiar. "
            "La protagonista logró restaurar la credibilidad de su marca ante sus distribuidores internacionales mediante certificados de autenticidad con código criptográfico inviolable, salvando su firma de diseño de la destrucción comercial definitiva. "
            "Aunque la relación con su hermana y su madre quedó rota de forma irreversible, la diseñadora aprendió la lección más valiosa de su carrera profesional: la confianza ciega es el mayor enemigo del creador y la propiedad industrial debe custodiarse bajo llave incluso ante la propia sangre. "
            "Este último caso nos enseña que plagiar el trabajo ajeno amparándose en el parentesco familiar es un delito ético y legal que merece el rechazo social más contundente y la condena judicial más severa."
        ),
        (
            "Al reflexionar sobre estos tres litigios mercantiles intrafamiliares, queda en evidencia que los negocios exigen reglas racionales, auditorías permanentes y estructuras societarias blindadas que no admitan excepciones afectivas. "
            "La ilusión de que la confianza familiar sustituye la necesidad de contratos mercantiles detallados y pactos de socios protocolizados es la causa principal de la ruina de miles de pequeñas y medianas empresas en todo el mundo. "
            "Los abogados corporativos más experimentados advierten que todo negocio con familiares debe estructurarse asumiendo desde el primer día que los socios pueden convertirse en adversarios judiciales en caso de discrepancias económicas graves. "
            "Firmar acuerdos notariales claros, delimitar las funciones laborales de cada integrante y someter las cuentas a auditorías externas anuales es la única fórmula que protege simultáneamente el capital del negocio y la supervivencia de los afectos personales. "
            "La claridad en las reglas mercantiles no es desconfianza, sino la muestra más elevada de respeto hacia el esfuerzo común y hacia las familias de los trabajadores que dependen de la viabilidad de la empresa."
        ),
        (
            "Asimismo, estos testimonios demuestran la importancia vital de no ceder jamás al chantaje de quienes exigen perdón incondicional tras haber cometido actos deliberados de fraude, apropiación indebida o robo de propiedad intelectual. "
            "El perdón auténtico exige la restitución íntegra del daño causado, el reconocimiento público de la culpa y la aceptación voluntaria de las consecuencias jurídicas y comerciales de los propios actos desleales. "
            "Pretender que la víctima de un expolio empresarial olvide el agravio simplemente para mantener las apariencias en comidas familiares es una muestra de hipocresía colectiva que solo perpetúa la impunidad del pariente infractor. "
            "Defender las creaciones propias y el patrimonio societario con todas las armas que la ley pone a nuestro alcance es un acto de valentía y madurez cívica que merece el aplauso y el reconocimiento de toda la comunidad. "
            "Nadie tiene el derecho de beneficiarse de tus talentos ni de tu disciplina empresarial invocando lazos sanguíneos que ellos mismos destruyeron en el instante exacto en que decidieron traicionarte por dinero."
        ),
        (
            "Para concluir este recorrido por las disputas corporativas y las traiciones societarias, queremos invitarte a analizar cómo manejas los acuerdos comerciales y profesionales en tu propio entorno familiar. "
            "¿Has tenido alguna vez que emprender acciones legales o poner límites contractuales estrictos a un familiar que intentó aprovecharse de tus proyectos o de tus inversiones? "
            "¿Consideras que actuaron con justicia nuestros tres protagonistas al llevar a sus propios parientes a los tribunales para defender sus patentes, sus empresas y sus marcas artesanales? "
            "Recordar que tus creaciones y tu patrimonio son el fruto de tu ingenio y de tu perseverancia te dará la fuerza necesaria para no ceder ante chantajes afectivos vacíos de moral. "
            "Caminar por la vida con la tranquilidad de haber actuado con honradez intachable y con la firmeza de haber defendido tu trabajo es la mayor satisfacción que un profesional íntegro puede alcanzar. "
            "Ningún lazo familiar disfuncional justifica la destrucción de tus proyectos empresariales construidos con tanta pasión y rectitud."
        ),
        (
            "En el primer caso, la querella penal restituyó el control de las aplicaciones tecnológicas al verdadero programador, castigando la soberbia comercial del primo desleal. "
            "En el segundo caso, el protocolo de empresa familiar salvaguardó los obradores de panadería frente a la incompetencia del hermano mayor consentido por sus padres. "
            "Y en el tercer caso, la demanda por competencia desleal limpió el nombre de la firma de joyería artesanal frente al plagio premeditado de la hermana menor usurpadora. "
            "Estas tres victorias jurídicas incontestables demuestran que la ley mercantil es el mejor escudo protector para quienes emprenden con decencia, disciplina y respeto irrestricto hacia la verdad. "
            "Que estas lecciones sirvan como inspiración y advertencia para todos los emprendedores que hoy forjan su destino en el competitivo mundo de los negocios familiares."
        ),
        (
            "Agradecemos de corazón la generosidad de los profesionales que nos han confiado sus testimonios confidenciales para abrir los ojos a otros creadores frente a la traición societaria. "
            "El debate sobre la propiedad intelectual, los protocolos de empresa familiar y los límites éticos en los negocios continuará abierto en nuestra comunidad para todos aquellos que valoran el mérito, la innovación y la justicia."
        ),
        (
            "Como lección adicional sobre la prevención de litigios mercantiles en empresas fundadas por parientes, los peritos contables recomiendan instaurar una auditoría externa independiente cada seis meses. "
            "Cuando las cifras de facturación y los márgenes de beneficio quedan expuestos con absoluta transparencia ante auditores colegiados ajenos al clan familiar, las suspicacias y los intentos de desvío de fondos se reducen de forma drástica. "
            "Asimismo, la figura de los consejeros independientes en los órganos de administración de las sociedades familiares aporta una mirada objetiva y profesional que evita que las tensiones afectivas contaminen las decisiones comerciales estratégicas. "
            "Separar la mesa de los domingos del consejo de administración societario es la regla de oro que garantiza la continuidad generacional de cualquier empresa próspera y saludable."
        ),
        (
            "Por último, resulta indispensable recalcar que la protección de la propiedad intelectual mediante patentes registradas, marcas comerciales oficiales y depósitos de código fuente ante notario debe realizarse con anterioridad a cualquier lanzamiento comercial. "
            "Confiar en acuerdos verbales o asumir que la hermandad evitará el plagio de ideas innovadoras es una temeridad que cuesta la ruina a miles de diseñadores y programadores cada año. "
            "El registro legal no es un acto de hostilidad hacia la familia, sino el trámite técnico indispensable para certificar ante el mundo la autoría legítima de una obra intelectual o de un invento comercial. "
            "Quien respeta verdaderamente tu trabajo aplaudirá que blindes tus patentes, mientras que quien se ofende por tus medidas de protección legal probablemente estaba albergando intenciones ocultas de apropiarse de tus frutos profesionales sin pagar el precio justo."
        ),
    ]
    return "\n\n".join(p.strip() for p in paragraphs)


def build_aelithia_business_betrayal(topic: str, **kwargs: Any) -> str:
    s = get_business_story(topic)
    extra = [
        (
            "Al analizar la psicología de los usurpadores corporativos en el seno familiar, los psicólogos organizacionales identifican una marcada tendencia al narcisismo encubierto. "
            "Estos individuos suelen convencerse a sí mismos de que el éxito ajeno se debe a la suerte o a privilegios inmerecidos, justificando internamente sus actos de expolio como un acto de justicia poética o reequilibrio histórico. "
            "Cuando son descubiertos y confrontados con pruebas documentales irrefutables, rara vez muestran arrepentimiento sincero; en su lugar, adoptan el papel de víctimas agraviadas y manipulan a los parientes más vulnerables para que presionen al emprendedor legítimo. "
            "Aprender a no caer en la trampa de la compasión mal entendida y sostener las acciones judiciales hasta sus últimas consecuencias es la única manera de desmantelar este patrón de abuso psicológico y patrimonial."
        ),
        (
            "Como conclusión para todos los profesionales que integran nuestra comunidad, compartimos tres recomendaciones prácticas para operar con seguridad en cualquier sociedad mercantil familiar. "
            "Primero, nunca aceptes participaciones verbales: todo aporte de capital, trabajo o tecnología debe quedar plasmado en escrituras públicas con porcentajes societarios rigurosamente definidos. "
            "Segundo, establece cláusulas de salida y de compra preferente que permitan disolver la sociedad o expulsar a un socio desleal sin paralizar la actividad productiva de la empresa. "
            "Y tercero, mantén una cuenta bancaria personal totalmente separada de las finanzas de la empresa, evitando avales solidarios que puedan poner en peligro la vivienda de tu propia familia en caso de litigio societario. "
            "La libertad y el éxito empresarial se conquistan con trabajo honesto, pero se defienden con prudencia legal, determinación inquebrantable y límites afectivos infranqueables."
        ),
    ]
    return s + "\n\n" + "\n\n".join(p.strip() for p in extra)

def get_eldercare_story(topic: str) -> str:
    paragraphs = [
        (
            f"El cuidado de los adultos mayores y la gestión de las últimas voluntades representan la prueba definitiva de la catadura moral de una familia, y hoy analizamos los sucesos de {topic} donde la codicia por las herencias desató batallas despiadadas. "
            "Cuando los abuelos o los padres envejecen y requieren atenciones médicas continuadas, cuidados paliativos y compañía constante, la mayoría de los familiares suelen desaparecer misteriosamente, dejando la carga sobre los hombros del miembro más empático y generoso del clan. "
            "Sin embargo, apenas el anciano fallece y se abre el testamento ante notario público, los mismos parientes ausentes regresan como buitres rapaces exigiendo partes iguales de un patrimonio que jamás se preocuparon por sostener ni cuidar en vida. "
            "Acompáñanos a examinar tres testimonios conmovedores donde cuidadores abnegados tuvieron que defender la memoria de sus seres queridos y su propia dignidad frente al asedio carroñero de hermanos y tíos que nunca aportaron un solo día de ayuda. "
            "Analizaremos cada encrucijada desde la perspectiva de quienes supieron anteponer el amor y el deber filial durante años, pero supieron también decir basta frente al cinismo de quienes reclaman derechos sin haber asumido deber alguno. "
            "La pregunta fundamental que nos interpela hoy es si la herencia material debe ser un premio automático por consanguinidad biológica o una compensación justa hacia quien sostuvo la vida y la dignidad del anciano en sus momentos de mayor desamparo y vulnerabilidad."
        ),
        (
            "El primer caso de esta conmovedora serie nos traslada al hogar de un abuelo de ochenta y siete años aquejado de demencia senil y movilidad reducida tras sufrir un derrame cerebral. "
            "Nuestra protagonista, una nieta que postergó sus estudios de posgrado y redujo su jornada laboral a media jornada, asumió en solitario el cuidado integral del anciano durante seis largos años ininterrumpidos en su casa familiar. "
            "Le cambiaba los pañales, administraba la medicación geriátrica en horarios estrictos, lo acompañaba a las visitas hospitalarias semanales y le brindaba el cariño que sus propios hijos le negaban sistemáticamente. "
            "Durante ese sexenio de sacrificios diarios, los dos tíos directos de la joven nunca se presentaron en la vivienda para relevarla un solo fin de semana, ni aportaron un solo céntimo para los gastos farmacéuticos o de alimentación especial. "
            "Sin embargo, a los tres días de celebrarse el funeral del anciano, los dos tíos se presentaron sin cita previa en la vivienda acompañados de un perito tasador inmobiliario, exigiendo la venta inmediata del inmueble: "
            "'Hemos venido a valorar la casa porque queremos cobrar nuestra parte legítima de la herencia sin dilaciones; tú ya viviste gratis aquí durante seis años, así que empaca tus maletas y desaloja en un plazo máximo de dos semanas'. "
            "La frialdad despiadada con la que trataron a la mujer que había cuidado a su propio padre hasta el último aliento dejó al descubierto la peor miseria humana."
        ),
        (
            "Lo que los codiciosos tíos ignoraban por completo era que el abuelo, dos años antes de que su deterioro cognitivo avanzara de forma irreversible y contando con un dictamen médico oficial de perfecta lucidez mental, había acudido al notario principal de la ciudad. "
            "En un testamento abierto redactado ante tres testigos independientes de reconocida honorabilidad, el anciano había legado el tercio de libre disposición y el tercio de mejora de la casa exclusivamente a su nieta cuidadora, dejando para sus hijos ausentes únicamente la legítima estricta reducida al mínimo legal permitido por el código civil. "
            "Asimismo, había suscrito un contrato de alimentos y cuidados vitalicios con su nieta debidamente inscrito en el registro de la propiedad, reconociendo el valor económico de las atenciones recibidas y compensándolas con la adjudicación preferente del pleno dominio del inmueble. "
            "Cuando el notario leyó las disposiciones testamentarias ante los tíos estupefactos, el despacho se convirtió en un volcán de alaridos, acusaciones de manipulación mental y amenazas de impugnación judicial por supuesta captación de voluntad. "
            "La nieta mantuvo una serenidad inquebrantable, exhibiendo los diarios de cuidado, los informes médicos periódicos y los comprobantes bancarios donde constaba que ella había costeado la totalidad de los gastos geriátricos con sus propios ahorros. "
            "El juez de primera instancia desestimó de plano la demanda de impugnación de los tíos con condena en costas procesales por temeridad evidente, blindando el derecho de la nieta a residir en la casa que cuidó con tanta devoción. "
            "Este primer dilema demuestra con contundencia que la ley y la justicia recompensan la gratitud auténtica frente a la codicia carroñera de parientes oportunistas."
        ),
        (
            "El segundo caso aborda el chantaje moral al que fue sometido un hermano menor que asumió el cuidado de su madre enferma de cáncer terminal durante tres años ininterrumpidos en el pueblo natal. "
            "Los dos hermanos mayores, que residían cómodamente en la capital trabajando como ejecutivos bancarios, se limitaban a enviar llamadas telefónicas mensuales de cinco minutos para preguntar 'cómo seguía mamá', sin aportar dinero ni presencias físicas. "
            "Tras el doloroso desenlace y la cremación de la madre, se descubrió que la difunta había donado en vida al hermano cuidador una finca rústica de olivos centenarios que había pertenecido a la familia durante tres generaciones. "
            "La donación había sido formalizada en escritura pública con dispensa expresa de colación hereditaria, como agradecimiento explícito de la madre por los sacrificios personales y la renuncia profesional de su hijo menor. "
            "Apenas se enteraron de la donación de los olivos, los dos hermanos ejecutivos contrataron a un despacho de abogados litigantes para asediar al cuidador con demandas de rescisión por fraude de acreedores y nulidad de donación: "
            "'Exigimos que devuelvas la finca a la masa hereditaria para repartirla entre los tres a partes iguales, o de lo contrario te acusaremos penalmente de haberte apropiado de la pensión de viudedad de nuestra madre durante sus últimos meses de vida'. "
            "La infamia de la acusación golpeó al protagonista en lo más profundo de su orgullo filial, haciéndolo revivir el dolor de la pérdida materna bajo una pesadilla de citaciones judiciales."
        ),
        (
            "En el segundo caso, el hermano menor demostró que la honestidad y la pulcritud administrativa son las mejores defensas frente al odio intrafamiliar más encarnizado. "
            "Había guardado en carpetas clasificadas cada ticket de farmacia, cada factura de oxígeno medicinal y cada extracto bancario de la cuenta de su madre desde el primer día del diagnóstico oncológico, acreditando documentalmente que hasta el último euro de la pensión había sido invertido íntegramente en la salud y el confort de la enferma. "
            "Asimismo, aportó ante el tribunal las cartas manuscritas que su madre le entregó en vida donde expresaba su voluntad explícita de premiar a quien no la había abandonado en la etapa más oscura de su vida terrenal. "
            "El tribunal provincial desestimó íntegramente la demanda de los hermanos mayores, declarando la plena validez de la donación de los olivos y condenando a los demandantes por litigiosidad abusiva y temeraria. "
            "Al verse derrotados en sede judicial, los ejecutivos intentaron buscar una reconciliación forzada aduciendo que 'la familia debe perdonar los malos momentos y mantenerse unida por la memoria de mamá'. "
            "El protagonista cerró la puerta con serenidad absoluta: les entregó las cenizas maternas que les correspondían y les notificó formalmente que no deseaba volver a verlos ni escuchar sus voces durante el resto de sus días. "
            "Esta valiente actitud enseña que perdonar no significa permitir que los agresores sigan formando parte de tu vida y que alejarse de parientes carroñeros es el único camino para honrar la paz de quienes nos amaron con autenticidad."
        ),
        (
            "En el tercer caso que examinamos hoy, el conflicto surgió en torno a la venta forzosa de la vivienda de una tía soltera sin descendencia directa que fue acogida en su vejez por una sobrina predilecta. "
            "La tía vivió durante ocho años en el hogar de la sobrina, recibiendo cuidados integrales, integración afectiva con sus sobrinos nietos y una vejez colmada de dignidad y sonrisas. "
            "En su testamento notarial, la anciana instituyó heredera universal de su departamento urbano a la sobrina acogedora, dejando legados económicos menores para los restantes diez sobrinos de la familia extensa. "
            "Cuando la anciana falleció a los noventa y dos años de edad, los diez primos restantes formaron un frente común de presión encabezado por un tío político que administraba una agencia de préstamos: "
            "'Es una vergüenza que te quedes con un piso entero mientras nosotros apenas recibimos una miseria; o firmas un acuerdo privado para repartir el valor del departamento entre los once primos a partes iguales, o iniciaremos una campaña de desprestigio en tu contra en toda la comarca'. "
            "La sobrina recibió llamadas amenazantes a altas horas de la madrugada, pintadas insultantes en la fachada de su negocio local y falsas denuncias anónimas ante los servicios sociales acusándola de haber maltratado a la anciana en sus últimos meses. "
            "El acoso colectivo buscaba quebrar su resistencia emocional para forzarla a ceder el cincuenta por ciento de los bienes antes de que el testamento fuera ejecutado registralmente en la oficina de hipotecas."
        ),
        (
            "La resolución del tercer caso fue contundente: la sobrina no solo se negó a firmar acuerdo alguno bajo coacción, sino que interpuso una querella criminal por coacciones continuadas, amenazas graves y calumnias con publicidad contra el tío promotor y los tres primos más agresivos de la trama. "
            "La policía judicial recabó las grabaciones de los mensajes de audio amenazantes y los testimonios de los vecinos del vecindario que certificaban el trato exquisito y amoroso que la tía recibió durante toda su estancia en el hogar de la sobrina. "
            "El juzgado penal impuso órdenes de alejamiento estrictas contra los cabecillas de la trama de extorsión y les fijó fianzas de responsabilidad civil para garantizar la indemnización por los daños morales causados a la protagonista y a sus hijos menores. "
            "Frente a la contundencia de las medidas judiciales penales, el resto de los primos se apresuró a desmarcarse de la trama y aceptar sus legados testamentarios sin rechistar, dejando al cabecilla extorsionador aislado ante su propia condena penal. "
            "La sobrina inscribió el departamento a su nombre y lo destinó a vivienda habitual para su propia hija universitaria, perpetuando el legado de amor y generosidad que su tía soltera quiso dejar para las nuevas generaciones de su estirpe. "
            "Este último caso nos demuestra que frente a la intimidación de las manadas familiares carroñeras no cabe la sumisión ni la tibieza, sino la aplicación estricta de las leyes penales para proteger nuestro honor y el cumplimiento de las voluntades de quienes confiaron en nosotros."
        ),
        (
            "Al analizar en conjunto estos tres testimonios sobre el cuidado de los ancianos y las disputas sucesorias, resalta con claridad meridiana una lección fundamental de justicia distributiva: los derechos hereditarios legítimos deben ser interpretados a la luz de los deberes cumplidos. "
            "Las legislaciones sucesorias modernas avanzan decididamente hacia la ampliación de la libertad de testar, permitiendo que las personas mayores puedan desheredar justamente a aquellos descendientes que incurrieron en abandono afectivo o material continuado durante su ancianidad. "
            "El maltrato psicológico que supone el desamparo de un progenitor en su vejez es una causa moralmente incontrovertible para privar de cualquier beneficio económico a quien prefirió la comodidad del olvido frente al sacrificio del cuidado diario. "
            "Quien no estuvo presente para secar las lágrimas, limpiar las heridas o sostener la mano temblorosa de un anciano en la soledad de un hospital, no tiene legitimidad moral para cruzar el umbral del notario exigiendo las llaves de su vivienda."
        ),
        (
            "Asimismo, estas experiencias subrayan la imperiosa necesidad de que los cuidadores familiares aprendan a protegerse jurídicamente desde el primer instante en que asumen la responsabilidad del cuidado de un adulto mayor dependiente. "
            "Documentar los gastos mediante facturas oficiales, conservar los historiales médicos detallados y formalizar ante notario las voluntades del anciano mientras este conserve plenamente sus facultades cognitivas no es egoísmo: es un acto de prudencia indispensable para blindar la verdad frente a futuras calumnias intrafamiliares. "
            "Los parientes que abandonan a los ancianos en vida son exactamente los mismos que acudirán con abogados agresivos tras el entierro para impugnar cualquier acto de justicia que premie al cuidador generoso. "
            "Actuar con rigor documental y transparencia legal es la única garantía de que los últimos deseos de nuestros seres queridos serán respetados escrupulosamente contra la rapiña de los herederos ausentes."
        ),
        (
            "Para concluir este emotivo recorrido por los dilemas del cuidado filial y las batallas sucesorias, queremos invitarte a reflexionar sobre cómo tratas a los adultos mayores que forman parte de tu propio círculo familiar. "
            "¿Estás presente en la vida cotidiana de tus padres o abuelos ancianos, o eres de los que esperan que otros asuman el esfuerzo diario para luego reclamar derechos sobre la herencia futura? "
            "¿Consideras que actuaron con rectitud nuestros tres protagonistas al defender hasta las últimas consecuencias legales las disposiciones testamentarias que premiaron su entrega y sacrificio? "
            "Cuidar a quien nos dio la vida o a quien nos acogió en la infancia es el acto más noble y sagrado que un ser humano puede consumar en su tránsito terrenal. "
            "Defender ese legado frente a la avaricia ajena no es una muestra de codicia, sino la confirmación más elevada de lealtad hacia la memoria de quienes se marcharon dejándonos su bendición y su confianza más profunda."
        ),
        (
            "En el primer caso, la nieta aseguró la casa donde cuidó al abuelo gracias a las cláusulas de mejora y alimentos vitalicios blindadas ante notario. "
            "En el segundo caso, el hermano menor custodió los olivos centenarios gracias al archivo escrupuloso de cada gasto médico incurrido durante la enfermedad de su madre. "
            "Y en el tercer caso, la querella penal protegió el departamento urbano heredado frente a la extorsión coordinada de diez primos carroñeros que nunca visitaron a la anciana tía. "
            "Estas tres victorias morales y judiciales demuestran que la decencia, la generosidad y el amor filial genuino prevalecen frente a la bajeza de quienes buscan enriquecerse sin haber doblado la espalda jamás por sus mayores. "
            "Que estos testimonios sirvan como inspiración y fortaleza para todos los cuidadores abnegados que hoy dedican sus días a acompañar a nuestros ancianos con amor y dignidad infinita."
        ),
        (
            "Agradecemos profundamente el testimonio de todos los cuidadores que nos han enviado sus historias confidenciales para dar voz a una realidad que a menudo permanece silenciada en la intimidad de los hogares. "
            "El debate sobre el cuidado de los ancianos, las herencias y el derecho a testar con plena libertad continuará abierto en nuestra comunidad para todos aquellos que valoran el amor, la justicia y la dignidad humana."
        ),
        (
            "Como orientación legal práctica para quienes cuidan a familiares dependientes, los notarios aconsejan formalizar un poder preventivo o un protocolo de autotutela antes de que aparezcan los primeros síntomas de deterioro neurodegenerativo. "
            "Este instrumento notarial permite al anciano designar de forma anticipada quién será la persona autorizada para gestionar su patrimonio y sus decisiones médicas cuando pierda su capacidad de obrar. "
            "Asimismo, la figura de la donación con reserva de usufructo vitalicio permite transmitir la titularidad de los bienes al cuidador mientras el anciano conserva el derecho exclusivo a residir en su vivienda hasta su fallecimiento. "
            "Adoptar estas precauciones legales con suficiente antelación es el único medio eficaz para evitar que los herederos ausentes paralicen judicialmente las cuentas bancarias o intenten incapacitar al anciano de forma fraudulenta."
        ),
        (
            "Por último, los terapeutas especializados en duelo familiar recomiendan a los cuidadores establecer un cerco emocional inquebrantable frente a las agresiones verbales de los parientes que reaparecen tras el sepelio. "
            "El rencor de los familiares que abandonaron a sus mayores no proviene de una legítima sed de justicia, sino del peso insoportable de su propia culpa proyectada contra quien sí estuvo a la altura del deber moral. "
            "No malgastes tu energía intentando convencer a quien eligió la cobardía del desapego; conserva en tu corazón la mirada de paz de quien despidió a su ser querido sabiendo que nunca le faltó un abrazo sincero en sus horas finales. "
            "Esa paz interior es la herencia invisible e indestructible que ningún tribunal de justicia ni ningún pariente avaricioso podrá arrebatarte jamás."
        ),
    ]
    return "\n\n".join(p.strip() for p in paragraphs)


def build_aelithia_eldercare_will(topic: str, **kwargs: Any) -> str:
    s = get_eldercare_story(topic)
    extra = [
        (
            "Al reflexionar sobre las dinámicas sociales del envejecimiento en nuestra sociedad, constatamos que el abandono de los ancianos es una de las mayores sombras morales de nuestro tiempo. "
            "El individualismo extremo empuja a muchos descendientes a desentenderse de sus progenitores cuando estos dejan de ser productivos o requieren atenciones que incomodan su estilo de vida urbano. "
            "Sin embargo, esa misma comodidad se esfuma en cuanto se percibe la posibilidad de obtener una ganancia económica inmediata mediante la liquidación de las propiedades familiares acumuladas durante décadas de esfuerzo honrado. "
            "La codicia ciega a quienes jamás supieron valorar las manos encallecidas que construyeron su propia infancia, llevándolos a cometer las mayores bajezas contra sus propios hermanos de sangre."
        ),
        (
            "Para concluir el análisis de estos tres casos conmovedores, queremos dejar tres reflexiones esenciales para todos los oyentes de nuestra comunidad. "
            "Primero, honra a quien te cuidó y acompáñalo en su vejez con presencia real, porque el tiempo que se escapa no vuelve jamás. "
            "Segundo, si eres el cuidador principal de un familiar dependiente, no permitas que la timidez te impida blindar legalmente las voluntades y los recursos necesarios para garantizar una vejez digna y tranquila. "
            "Y tercero, mantén siempre la cabeza alta frente a las críticas de quienes solo aparecen para criticar o exigir herencias: tu conciencia limpia vale infinitamente más que cualquier aprobación hipócrita de parientes desleales. "
            "El amor verdadero se demuestra con hechos diarios, con sacrificio constante y con una lealtad incondicional que trasciende las fronteras materiales de este mundo."
        ),
    ]
    return s + "\n\n" + "\n\n".join(p.strip() for p in extra)


# =============================================================================
# DISPATCHER LISTS AND FUNCTIONS
# =============================================================================

from src.templates.longform_stories_ext import (
    build_moku_deepsea,
    build_moku_asylum,
    build_moku_observatory,
    build_moku_saltmine,
)

MOKU_STORIES: List[Callable[..., str]] = [
    build_moku_mountain_radio,     # Story 0: Radio station (existing gold standard)
    build_moku_bunker,             # Story 1: Subterranean research bunker
    build_moku_lighthouse,         # Story 2: Black Reef offshore lighthouse
    build_moku_rail,               # Story 3: Northern taiga rail signal station
    build_moku_deepsea,            # Story 4: Mariana Trench bathyscaphe expedition
    build_moku_asylum,             # Story 5: Abandoned Blackwood Sanatorium night guard
    build_moku_observatory,        # Story 6: High-altitude Svalbard Arctic observatory
    build_moku_saltmine,           # Story 7: Ancient salt mine crypt & seismic station
]

AELITHIA_STORIES: List[Callable[..., str]] = [
    build_aelithia_family_debt,       # Story 0: Birthday loan & sibling fraud (existing)
    build_aelithia_wedding_house,     # Story 1: Wedding & house down payment extortion
    build_aelithia_business_betrayal, # Story 2: Business partnership & patent theft
    build_aelithia_eldercare_will,    # Story 3: Eldercare abandonment & estate vultures
]


def get_moku_longform_story(topic: str, index: int | None = None, **kwargs: Any) -> str:
    """Returns a diverse longform story for Moku horror channel, strictly avoiding recent publication collisions."""
    recent_texts = kwargs.get("recent_texts")
    if not recent_texts:
        try:
            from src.core.repository import QueueRepository
            from src.config import DEFAULT_DB_PATH
            recent_texts = QueueRepository(DEFAULT_DB_PATH).recent_published_texts("moku")
        except Exception:
            recent_texts = ()

    if index is not None:
        start_idx = index % len(MOKU_STORIES)
    elif "La Estación de Radio Olvidada" in topic or "radio" in topic.lower():
        start_idx = 0
    else:
        seed = kwargs.get("seed")
        if seed is not None:
            start_idx = int(seed) % len(MOKU_STORIES)
        else:
            h = int(hashlib.md5(topic.encode("utf-8")).hexdigest()[:8], 16)
            start_idx = h % len(MOKU_STORIES)

    from src.core.quality import text_similarity

    best_story = ""
    min_sim = 1.0

    for offset in range(len(MOKU_STORIES)):
        cand_idx = (start_idx + offset) % len(MOKU_STORIES)
        candidate = MOKU_STORIES[cand_idx](topic, **kwargs)
        if not recent_texts:
            return candidate
        max_sim = max((text_similarity(candidate, prev) for prev in recent_texts), default=0.0)
        if max_sim < 0.70:
            return candidate
        if max_sim < min_sim:
            min_sim = max_sim
            best_story = candidate

    return best_story or MOKU_STORIES[start_idx](topic, **kwargs)


def get_aelithia_longform_story(topic: str, index: int | None = None, **kwargs: Any) -> str:
    """Returns a diverse longform story for Aelithia drama channel, strictly avoiding recent publication collisions."""
    recent_texts = kwargs.get("recent_texts")
    if not recent_texts:
        try:
            from src.core.repository import QueueRepository
            from src.config import DEFAULT_DB_PATH
            recent_texts = QueueRepository(DEFAULT_DB_PATH).recent_published_texts("aelithia")
        except Exception:
            recent_texts = ()

    if index is not None:
        start_idx = index % len(AELITHIA_STORIES)
    elif "El Testamento de la Abuela" in topic:
        start_idx = 0
    else:
        seed = kwargs.get("seed")
        if seed is not None:
            start_idx = int(seed) % len(AELITHIA_STORIES)
        else:
            h = int(hashlib.md5(topic.encode("utf-8")).hexdigest()[:8], 16)
            start_idx = h % len(AELITHIA_STORIES)

    from src.core.quality import text_similarity

    best_story = ""
    min_sim = 1.0

    for offset in range(len(AELITHIA_STORIES)):
        cand_idx = (start_idx + offset) % len(AELITHIA_STORIES)
        candidate = AELITHIA_STORIES[cand_idx](topic, **kwargs)
        if not recent_texts:
            return candidate
        max_sim = max((text_similarity(candidate, prev) for prev in recent_texts), default=0.0)
        if max_sim < 0.70:
            return candidate
        if max_sim < min_sim:
            min_sim = max_sim
            best_story = candidate

    return best_story or AELITHIA_STORIES[start_idx](topic, **kwargs)
