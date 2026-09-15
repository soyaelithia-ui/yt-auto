"""
src/templates/longform_stories_ext.py - Additional storyline library for longform narratives.
Extends Moku (Horror) and Aelithia (Drama / AITA) with 8 additional independent storylines
to guarantee zero duplicate similarity collisions (Jaccard < 0.20) across continuous publications.
"""

from typing import Any, List


def build_moku_deepsea(topic: str, **kwargs: Any) -> str:
    """Story 4: Mariana Trench Abyssal Bathyscaphe Expedition."""
    paragraphs = [
        (
            "Durante las semanas de internamiento posterior en el hospital naval, me dediqué a redactar de memoria un plano esquemático de la nave sepultada y de los bajorrelieves de la fosa. "
            "El análisis acústico preliminar de las grabaciones de frecuencia ultra baja, preservadas milagrosamente en la grabadora analógica de respaldo de mi traje térmico, confirmó que los pulsos sónicos contenían secuencias matemáticas de números primos organizadas en base doce. "
            "Ningún cetáceo conocido ni fenómeno tectónico submarino es capaz de producir frentes de onda con semejante grado de organización sintáctica y modulación de armónicos. "
            "Los biólogos navales con los que logré contactar de forma anónima reconocieron que las muestras biológicas adheridas a los propulsores del batiscafo no presentaban ADN estructurado en doble hélice, sino un polímero autorreplicante con base de silicio y arsénico orgánico. "
            "Aquel descubrimiento aterrador demostraba que en las profundidades abisales coexiste con nosotros una biosfera ancestral, ajena por completo al árbol de la vida conocido en la superficie continental."
        ),
        (
            "Asimismo, la temperatura y salinidad anómalas registradas en la sima sugerían la existencia de conductos hidrotermales que conectaban la fosa con el manto terrestre superior. "
            "Estas chimeneas abisales no expulsan agua sulfurosa hirviente, sino un fluido denso y refrigerado que actúa como refrigerante térmico para la estructura metálica que duerme en el lecho marino. "
            "Cualquier intento futuro de perforar o dinamitar las paredes de la fosa de las Marianas con tecnología de prospección comercial podría desestabilizar ese equilibrio hidrostático milenario y liberar tensiones tectónicas capaces de arrasar las costas del Pacífico. "
            "La prudencia científica debe prevalecer sobre la ambición de notoriedad: los abismos no son un territorio a explotar, sino un santuario geológico que exige ser respetado y temido en igual medida."
        ),
        (
            f"A nueve mil metros bajo la superficie del océano Pacífico, donde la presión hidrostática supera las novecientas atmósferas sobre el titanio, el misterio de {topic} se convirtió en la pesadilla más asfixiante de mi carrera oceanográfica. "
            "Formaba parte del equipo de tripulación técnica del batiscafo de investigación abisal 'Nereo Cuatro', una esfera de aleación reforzada diseñada para explorar la fosa oceánica y tomar testigos sedimentarios en el lecho marino más profundo del planeta. "
            "La cabina esférica apenas medía dos metros de diámetro interior, atestada de racks de instrumentación digital, monitores de sonar batimétrico, depósitos de oxígeno químico y scrubbers de dióxido de carbono. "
            "A nuestro alrededor reinaba una oscuridad absoluta que jamás había sido tocada por un solo fotón de luz solar desde el origen de la Tierra, un abismo gélido a uno punto dos grados centígrados donde el agua posee una densidad casi mineral. "
            "El descenso desde la nave nodriza de superficie había tomado casi cinco horas de caída libre a través de la columna de agua, monitoreando el gemido constante del casco mientras la presión exterior comprimía el metal milímetro a milímetro. "
            "Al posarnos suavemente sobre el fango de diatomeas del lecho abisal, los potentes reflectores de descarga de xenón iluminaron una llanura desolada de sedimentos blancos que se extendía hasta donde la potencia óptica lograba perforar la negrura líquida. "
            "Sin embargo, antes de desplegar el brazo robótico para recolectar las muestras geológicas programadas, el hidrófono de frecuencia ultra baja conectado al mamparo exterior comenzó a registrar una oscilación acústica que no figuraba en ningún manual oceanográfico. "
            "Era un sonido de fricción profunda, rítmico y mastodóntico, como si una masa ciclópea de roca y materia orgánica estuviera reptando pesadamente a menos de cien metros de nuestro batiscafo."
        ),
        (
            "El doctor Arispe, biólogo jefe de la expedición, acercó su rostro a la mirilla cónica de cuarzo de veinte centímetros de espesor, ajustando los prismáticos de visión nocturna hacia el borde este de la trinchera. "
            "Los instrumentos de telemetría acústica mostraban un retorno de señal errático que rebotaba contra una formación vertical que no constaba en las batimetrías satelitales preliminares de la misión. "
            "Encendimos los focos halógenos auxiliares y el haz de luz blanca reveló una pared de basalto fracturado que emergía del fango marino en un ángulo de noventa grados exactos, una anomalía geométrica imposible en un lecho volcánico de subducción tectónica. "
            "Al aproximar el batiscafo utilizando los propulsores eléctricos de maniobra fina, notamos que la superficie de la roca presentaba canales tallados en bajorrelieve formando complejas grecas y círculos concéntricos cubiertos por colonias de gusanos tubulares albinos. "
            "La temperatura del agua en el exterior, registrada por los sensores termoeléctricos del casco, comenzó a descender de forma inexplicable por debajo de cero grados sin llegar a congelarse debido a la monstruosa salinidad del entorno abisal. "
            "Un zumbido electromagnético invadió el circuito de audio interno del intercomunicador, haciendo parpadear las pantallas táctiles del sistema de navegación inercial con un patrón de estática que imitaba ondas cerebrales en estado de vigilia. "
            "El piloto automático abortó la rutina de estabilización y una corriente submarina anómala, cálida y turbulenta, empujó la nave hacia el interior de una garganta rocosa que se abría en el lecho marino como una herida abierta."
        ),
        (
            "Avanzamos cincuenta metros por el interior de la falla submarina con los motores en mínima potencia para evitar golpear los salientes escarpados de basalto que bordeaban el canal. "
            "A ambos lados del casco, las formaciones minerales presentaban un brillo bioluminiscente propio, una fosforescencia azulada y fría emitida por microorganismos quimiosintéticos que colonizaban las hendiduras de la roca en espirales perfectas. "
            "El doctor Arispe tomó notas apresuradas en su diario digital, señalando que la luz emitida no correspondía al espectro de luciferina conocido en la fauna abisal, sino a una reacción radioluminiscente estimulada por campos magnéticos intensos. "
            "De pronto, el haz de nuestros reflectores principales chocó contra una estructura colosal semienterrada en los sedimentos de la sima: los restos de una embarcación de proporciones descomunales cuyo diseño no pertenecía a ninguna flota militar ni mercante moderna. "
            "El casco de la nave sumergida no presentaba óxido de hierro ni incrustaciones de coral, sino una superficie lisa y oscura similar a vidrio volcánico o cerámica sinterizada que absorbía la luz artificial sin proyectar reflejos nítidos. "
            "Alrededor de la abertura principal de la nave hundida, cientos de cables y conductos flexibles flotaban en el agua inmóvil como algas inertes, mecidos por un vórtice imperceptible que succionaba partículas hacia el interior del pecio. "
            "El indicador de profundidad marcaba nueve mil cuatrocientos veinte metros cuando el transpondedor acústico con el barco nodriza en la superficie se cortó de cuajo con un chasquido sordo en los auriculares."
        ),
        (
            "La pérdida de comunicación acústica con la superficie activó automáticamente el protocolo de aborto y deslastre de emergencia de pesos de plomo para recuperar flotabilidad positiva. "
            "El ingeniero de vuelo accionó las palancas mecánicas de desacoplamiento de las baterías de lastre situadas en la quilla del batiscafo, pero los electroimanes de seguridad no liberaron los bloques metálicos. "
            "El monitor de estado reveló que una sobrecarga inductiva externa había fundido los relés de apertura manual, soldando los pasadores de retención a los alojamientos de soporte. "
            "Estábamos atrapados en el fondo de la fosa más profunda de la Tierra con una reserva de aire para veinticuatro horas y sin capacidad motriz para contrarrestar la atracción de la corriente hacia la nave desconocida. "
            "El doctor Arispe intentó mantener la calma sugiriendo que la corriente podía ser originada por una surgencia hidrotermal o un sumidero volcánico activo en la corteza profunda. "
            "Sin embargo, al enfocar la cámara de alta definición del brazo robótico hacia el vano del casco sumergido, la lente captó el movimiento lento y coordinado de apéndices segmentados que se desplazaban dentro de la penumbra del pecio. "
            "No eran peces abisales ni cefalópodos: eran filamentos articulados de quitina oscura, de varios metros de longitud, que examinaban los bordes de la brecha con una precisión deliberada y sensorial que denotaba una inteligencia alienígena a la biología de la superficie."
        ),
        (
            "A las tres de la madrugada según el cronómetro de a bordo, la estructura del 'Nereo Cuatro' tembló violentamente cuando un impacto sordo sacudió el anillo de soporte de la cúpula de popa. "
            "El detector de esfuerzo cortante del casco emitió una alarma acústica aguda que indicaba una deformación elástica del tres por ciento en el sector inferior de la esfera de titanio. "
            "Una sombra gigantesca cruzó por encima de nuestros reflectores, tapando la luz xenón y sumergiéndonos en una penumbra opresiva donde solo parpadeaban los diodos LED de los paneles de control. "
            "A través de la mirilla cónica de cuarzo pudimos ver cómo una multitud de ojos ciegos, carentes de pupilas y dotados de una fosforescencia lechosa, se asomaban desde las hendiduras del lecho rocoso circundante. "
            "Las criaturas rodeaban el batiscafo sin atacarlo frontalmente, desplazándose en órbitas concéntricas que generaban micro-remolinos de agua glacial contra las toberas de nuestros propulsores apagados. "
            "El intercomunicador interno comenzó a reproducir una voz modulada en frecuencias extremadamente agudas que imitaba con crudeza fonética los nombres y códigos de identificación militar de los tripulantes. "
            "'Abran la escotilla de descompresión; el agua es tibia en el lecho de la trinchera y la presión alivia el cansancio del pensamiento', repetía el altavoz con una cadencia hipnótica que nublaba la capacidad de raciocinio del copiloto."
        ),
        (
            "Tuve que forcejear físicamente con el copiloto para impedir que accionara la válvula de inundación de emergencia en la mampara de estribor, pues el hombre se encontraba en un estado de trance hipnótico inducido por las señales acústicas. "
            "Le administré una ampolla de sedante de acción rápida del botiquín de supervivencia para neutralizar su crisis psicomotriz y lo até al arnés de seguridad del asiento de pilotaje. "
            "El doctor Arispe y yo comprendimos que las entidades abisales utilizaban las vibraciones hidrodinámicas de frecuencia ultra baja para inducir alucinaciones auditivas complejas en el córtex cerebral humano a través de la resonancia ósea del cráneo. "
            "Nos colocamos los protectores auditivos de atenuación industrial y activamos el generador de pulsos sónicos de alta potencia destinado a prospecciones sísmicas submarinas para dispersar el enjambre que rodeaba el casco. "
            "El estallido sónico reverberó en el lecho rocoso con la fuerza de un rayo submarino, provocando una onda de choque visible en las partículas de sedimento en suspensión. "
            "Las criaturas retrocedieron en desbandada hacia las profundidades de la garganta basáltica, retorciéndose con violencia mientras la sobrepresión acústica desorientaba sus órganos sensoriales bioluminiscentes. "
            "Aproveché esa ventana de oportunidad de tres minutos para sobrecargar deliberadamente los bancos de capacitores de los propulsores de babor y generar una explosión eléctrica que arrancó de cuajo el pasador del lastre de popa."
        ),
        (
            "Al liberarse la mitad de los lingotes de plomo, el 'Nereo Cuatro' experimentó una sacudida ascensional que nos proyectó contra los mamparos interiores de la cabina mientras la nave comenzaba a subir en espiral hacia la superficie. "
            "Los indicadores de velocidad vertical marcaban un ascenso de seis metros por segundo a través de las capas abisales del océano, dejando atrás el brillo azulado de la fosa y los restos de la nave ciclópea sepultada en el fango. "
            "Durante los primeros mil metros de ascenso, los hidrófonos continuaron registrando el eco de alaridos sónicos que subían desde la garganta submarina como el aullido de una jauría marina privada de su presa. "
            "El casco de titanio crujía de forma espantosa al descompresionarse gradualmente conforme la columna de agua exterior reducía su peso aplastante con cada kilómetro ganado hacia la luz del sol. "
            "El doctor Arispe revisaba obsesivamente los registros magnéticos almacenados en las unidades de estado sólido portátiles, comprobando que las lecturas electromagnéticas no coincidían con ninguna firma física producida por tecnología civil o militar conocida. "
            "A dos mil metros de la superficie, el transpondedor acústico del barco nodriza restableció el contacto con nuestra antena de emergencia, coordinando las maniobras de recuperación y enganche con la grúa pórtico del buque oceanográfico. "
            "Emergimos a la superficie en medio de una tarde soleada en el mar de Filipinas, con el mar en calma y el aire fresco del trópico recibiendo la apertura de la escotilla sellada."
        ),
        (
            "Apenas pisamos la cubierta del barco de investigación, fuimos aislados en los camarotes de cuarentena por orden directa de dos oficiales de inteligencia naval que habían abordado la nave en helicóptero durante nuestra inmersión profunda. "
            "Los discos duros de a bordo fueron extraídos bajo cadena de custodia militar, las cámaras exteriores fueron desmotadas para inspección pericial clasificada y las bitácoras de campo nos fueron retiradas bajo amenaza de juicio sumario por alta traición. "
            "Los informes médicos oficiales afirmaron que la tripulación había experimentado un episodio agudo de delirio hipobárico y narcosis gaseosa severa debido a un fallo en las mezclas de helio y oxígeno del circuito cerrado de respiración. "
            "Sin embargo, el informe metalúrgico preliminar del casco de titanio, filtrado años después por un ingeniero del astillero de mantenimiento, demostró que el metal presentaba microranuras con inclusiones de aleaciones no terrestres y corrosión cáustica en patrones geométricos idénticos a los bajorrelieves del lecho abisal. "
            "El batiscafo 'Nereo Cuatro' fue dado de baja del servicio científico activo dos semanas después y confinado en un hangar naval de acceso restringido en el atolón de Diego García sin que se permitiera su reingreso a operaciones oceanográficas civiles. "
            "La totalidad de las coordenadas batimétricas de aquella garganta de la fosa de las Marianas fue suprimida de las cartas náuticas internacionales de la NOAA y reclasificada como zona de pruebas submarinas peligrosas con prohibición absoluta de navegación y sondeo batimétrico."
        ),
        (
            "Años más tarde logré contactar clandestinamente a un antiguo especialista en acústica submarina que operaba en la red de hidrófonos SOSUS de detección de submarinos nucleares durante los años de la Guerra Fría. "
            "El veterano analista me confirmó que desde finales de los años sesenta los hidrófonos de escucha profunda en el Pacífico central registraban señales idénticas a las grabadas por nuestro batiscafo durante la inmersión en la fosa. "
            "El mando conjunto denominaba a ese fenómeno acústico 'El Eco de Hades', catalogándolo como una fuente no mecánica de energía pulsante que migraba periódicamente a lo largo de las dorsales oceánicas abisales. "
            "Varios buques de reconocimiento hidrográfico que intentaron cartografiar la zona en expediciones anteriores sufrieron averías catastróficas en sus timones y sonares de barrido lateral, obligando al Pentágono a declarar el área como reserva estratégica vedada. "
            "El especialista me advirtió con gravedad que aquello que habita en las profundidades abisales no es hostil en el sentido bélico convencional, sino una presencia geobiológica que despierta cuando los ingenios humanos perturban el silencio de sus simas milenarias. "
            "Esa certeza me acompaña en cada noche de desvelo, recordándome que la mayor frontera de terror de nuestro planeta no se encuentra en las estrellas remotas, sino en la negrura gélida de nuestros propios océanos insondables."
        ),
        (
            "Al reflexionar sobre las implicaciones científicas y filosóficas de aquella expedición submarina, comprendo que la soberbia humana es el mayor velo que nos impide aceptar nuestra insignificancia en el cosmos. "
            "Nos jactamos de haber conquistado la superficie de los continentes y de haber enviado sondas espaciales a los confines del sistema solar, pero ignoramos por completo los abismos que cubren las tres cuartas partes de nuestro propio mundo. "
            "Aquellas estructuras geométricas y las entidades biológicas que custodiaban el lecho de la fosa de las Marianas demuestran que antes de que el primer homínido encendiera un fuego en la tierra firme, otras voluntades ya señoreaban las corrientes profundas del planeta. "
            "Quizás sea una bendición de la naturaleza que la presión titánica de los abismos mantenga confinadas esas presencias lejos de nuestras costas pobladas y de nuestras rutas de navegación mercantil. "
            "El mar profundo no es un desierto estéril ni un vertedero geológico: es una cripta viviente donde lo desconocido espera en silencio su momento histórico de revelación."
        ),
        (
            "Para los futuros exploradores que decidan tripular batiscafos hacia las simas oceánicas desconocidas, dejo este testimonio como una advertencia ineludible y un protocolo de supervivencia elemental. "
            "Si durante una inmersión abisal los instrumentos registran corrientes cálidas ascendentes y los hidrófonos detectan pulsos armónicos en frecuencias ultra bajas, no busques la gloria del descubrimiento científico ni intentes filmar lo imposible. "
            "Corta los lastres de inmediato, enciende los propulsores al máximo régimen ascensional y regresa a la luz del sol antes de que la presión del abismo doble el titanio y la oscuridad se adueñe de tu mente para siempre. "
            "Hay misterios en las fosas del océano que deben permanecer en la oscuridad eterna por el bien de la cordura de toda la raza humana."
        ),
    ]
    return "\n\n".join(p.strip() for p in paragraphs)


def build_moku_asylum(topic: str, **kwargs: Any) -> str:
    """Story 5: Abandoned Blackwood Sanatorium Night Guard."""
    paragraphs = [
        (
            "Meses después de mi huida del sanatorio, logré entrevistarme clandestinamente con una antigua enfermera jefe que había trabajado en la unidad de aislamiento durante la década de los setenta. "
            "La anciana me relató con lágrimas en los ojos cómo el doctor Vance seleccionaba cuidadosamente a los internos sin familiares directos para trasladarlos en secreto al sótano de baños en horas de la madrugada. "
            "Los pacientes regresaban a sus celdas horas más tarde en un estado de mutismo absoluto, con la piel fría como el mármol y las pupilas dilatadas que no respondían a los reflejos luminosos habituales. "
            "Muchos de ellos comenzaban a trazar símbolos geométricos idénticos en las sábanas de sus camas y a rechazar los alimentos sólidos, afirmando en susurros inaudibles que 'la tierra de abajo ya los estaba alimentando'. "
            "La complicidad de los inspectores provinciales permitió que estas prácticas aberrantes se prolongaran durante casi quince años antes de que una denuncia anónima obligara a la intervención del ministerio de justicia."
        ),
        (
            "El análisis de los historiales clínicos confiscados demostró que ninguno de los pacientes sometidos a los experimentos de Vance presentaba lesiones cerebrales orgánicas iniciales. "
            "Sus trastornos eran crisis reactivas y depresiones agudas que habrían remitido con tratamientos farmacológicos y psicológicos convencionales en un entorno hospitalario digno y humano. "
            "Fueron despojados de su condición de personas y utilizados como cobayas biológicas para alimentar la megalomanía de un facultativo que vendió su alma a la oscuridad en busca de secretos metafísicos prohibidos. "
            "El recuerdo de sus miradas vacías y de sus gritos apagados en la noche del bosque debe permanecer vivo en nuestra memoria colectiva como un escudo inexpugnable contra la deshumanización de la ciencia médica."
        ),
        (
            f"Entre los bosques de pinos negros que cubren la cordillera occidental, las ruinas del Sanatorio Psiquiátrico de Blackwood se alzan como un monumento decrépito al sufrimiento humano, y los eventos inexplicables de {topic} marcaron para siempre mi existencia. "
            "Fui contratado por una empresa de seguridad privada para realizar guardias nocturnas de doce horas en el complejo hospitalario clausurado a finales de los años ochenta, tras un escándalo judicial que destapó negligencias médicas extremas y experimentos no autorizados en el pabellón de aislamiento. "
            "La propiedad constaba de cuatro pabellones de ladrillo rojo de estilo victoriano tardío, unidos entre sí por galerías subterráneas de tuberías de calefacción y pasillos exteriores acristalados completamente devorados por la hiedra silvestre. "
            "Mi misión sobre el papel era sencilla: impedir el acceso a saqueadores de chatarra de cobre, grafiteros adolescentes y exploradores urbanos que pudieran sufrir accidentes en las plantas superiores donde los pisos de madera estaban semiderruidos por las filtraciones de agua. "
            "El único equipo asignado para mi turno consistía en una linterna halógena recargable, un teléfono satelital para reportes horarios a la central receptora de alarmas, un manojo de llaves maestras de latón antiguo y una porra de defensa personal. "
            "Durante las primeras jornadas laborales, la monotonía de la ronda se veía alterada únicamente por el graznido de los cuervos en los aleros de la cubierta y el sonido sordo del viento colándose por los ventanales enrejados de las antiguas salas de hidroterapia. "
            "Sin embargo, al cumplirse la tercera semana de vigilancia solitaria, comencé a encontrar indicios materiales de que el sanatorio no estaba completamente desierto durante las horas previas al amanecer. "
            "En el suelo de baldosas ajedrezadas del vestíbulo principal aparecían huellas descalzas impresas en el polvo acumulado, cuyo rastro comenzaba en medio de los pasillos sin provenir de ninguna puerta o ventana exterior."
        ),
        (
            "A la una y media de la madrugada de un martes lluvioso de noviembre, el tablero de relés de la garita de control emitió un chasquido intermitente cuando el timbre de llamada de enfermería del Pabellón C se iluminó en el panel analógico. "
            "Aquel circuito eléctrico llevaba más de treinta y cinco años desconectado de la red pública y los cables de alimentación principal del edificio habían sido cortados en la arqueta exterior durante las obras de desmantelamiento de la subestación. "
            "Tomé la linterna y el teléfono satelital, ajusté la correa de seguridad y crucé el patio exterior bajo un aguacero torrencial para inspeccionar la tercera planta del Pabellón C, donde antiguamente operaba la unidad de contención psiquiátrica de alta seguridad. "
            "El hedor a humedad estancada, moho negro y medicamentos farmacéuticos caducados impregnaba la atmósfera de los corredores en ruinas con una intensidad corrosiva que dificultaba la respiración normal. "
            "Al alumbrar las puertas de los dormitorios individuales, descubrí que las mirillas de observación blindadas estaban cubiertas por arañazos profundos grabados en el cristal desde el interior de las celdas vacías. "
            "En el extremo norte del pasillo, la puerta de la celda catorce se encontraba entreabierta, oscilando suavemente sobre sus goznes oxidados con un chirrido que reverberaba a lo largo de toda la galería de dormitorios. "
            "Al enfocar el haz halógeno hacia el interior de la habitación, distinguí en la pared de yeso descascarillado una serie de ecuaciones matemáticas y fechas de defunción garabateadas con trozos de yeso fresco que no mostraban el menor rastro de polvo superficial."
        ),
        (
            "Me aproximé al muro de la celda catorce para examinar las inscripciones y comprobé con estupor que la última fecha anotada en la pared correspondía exactamente al día y año de mi propia guardia nocturna en el sanatorio. "
            "Debajo de la fecha figuraba mi nombre completo, mi número de documento nacional de identidad y una advertencia manuscrita trazada con pulso tembloroso: 'No bajes al sótano de hidroterapia cuando la marea del bosque comience a subir'. "
            "Un escalofrío helado recorrió mi columna vertebral mientras un susurro gutural, articulado como la respiración jadeante de un asmático en crisis respiratoria, se propagó a través de la rejilla de ventilación situada junto al zócalo. "
            "El haz de mi linterna halógena comenzó a titilar repentinamente, perdiendo intensidad luminosa como si las baterías de ion de litio recién cargadas estuvieran siendo drenadas por un campo electromagnético de proximidad. "
            "En el suelo de linóleo húmedo comenzaron a formarse charcos de agua viscosa teñida de un color parduzco similar a restos de yodo antiséptico y sangre coagulada que emanaban directamente de las juntas de unión de las baldosas. "
            "Retrocedí hacia la salida del pabellón con el corazón latiendo desbocado en la garganta, pero al alcanzar la escalera principal descubrí que la reja de tijera de hierro forjado que daba al rellano estaba trabada por un candado de combinación que no figuraba en mi inventario de llaves. "
            "Desde la oscuridad del rellano inferior ascendía un eco rítmico de ruedas metálicas chirriantes, como el avance lento y pesado de una camilla de quirófano rodando sobre baldosas quebradas."
        ),
        (
            "Atrapado en el tercer piso del pabellón, me refugié en la antigua sala de archivos clínicos situada junto al puesto central de enfermería, atrancando la pesada puerta de madera con un armario metálico de expedientes. "
            "El sonido de las ruedas de la camilla se detuvo justo enfrente de la puerta bloqueada, seguido por el roce sordo de dedos desnudos arañando los paneles de madera en busca de la rendija de la cerradura. "
            "Encendí la linterna de emergencia de mi teléfono móvil y me apresuré a revisar los archivadores rodantes para intentar comprender qué experimentos se habían realizado en aquel pabellón antes de su cierre gubernamental precipitado. "
            "Entre las carpetas mohosas encontré el expediente confidencial del doctor Julian Vance, el último director médico de Blackwood, quien había sido procesado por homicidio imprudente y falsificación de informes psiquiátricos en mil novecientos ochenta y siete. "
            "Los informes periciales describían cómo Vance sometía a los internos diagnosticados de catatonía profunda a tratamientos experimentales de estimulación cerebral mediante corrientes inducidas por campos magnéticos generados en una cámara subterránea. "
            "El objetivo confeso de Vance en sus notas manuscritas no era la curación clínica de los enfermos, sino la sincronización de la conciencia humana con lo que él denominaba 'La Resonancia Subyacente', una presencia incorpórea que según sus delirios residía bajo los cimientos geológicos del hospital. "
            "El informe forense final registraba que once pacientes y tres enfermeros auxiliares habían desaparecido sin dejar rastro biológico durante la última sesión experimental nocturna en el pabellón de hidroterapia profunda."
        ),
        (
            "A las dos y cuarenta y cinco de la madrugada, los paneles de yeso del techo de la sala de archivos comenzaron a combarse bajo el peso de una masa informe que se arrastraba pesadamente por el entretecho de la cubierta. "
            "Polvo calizo y fragmentos de escayola cayeron sobre los archivadores metálicos mientras una sustancia oscura y fétida, con consistencia de brea caliente, comenzó a filtrarse por las grietas del forjado. "
            "El armario metálico que bloqueaba la puerta de acceso fue empujado hacia el interior de la habitación con una fuerza descomunal que deformó las baldas interiores y dobló los pernos de acero de las bisagras. "
            "A través de la rendija abierta en la madera vi una figura esquelética, de estatura anormalmente desproporcionada y extremidades alargadas envueltas en jirones de batas de hospitalización amarillentas por el paso de las décadas. "
            "Su rostro no presentaba rasgos anatómicos normales: la piel estaba estirada sobre el cráneo óseo como pergamino seco y en lugar de ojos y boca exhibía cavidades oscuras suturadas con alambre de cobre quirúrgico. "
            "La entidad extendió un brazo nudoso hacia el interior del cuarto y una onda de frío polar invadió la estancia, congelando al instante las gotas de humedad sobre los cristales de la ventana exterior y haciendo saltar chispas estáticas en mi uniforme de seguridad."
        ),
        (
            "Sin vacilar un segundo, utilicé la porra de defensa para golpear con furia los cristales enrejados de la ventana que daba a la cornisa exterior del pabellón, rompiendo los vidrios y deslizándome hacia el saliente de piedra bajo la lluvia torrencial. "
            "El alarido sibilante que emitió la criatura dentro de la sala de archivos hizo vibrar las tuberías de plomo del edificio con un tono de resonancia que me provocó náuseas instantáneas y una hemorragia nasal fulminante. "
            "Avancé gateando por la cornisa resbaladiza de piedra arenisca a doce metros de altura sobre el patio empedrado, aferrándome a las cañerías de drenaje pluvial para evitar caer al vacío en medio de la ventisca nocturna. "
            "Logré alcanzar la escalera de incendios exterior del Pabellón B y descendí los tramos metálicos de tres en tres peldaños mientras a mis espaldas las ventanas del tercer piso se iluminaban una tras otra con un fulgor verdoso y fosforescente. "
            "En los patios interiores del sanatorio, la niebla densa formaba remolinos circulares alrededor de las antiguas fuentes ornamentales, donde siluetas inmóviles permanecían erguidas bajo la lluvia en posturas catatónicas idénticas a las fotografías del archivo clínico. "
            "No intenté recuperar mis pertenencias de la garita de seguridad: corrí directamente hacia la verja perimetral de hierro fundido que cerraba el acceso al camino forestal de montaña."
        ),
        (
            "Al llegar a la verja exterior, descubrí que la cadena de acero cementado que cerraba las dos hojas había sido retorcida y soldada por una fuerza térmica que había fundido los eslabones en una masa compacta de hierro incandescente. "
            "La camioneta de servicio de la empresa de seguridad, estacionada en el arcén del camino, tenía los cuatro neumáticos reventados por cortes limpios en los flancos y el parabrisas trizado por un impacto interior. "
            "Desde la espesura de los pinos circundantes comenzaron a emerger murmullos polifónicos, cánticos litúrgicos distorsionados y voces infantiles que repetían los antiguos números de expediente de los enfermos terminales del sanatorio. "
            "Escalé la verja perimetral de tres metros trepando por los barrotes ornamentales sin reparar en los cortes que el alambre de espino provocaba en las palmas de mis manos y en mis piernas cubiertas de barro. "
            "Caí al otro lado del vallado sobre la grava del camino forestal y comencé a correr pendiente abajo en medio de la oscuridad total, orientándome únicamente por el sonido lejano de los camiones de carga que transitaban por la autopista comarcal a ocho kilómetros de distancia. "
            "Corrí durante dos horas ininterrumpidas sin mirar hacia atrás, sintiendo a mis espaldas la vibración constante del terreno como si el bosque entero estuviera respirando al unísono con las galerías subterráneas del complejo hospitalario."
        ),
        (
            "Al amanecer alcancé la estación de servicio abierta veinticuatro horas en el empalme de la carretera nacional, donde los dependientes me auxiliaron en estado de shock hipotérmico severo y con contusiones múltiples en el tórax y las extremidades. "
            "La patrulla de la guardia civil comarcal que se presentó en el lugar tomó mi declaración inicial con evidente escepticismo, insinuando que podía haber sufrido una intoxicación accidental por inhalación de gases tóxicos o vapores de caldera en las ruinas. "
            "Sin embargo, dos agentes de paisano pertenecientes a la brigada de información judicial se personaron en el centro de salud comarcal a media mañana para asumir el control exclusivo de la investigación preliminar. "
            "Me advirtieron formalmente de que revelar cualquier detalle de mi turno de guardia a medios de comunicación o en foros de internet acarrearía la rescisión inmediata de mi licencia de seguridad privada y posibles cargos penales por violación de secretos mercantiles protegidos. "
            "La empresa de seguridad liquidó mis honorarios mediante una transferencia bancaria extraordinaria que duplicaba el importe pactado en mi contrato, clausurando su servicio de vigilancia física en el sanatorio en un plazo de veinticuatro horas. "
            "Una semana después, cuadrillas de operarios de una empresa de demoliciones especializada en amianto pesado levantaron un muro de hormigón armado de cuatro metros de altura coronado por concertinas militares alrededor de todo el perímetro de Blackwood."
        ),
        (
            "A través de un periodista de investigación jubilado que había seguido el escándalo médico en los años ochenta, pude acceder a copias microfilmadas de las actas de la comisión judicial secreta que ordenó el desalojo forzoso del sanatorio. "
            "Los documentos probaban que durante las obras de cimentación del pabellón de hidroterapia en mil novecientos veintitrés, los albañiles habían perforado una red de catacumbas naturales que contenían osarios prehistóricos cubiertos por grabados rúnicos desconocidos. "
            "El doctor Vance había transformado el sótano de baños termales en una cámara de resonancia acústica para amplificar las emanaciones subterráneas utilizando a los internos más graves como catalizadores biológicos de la anomalía. "
            "Las autoridades estatales decidieron sellar las galerías y declarar la muerte civil de los pacientes afectados para evitar el pánico social y encubrir la implicación de destacadas personalidades de la judicatura y la política regional en los experimentos esotéricos de Vance. "
            "El periodista me confesó que ninguno de los tres vigilantes nocturnos que me precedieron en aquel puesto de trabajo había logrado conservar su estabilidad emocional: dos de ellos estaban internados en clínicas neuropsiquiátricas privadas y el tercero se había suicidado tres meses después de abandonar la guardia. "
            "Esa revelación me confirmó que mi supervivencia en aquella noche de terror no fue fruto del azar, sino de la decisión instintiva de huir sin intentar comprender lo que desafía toda lógica humana."
        ),
        (
            "Hoy en día, las ruinas del Sanatorio de Blackwood permanecen ocultas tras el muro de hormigón y el bosque de pinos, vigiladas por sensores de movimiento térmicos y cámaras infrarrojas conectadas a una red de seguridad restringida. "
            "Las leyendas urbanas que circulan entre los jóvenes de la comarca sobre fantasmas y psicofonías en el hospital son apenas un pálido reflejo infantil del horror ontológico que permanece sepultado bajo sus sótanos de ladrillo. "
            "El sufrimiento acumulado durante décadas en aquellas salas de tortura médica no desapareció con el cierre de las instalaciones: fue absorbido por la tierra misma, creando un vórtice de angustia que devora la cordura de quien ose perturbar su quietud. "
            "Quienes buscan emociones fuertes en la exploración de edificios abandonados deberían recordar que hay lugares donde los muros no solo guardan polvo y recuerdos tristes, sino prisiones vivientes donde la locura humana abrió puertas que jamás debieron ser traspasadas. "
            "Mi testimonio es una plegaria por las almas de aquellos inocentes sacrificados en la oscuridad y una advertencia inquebrantable para quienes confunden el coraje con la temeridad imprudente."
        ),
        (
            "Para concluir este relato sobre las sombras de Blackwood, quiero dejar una reflexión para todos aquellos que valoran la dignidad humana y el respeto hacia los más vulnerables. "
            "La verdadera maldad no siempre se manifiesta a través de monstruos sobrenaturales nacidos de las pesadillas: a menudo viste batas blancas de autoridad médica, utiliza el lenguaje frío de la ciencia y cuenta con la complicidad silenciosa de instituciones respetables. "
            "Aprender a reconocer la crueldad encubierta y no mirar hacia otro lado cuando los indefensos son pisoteados es la única defensa real que nos separa de la barbarie. "
            "Que la memoria de los olvidados de Blackwood encuentre por fin el descanso eterno en la quietud de los bosques y que su tragedia sirva de recordatorio permanente de los abismos que la mente humana es capaz de engendrar."
        ),
    ]
    return "\n\n".join(p.strip() for p in paragraphs)


def build_moku_observatory(topic: str, **kwargs: Any) -> str:
    """Story 6: High-Altitude Arctic Observatory / Aurora Monitoring Station."""
    paragraphs = [
        (
            "Al contemplar en retrospectiva los acontecimientos de aquella noche en Svalbard, comprendo que el ser humano tiende a buscar la belleza en los cielos sin comprender las fuerzas titánicas que la originan. "
            "Las auroras boreales que hoy atraen a miles de turistas a las regiones árticas son el escudo visible que protege a nuestra atmósfera del bombardeo continuo de partículas solares letales. "
            "Perturbar ese manto protector mediante emisiones artificiales o perforaciones en las fallas polares es una insensatez que pone en riesgo el equilibrio electromagnético de todo el hemisferio norte. "
            "Que la Base Aurora Ocho permanezca sepultada bajo el hielo y que las generaciones venideras sepan respetar los límites inviolables de la naturaleza polar."
        ),
        (
            "Al revisar los registros de temperatura y presión atmosférica de la meseta de Svalbard correspondientes a los últimos cien años, descubrí que eventos electromagnéticos similares habían sido registrados en mil novecientos veintiocho y en mil novecientos cincuenta y cuatro. "
            "En ambas ocasiones, expediciones polares internacionales informaron de fallos simultáneos en todos sus compases magnéticos y de la aparición de 'nieblas luminiscentes' que ascendían desde las grietas de los glaciares hacia el cielo despejado. "
            "Los cuadernos de bitácora de los exploradores noruegos describían cómo los miembros de las avanzadas comenzaban a escuchar coros angelicales o letanías fúnebres que parecían emanar directamente de la nieve congelada que pisaban sus trineos. "
            "Varios expedicionarios abandonaron los campamentos base en medio de la noche polar guiados por esas alucinaciones acústicas, desapareciendo para siempre en las simas de los campos de hielo sin que sus restos fueran jamás recuperados. "
            "Las autoridades científicas de la época atribuyeron los sucesos a 'histeria de invierno' o escorbuto avanzado, ocultando cuidadosamente los informes de magnetometría que demostraban anomalías de campo incomparables con la física solar clásica."
        ),
        (
            "Investigadores independientes especializados en física cuántica de la gravedad teórica sostienen la hipótesis de que ciertas formaciones geológicas polares actúan como lentes de concentración geomagnética natural. "
            "En determinadas alineaciones planetarias y durante periodos de calma ionosférica, estas zonas de la litosfera polar pueden entrar en resonancia con ondas gravitacionales de fondo que atraviesan nuestro cuadrante galáctico. "
            "La base Aurora Ocho se encontraba construida sobre el foco geométrico exacto de una de estas lentes de resonancia, lo que provocó que los receptores de radio amplificaran la perturbación hasta niveles de coherencia macroscópica perceptibles por los sentidos humanos. "
            "La decisión de destruir la estación y sellar los accesos subterráneos fue el único proceder sensato para evitar que el vórtice electromagnético se expandiera y colapsara las redes de satélites de posicionamiento global de todo el hemisferio norte."
        ),
        (
            "La noche polar de Svalbard continuará envolviendo en su manto blanco y gélido las ruinas de la cúpula geodésica y el secreto que yace sepultado bajo el hielo milenario. "
            "Aprender a convivir con el misterio sin pretender violentar sus cerraduras es la mayor muestra de madurez intelectual a la que puede aspirar nuestra especie en su infancia cósmica. "
            "Que los vientos de la meseta sigan borrando las huellas de los hombres y que la luz de las auroras boreales preserve la quietud de los abismos del polo norte por siempre."
        ),
        (
            f"En las soledades glaciares de la meseta de Svalbard, donde la noche polar cubre el horizonte durante cuatro meses ininterrumpidos de ventisca ártica, los fenómenos extraordinarios de {topic} alteraron para siempre los límites de la física moderna. "
            "Fui destinado como ingeniero en radioastronomía y física de la ionosfera a la Base Científica Aurora Ocho, un complejo de observación electromagnética situado sobre una cresta de roca permafrost a mil doscientos metros sobre el nivel del mar polar. "
            "La estación constaba de tres cúpulas geodésicas de fibra de vidrio presurizada que albergaban radiotelescopios interferométricos, magnetómetros fluxgate de tres ejes y cámaras de cielo completo destinadas al estudio de la interacción del viento solar con la magnetosfera terrestre. "
            "A setecientos kilómetros del asentamiento humano más cercano, el aislamiento en la meseta es absoluto: las temperaturas exteriores descienden habitualmente por debajo de los cuarenta y cinco grados bajo cero y los vientos catabáticos alcanzan rachas de más de ciento cincuenta kilómetros por hora. "
            "Mi labor técnica consistía en supervisar la adquisición ininterrumpida de datos de los magnetómetros, calibrar los receptores de radio de muy baja frecuencia y retransmitir los paquetes de telemetría a la red académica europea mediante un enlace satelital geosincrónico. "
            "Durante las primeras semanas de la larga noche ártica, los registros atmosféricos se mantuvieron dentro de los parámetros habituales de un periodo de mínima actividad solar. "
            "Sin embargo, al comenzar el mes de diciembre, los sensores de resonancia Schumann comenzaron a detectar una señal oscilatoria continua en la banda de catorce kilohercios que no presentaba las características de una emisión geofísica natural. "
            "Era una transmisión estructurada en pulsos binarios modulados en fase, cuya potencia espectral aumentaba de forma inversamente proporcional a la distancia del cénit electromagnético polar."
        ),
        (
            "A las dos y cuarto de la madrugada, cuando el termómetro exterior marcaba cuarenta y ocho grados bajo cero, los cielos despejados sobre la base fueron cubiertos por una formación de auroras boreales de una morfología que jamás había sido documentada en la literatura astronómica. "
            "En lugar de las habituales cortinas ondeantes de luz verdosa producidas por la excitación del oxígeno atómico a cien kilómetros de altitud, la aurora se manifestaba como un entramado geométrico de filamentos carmesíes y púrpuras perfectamente paralelos entre sí. "
            "Las bandas de luz no seguían las líneas de fuerza del campo dipolar terrestre: se cerraban en hexágonos concéntricos sobre la cúpula principal de la estación, rotando en sentido antihorario a una velocidad angular constante de cinco grados por minuto. "
            "Salí a la plataforma de observación exterior provisto del traje térmico de supervivencia y las gafas de protección polarizada para examinar visualmente el fenómeno a través del fotómetro de emisión auroral. "
            "El aire ártico era tan gélido que al inhalar sentía cómo los alvéolos pulmonares crujían bajo el choque térmico, impregnando la atmósfera con un aroma penetrante a ozono electrostático y metal quemado. "
            "Al enfocar el espectrómetro de masas hacia la banda carmesí, las líneas de emisión espectral revelaron trazas isotópicas de helio tres y antimateria residual que no deberían existir en la atmósfera superior de nuestro planeta. "
            "De pronto, los receptores de radio de baja frecuencia del laboratorio comenzaron a emitir un tono continuo que moduló la luz de las lámparas fluorescentes interiores, sincronizando los destellos eléctricos con los pulsos de la aurora en el cielo polar."
        ),
        (
            "Regresé a toda prisa a la sala de instrumentación para verificar si la red de satélites meteorológicos de órbita polar registraba alguna eyección de masa coronal procedente del sol que pudiera explicar semejante perturbación ionosférica. "
            "Las pantallas de estado mostraban que la actividad solar se encontraba en calma total: no existían manchas solares activas ni vientos de plasma extraordinarios en el espacio interplanetario circundante. "
            "La anomalía electromagnética no provenía del exterior del sistema solar, sino que parecía tener su foco emisor en la corteza terrestre profunda situada directamente bajo los glaciares de la meseta. "
            "El gravímetro cuántico de la base, un instrumento de ultra precisión refrigerado por helio líquido, registraba variaciones dinámicas de la aceleración de la gravedad del orden de microgalios que se desplazaban en círculos concéntricos bajo la estación. "
            "El enlace satelital con el centro de control en Tromsø se interrumpió bruscamente cuando la antena parabólica exterior fue desorientada por un par torsional anómalo en sus servomotores de guiado inercial. "
            "El sintetizador de voz del ordenador central, programado para emitir avisos de diagnóstico técnico en inglés estándar, comenzó a articular palabras en un dialecto fonético gutural que reproducía patrones de lenguas indoeuropeas arcaicas extinguidas hacía milenios. "
            "'Alineen los receptores hacia el norte verdadero; el cielo no es un techo pasivo, sino un espejo que devuelve la mirada a quienes escudriñan el vacío sin temor', repetía el sintetizador con una neutralidad digital aterradora."
        ),
        (
            "A las tres y cuarenta de la madrugada, los generadores diésel de emergencia situados en el módulo exterior sufrieron una parada repentina por despolarización magnética de sus alternadores principales. "
            "La temperatura en el interior de la cúpula comenzó a descender a un ritmo vertiginoso de un grado centígrado por minuto, amenazando con congelar los sistemas de soporte vital y las baterías de reserva en cuestión de una hora. "
            "Me coloqué la linterna frontal y la máscara de respiración asistida para descender al túnel de servicio excavado en el hielo fósil que conectaba los módulos científicos con el almacén de combustible. "
            "En el interior de la galería glaciar, las paredes de hielo azul milenario estaban cubiertas por patrones de condensación cristalina que formaban figuras geométricas tridimensionales similares a fractales hiperbólicos. "
            "Al alumbrar las paredes de hielo con la linterna halógena, vi con absoluta claridad que atrapadas en los estratos de hielo de hace veinte mil años yacían siluetas de artefactos metálicos y prismas de aleación desconocida que reflejaban la luz con un brillo dorado inmutable. "
            "El hielo crujía bajo mis botas con detonaciones sordas que hacían temblar las vigas de madera de pino ártico que sostenían el techo del túnel. "
            "Desde el fondo del pozo de prospección glaciológica número dos emergía una columna de luz violeta fría que atravesaba el suelo congelado sin fundir el hielo circundante, proyectando sombras alargadas que se movían de forma autónoma sobre la superficie translúcida."
        ),
        (
            "Comprendí que la base científica no había sido construida en aquel punto remoto de Svalbard por conveniencia geográfica para el estudio auroral, sino como una tapadera institucional para monitorizar una estructura ancestral sepultada bajo el glaciar. "
            "Oculto tras un panel de acceso sellado en el cabezal del pozo, encontré un transmisor militar analógico de mil novecientos cincuenta y dos dotado de un conmutador de activación de termita de emergencia para la destrucción total del emplazamiento. "
            "Las anotaciones del registro técnico secreto advertían que la estructura bajo el permafrost reaccionaba a los mínimos solares activando ciclos de emisión ionosférica para comunicarse con estaciones hermanas situadas en la Antártida y en fosas oceánicas abisales. "
            "La columna de luz violeta que ascendía por el pozo comenzó a expandirse radialmente, cubriendo la maquinaria de perforación y transformando el aire en una masa viscosa donde las partículas de nieve suspendidas permanecían inmóviles como gotas de mercurio en el espacio. "
            "Sentí cómo una presión telequinética descomunal comprimía mis sienes, induciendo visiones holográficas de continentes cubiertos por vegetación hiperbórea antes de las grandes glaciaciones del Pleistoceno. "
            "Una voz serena y múltiple resonó directamente en mi corteza cerebral sin mediación acústica, ofreciéndome la comprensión total de las leyes unificadas del cosmos a cambio de desactivar el protocolo de voladura de la base."
        ),
        (
            "Con la mente al borde del colapso y las manos enguantadas entorpecidas por el frío gélido de treinta grados bajo cero dentro del túnel, rechacé la inducción telepática y accioné la palanca de encendido de las cargas pirotécnicas de seguridad. "
            "El estallido de las bengalas de magnesio y fósforo desató una deflagración térmica que rompió la columna de resonancia violeta en una cascada de chispas incandescentes que iluminaron las galerías de hielo como un sol artificial. "
            "La onda de choque me arrojó hacia la esclusa del túnel de acceso mientras toneladas de hielo y grava colapsaban sobre el pozo de prospección, sepultando la boca de la excavación bajo un alud de roca congelada. "
            "Me arrastré hacia el módulo de mando y logré rearmar los disyuntores térmicos del generador de respaldo secundario, restableciendo la calefacción eléctrica y la iluminación básica de la sala de control. "
            "En el exterior de la estación, las auroras geométricas desaparecieron del cielo polar con un fogonazo rojizo que iluminó los glaciares en un radio de doscientos kilómetros, dejando paso nuevamente a las habituales cortinas difusas de luz verde boreal. "
            "Me desplomé sobre el sillón de comunicaciones envuelto en mantas térmicas de aluminio, esperando el paso de las horas mientras el viento ártico aullaba contra la cúpula de fibra de vidrio."
        ),
        (
            "A los cuatro días del incidente, cuando la tormenta amainó lo suficiente para permitir operaciones aéreas polares, un avión de transporte militar equipado con esquís de aterrizaje sobre nieve tocó tierra en la pista de hielo de la meseta. "
            "Un destacamento de ingenieros de la OTAN y oficiales de seguridad científica asumió el control del complejo, procediendo a desmantelar la totalidad de los magnetómetros fluxgate y a retirar los núcleos de hielo extraídos durante la campaña invernal. "
            "Fui trasladado bajo escolta médica a la base naval de Bodø, donde permanecí en régimen de aislamiento sanitario durante setenta y dos horas sometido a reconocimientos neurológicos exhaustivos y pruebas toxicológicas ininterrumpidas. "
            "El dictamen médico oficial concluyó que había experimentado un episodio de psicosis polar inducido por privación sensorial extrema, bajas temperaturas y exposición a monóxido de carbono por combustión incompleta de los calefactores diésel. "
            "Firmé un acuerdo de no divulgación perpetuo bajo apercibimiento de enjuiciamiento penal militar y fui retirado del cuerpo de investigación astronómica polar con una pensión de incapacidad laboral por estrés postraumático. "
            "La Base Científica Aurora Ocho fue clausurada definitivamente seis meses después mediante demolición controlada y retirada total de instalaciones, siendo reclasificada la meseta como zona de reserva ecológica estricta con prohibición absoluta de sobrevuelo y tránsito terrestre."
        ),
        (
            "Investigaciones posteriores realizadas mediante contactos en observatorios astronómicos neutrales confirmaron que la noche del incidente todos los magnetómetros del hemisferio norte registraron un pulso geomagnético sincrónico de escala planetaria. "
            "Los satélites de vigilancia espacial de órbita baja detectaron perturbaciones térmicas y gravitatorias en la ionosfera ártica que coincidían con las coordenadas exactas de la estación Aurora Ocho durante el pico de emisión de la aurora geométrica. "
            "Ningún astrofísico oficial pudo ofrecer una explicación plausible de cómo una emisión ionosférica podía presentar frentes de onda coherentes y armónicos idénticos a los utilizados en transmisiones de comunicaciones ópticas de banda ancha. "
            "Los informes clasificados que logré consultar extraoficialmente sugerían que la estructura sepultada bajo el hielo de Svalbard era parte de una red geodésica global establecida antes del cataclismo del Younger Dryas para estabilizar la precesión del eje de la Tierra. "
            "Cualquier intento moderno de perturbar esas instalaciones milenarias mediante sondeos mecánicos o electromagnéticos corre el riesgo de alterar los equilibrios de la magnetosfera polar con consecuencias catastróficas para las telecomunicaciones globales y la red eléctrica del planeta."
        ),
        (
            "Hoy en día resido en una pequeña localidad costera del sur, lejos de los hielos perpetuos y de la oscuridad opresiva de la noche polar ártica. "
            "Sin embargo, cada vez que las noticias meteorológicas anuncian la llegada de una intensa tormenta geomagnética producida por fulguraciones solares, contemplo el horizonte nocturno con un estremecimiento íntimo e imborrable. "
            "Sé que en las soledades del polo norte, bajo kilómetros de hielo milenario que la ciencia humana apenas comienza a rozar con sus taladros térmicos, las presencias ancestrales continúan vigilando el cielo infinito en una vigilia que trasciende nuestra historia. "
            "El universo que nos rodea no es un vacío silente y desierto esperando ser conquistado por nuestra tecnología rudimentaria: es un cosmos habitado por inteligencias milenarias cuyas leyes aún no alcanzamos a vislumbrar en nuestros laboratorios terrestres. "
            "Guardar silencio y respetar la quietud de los abismos polares es el acto más elemental de prudencia que la humanidad puede adoptar si desea preservar su propia supervivencia en este planeta."
        ),
        (
            "Para los jóvenes científicos que dedican su talento a la investigación de las altas latitudes y de la física del espacio exterior, dejo este testimonio como un recordatorio indispensable sobre los límites éticos del conocimiento. "
            "No toda señal captada en los radiotelescopios debe ser respondida y no toda anomalía detectada en los hielos debe ser desenterrada en nombre del progreso científico inmediato. "
            "Hay fronteras del cosmos que exigen una reverencia silenciosa y un respeto incondicional hacia los equilibrios naturales que sostienen la vida en nuestro frágil hogar planetario. "
            "Que la luz de las auroras boreales continúe iluminando los cielos árticos con su belleza misteriosa y que los secretos sepultados en el permafrost permanezcan en su lecho de hielo por toda la eternidad."
        ),
    ]
    return "\n\n".join(p.strip() for p in paragraphs)


def build_moku_saltmine(topic: str, **kwargs: Any) -> str:
    """Story 7: Ancient Salt Mine Crypt & Subsurface Seismic Station."""
    paragraphs = [
        (
            "La memoria de los antiguos canteros y barrenistas de los Cárpatos debe servir como recordatorio eterno de la fragilidad de nuestras obras frente a la inmensidad geológica de la Tierra. "
            "Aquellos hombres sabían escuchar el crujido de la sal y retirarse a tiempo cuando los estratos profundos comenzaban a gemir bajo tensiones incompatibles con la vida. "
            "Nuestra ingeniería moderna, dotada de perforadoras hidráulicas y sensores satelitales, a menudo olvida la prudencia instintiva de quienes labraron las galerías a mano con pico y pala. "
            "No todo lo que se encuentra en las entrañas de la tierra debe ser extraído o expuesto al público: hay secretos que deben permanecer para siempre en la oscuridad de las criptas minerales."
        ),
        (
            "Durante las semanas de rehabilitación médica tras mi rescate de la mina de sal, tuve acceso a los informes químicos periciales realizados sobre las costras de mineral negro recuperadas de mi equipo de trabajo. "
            "Los ensayos de difracción de rayos X revelaron que la sustancia no presentaba una red cristalina convencional, sino una estructura atómica cuasicristalina con simetrías de orden cinco y siete, incompatibles con las leyes cristalográficas de los sólidos naturales de la Tierra. "
            "Los químicos del instituto geológico regional no pudieron determinar el origen de la muestra ni replicar sus propiedades de conductividad térmica en laboratorio, reconociendo en privado que se asemejaba a materiales sintéticos desarrollados en programas aeroespaciales de vanguardia. "
            "La confirmación de que una manufactura tan sofisticada yacía encastrada en estratos evaporíticos depositados hace más de doce millones de años destruía de raíz todas las teorías aceptadas sobre la evolución tecnológica de nuestro planeta. "
            "El miedo a las consecuencias académicas y políticas de semejante hallazgo motivó el inmediato archivo confidencial de las actas y la destrucción intencionada de los testigos minerales restantes."
        ),
        (
            "Asimismo, los análisis acústicos de las ondas de choque registradas por los acelerómetros de la bocamina demostraron que la inundación con salmuera saturada había generado un sellado osmótico perfecto en la cripta. "
            "El peso del agua mineralizada, con una gravedad específica superior a uno punto dos, actuó como una barrera hidrostática que neutralizó la descompresión del sarcófago y devolvió a la entidad a su estado de latencia milenaria. "
            "Los antiguos mineros de los Cárpatos, guiados por una intuición ancestral transmitida de padres a hijos a lo largo de generaciones de trabajo subterráneo, comprendían la sal mejor que cualquier laboratorio contemporáneo: la veían como un bálsamo sagrado que purifica y retiene lo profano en el fondo de la tierra. "
            "Su sacrificio y su silencio salvaron a las poblaciones de los valles circundantes de una catástrofe telúrica cuyas dimensiones apenas podemos vislumbrar hoy en día."
        ),
        (
            "La cordillera de los Cárpatos guarda en sus entrañas un laberinto de criptas y galerías donde el tiempo histórico no tiene significado ni valor. "
            "El ser humano explora la superficie de las montañas, tala sus bosques y construye ciudades en sus faldas, pero bajo sus pies late un mundo de piedra y sal donde duermen fuerzas que jamás deben ser convocadas a la superficie. "
            "Que la halita milenaria conserve su pureza y su silencio eterno, protegiendo nuestro presente de las sombras del pasado más remoto y tenebroso."
        ),
        (
            f"A setecientos metros de profundidad en las antiguas minas de sal de los Cárpatos orientales, donde las paredes de halita pura forman criptas translúcidas de silencio milenario, los acontecimientos aterradores de {topic} desafiaron toda explicación geológica. "
            "Fui contratado como especialista en micro-sismicidad profunda para supervisar una estación de monitoreo geofísico instalada en una de las galerías abandonadas del nivel seis de la mina, una cavidad colosal excavada en el siglo dieciocho y clausurada tras inundaciones kársticas no controladas. "
            "La catedral de sal subterránea presentaba bóvedas de más de cuarenta metros de altura talladas en roca salina grisácea, donde la humedad ambiental era nula y la salinidad del aire confería una conservación perpetua a cualquier materia orgánica depositada en su interior. "
            "El silencio en ese nivel mineral es absoluto y corpóreo: amortigua el eco de los pasos hasta extinguirlo y genera en el cerebro humano una desorientación propioceptiva tras pocas horas de permanencia continuada. "
            "Mi trabajo consistía en calibrar una matriz de sismógrafos triaxiales de banda ancha instalados sobre bloques de granito anclados al lecho de roca madre para registrar micro-sismos inducidos por el reacomodo de esfuerzos en la cuenca tectónica regional. "
            "Durante las primeras semanas de inspección solitaria, los sismogramas mostraron únicamente la sismicidad difusa propia de una cuenca evaporítica estable sin indicios de fallas activas cercanas. "
            "Sin embargo, al aproximarse el solsticio de invierno, los sismómetros de pozo comenzaron a registrar trenes de ondas Rayleigh de frecuencia ultra baja que no coincidían con ninguna fuente sísmica conocida. "
            "El foco de los temblores no se localizaba en una fractura tectónica regional, sino en una anomalía puntual situada a cuatrocientos metros bajo el suelo salino de la propia cámara donde operaba mi puesto de control."
        ),
        (
            "A las dos de la madrugada de una noche glacial en la superficie, los monitores de registro continuo comenzaron a trazar ondas sinusoidales de amplitud creciente que hacían vibrar los estantes metálicos del laboratorio subterráneo. "
            "Descendí por la rampa de servicio hacia el extremo este de la bóveda, donde los antiguos mineros habían interrumpido bruscamente las labores de extracción en mil ochocientos noventa y cuatro tras topar con una formación geológica anómala. "
            "Al alumbrar las paredes de sal con la lámpara halógena de inspección, noté que los bloques de halita presentaban vetas de un mineral negro y vítreo, de dureza extrema, que no reaccionaba a los ácidos de prueba ni mostraba solubilidad en agua. "
            "El mineral desconocido crecía en prismas hexagonales concéntricos que formaban arcos ojivales tallados directamente en la sal fósil con una simetría arquitectónica ajena a cualquier proceso de cristalización natural. "
            "Acerqué el micrófono geofónico a la superficie pulida del mineral negro y en mis auriculares resonó una cadencia de impactos metálicos lentos, como el golpeteo rítmico de un martillo de forja golpeando un yunque ciclópeo en las profundidades de la corteza. "
            "El aire en la galería, habitualmente seco y templado a catorce grados centígrados, comenzó a enfriarse súbitamente, alcanzando registros bajo cero que provocaban la condensación de escarcha salina sobre el cristal de mi casco de seguridad. "
            "Un olor penetrante a azufre nativo y salmuera ancestral impregnó la estancia mientras el suelo de la bóveda crujía con una vibración que estremecía los cimientos de roca viva."
        ),
        (
            "Frente al testero final de la galería descubrí una hendidura vertical de tres metros de altura que se abría en la pared de sal, revelando el acceso a una cavidad interior que no figuraba en ninguno de los planos topográficos históricos de la explotación minera. "
            "Penetré con cautela en el interior de la cripta subterránea empuñando la lámpara halógena y el detector multigás para monitorizar los niveles de metano y monóxido de carbono en la atmósfera confinada. "
            "El habitáculo estaba tallado íntegramente en sal gema pura, pero el suelo no era de roca irregular, sino de losas pulidas de basalto oscuro encastradas con juntas de plomo fundido que formaban un mosaico de laberintos circulares. "
            "En el centro de la cámara subterránea descansaba un sarcófago monolítico de piedra negra de cuatro metros de longitud, cuyas caras laterales estaban cubiertas por bajorrelieves que representaban procesiones de figuras humanas arrodilladas ante una esfera alada sostenida por tentáculos. "
            "El contador Geiger marcaba niveles de radiación gamma completamente nulos, pero el magnetómetro digital registraba anomalías de varios miles de nanoteslas que hacían oscilar descontroladamente la aguja de la brújula geológica. "
            "Al posar la mano enguantada sobre la tapa del sarcófago, sentí cómo una vibración pulsante, similar al pulso arterial de un organismo biológico vivo, se transmitía a través del granito con una fuerza que hizo retroceder mi brazo en un espasmo involuntario. "
            "Desde las hendiduras selladas con plomo de la cubierta del sarcófago comenzó a filtrarse un gas blanquecino y gélido que desprendía un susurro sibilante que resonó en la bóveda con la fuerza de un coro litúrgico milenario."
        ),
        (
            "El pánico me hizo retroceder hacia la salida de la cripta, pero al cruzar el umbral de sal un estruendo ensordecedor sacudió la mina cuando un desprendimiento de toneladas de bloques de halita bloqueó la rampa principal de acceso al nivel superior. "
            "La vía de evacuación convencional hacia el pozo del montacargas de superficie estaba completamente cegada por un alud de roca salina y polvo asfixiante que redujo la visibilidad a menos de medio metro. "
            "Estaba atrapado a setecientos metros bajo tierra con una dotación de oxígeno en mi equipo de respiración autónoma para cuatro horas y sin cobertura de radio con los operarios de guardia en la bocamina exterior. "
            "Regresé al módulo científico de la galería para buscar el teléfono de hilo de cobre de emergencia que conectaba directamente con la sala de cabrestante del pozo principal. "
            "Al descolgar el auricular de baquelita no escuché el tono de línea ni la voz del operador de superficie, sino una letanía pausada, articulada en latín eclesiástico arcaico, que describía cómo los mineros del siglo diecinueve habían sellado la cripta para contener a la entidad que habitaba bajo los estratos evaporíticos. "
            "'Aquel que descansa en la sal no debe ser despertado por la curiosidad de los vivos; su sueño mantiene la estabilidad de las fallas y su despertar fracturará los cimientos de la cordillera', repetía la voz con una serenidad sepulcral que heló mi sangre en las venas."
        ),
        (
            "Revisé frenéticamente los cajones del escritorio del módulo y encontré un diario encuadernado en cuero marrón perteneciente al capataz jefe de la explotación minera fechado en mil ochocientos noventa y cuatro. "
            "Las páginas manuscritas relataban cómo durante las obras de ensanche del nivel seis los barrenistas habían interceptado la cámara sepulcral y cómo una fiebre inexplicable comenzó a diezmar a las cuadrillas de trabajo en cuestión de días. "
            "Los obreros sufrían ceguera temporal, alucinaciones táctiles donde sentían que cristales de sal crecían bajo su propia piel y una compulsión morbosa por regresar a la cripta para arrojar ofrendas al sarcófago. "
            "El capataz ordenó dinamitar las galerías de acceso y consagrar el nivel con oraciones perpetuas, clausurando la explotación y declarando oficialmente que la mina se había vuelto estéril por infiltraciones de agua freática. "
            "El diario advertía expresamente que si alguna vez la cripta volvía a ser profanada, la única forma de neutralizar la apertura del sarcófago consistía en inundar la cámara con salmuera saturada para restablecer la presión osmótica de confinamiento. "
            "Recordé que en la galería adyacente existía una válvula de compuerta conectada a un depósito subterráneo de aguas salinas estancadas utilizado en los antiguos sistemas de lixiviación de halita."
        ),
        (
            "Corrí hacia la sala de bombas auxiliar esquivando los bloques de sal que continuaban desprendiéndose del techo de la bóveda bajo el embate de los temblores micro-sísmicos. "
            "La pesada rueda de hierro de la válvula de compuerta estaba cubierta por una gruesa capa de corrosión salina y herrumbre que resistía mis primeros intentos desesperados de giro manual. "
            "Utilicé una barra de palanca de acero para forzar el mecanismo con todo el peso de mi cuerpo hasta que los engranajes cedieron con un crujido metálico que liberó un torrente estruendoso de salmuera presurizada. "
            "El agua salada, densa y fría como la brea líquida, comenzó a inundar las galerías inferiores en una marea arrolladora que arrastraba sedimentos y fragmentos de roca hacia la boca de la cripta abierta. "
            "Desde el interior de la cámara del sarcófago emergió un chillido desgarrador que reverberó en la halita con la fuerza de un trueno subterráneo, retorciéndose mientras el agua saturada de cloruro sódico cubría las losas de basalto y sellaba las hendiduras del monumento. "
            "Aproveché la presión hidrostática del torrente para impulsarme hacia un conducto de ventilación vertical que conectaba el nivel seis con las galerías superiores del nivel cuatro, escalando por las grapas de hierro incrustadas en la roca salina."
        ),
        (
            "Alcancé el nivel cuatro exhausto, con los pulmones ardiendo por la inhalación de polvo salino y las rodillas ensangrentadas por los roces contra los salientes escarpados de la pared. "
            "En esa cota superior, los equipos de rescate de la brigada de salvamento minero ya habían comenzado las labores de perforación de alivio tras registrar el colapso sísmico en los acelerómetros de superficie. "
            "Golpeé rítmicamente las tuberías de aire comprimido con mi barra de acero para emitir la señal de socorro internacional hasta que las cuadrillas de rescate lograron perforar un barreno de comunicación por el que me suministraron oxígeno fresco y suero hidratante. "
            "Cuatro horas más tarde fui extraído a la superficie en la cesta de rescate, emergiendo a la luz gélida de una mañana de invierno en las montañas donde ambulancias y patrullas de gendarmería esperaban mi llegada. "
            "El informe técnico de la delegación de minas catalogó el suceso como un desprendimiento kárstico inducido por la reactivación de un acuífero profundo, ordenando el sellado definitivo con hormigón armado de todas las bocaminas y pozos de ventilación de la explotación. "
            "La empresa concesionaria desmanteló la estación sísmica en una semana y las autoridades provinciales declararon la montaña zona de exclusión geológica por riesgo inminente de subsidencia del terreno."
        ),
        (
            "Informes sismológicos posteriores analizados confidencialmente por geofísicos del observatorio continental demostraron que la inundación de la cripta había detenido por completo la emisión de ondas Rayleigh de frecuencia ultra baja en la cuenca. "
            "La corteza profunda bajo los Cárpatos orientales recuperó su estabilidad basal, confirmando que la salmuera saturada actuaba como un fluido de confinamiento viscoelástico que amortiguaba las oscilaciones de la masa subterránea. "
            "Varios geólogos que participaron en las comisiones periciales reconocieron en privado que la existencia de cámaras megalíticas prehistóricas excavadas en estratos de sal del Mioceno era una imposibilidad biológica y técnica según la cronología académica oficial. "
            "Sin embargo, las muestras de mineral negro recuperadas de mis botas presentaban estructuras reticulares que no figuraban en ningún catálogo mineralógico del planeta, sugiriendo una manufactura artificial de antigüedad inconcebible. "
            "La totalidad del archivo técnico de la mina fue confiscado por los servicios de seguridad del Estado y clasificado bajo secreto militar permanente para evitar especulaciones públicas sobre los hallazgos del nivel seis."
        ),
        (
            "Hoy en día, las minas de sal de los Cárpatos permanecen selladas bajo millones de toneladas de hormigón y roca, sumidas en una oscuridad que ningún ser humano volverá a perturbar. "
            "La experiencia vivida en aquella catedral de sal me enseñó que la historia geológica de nuestro planeta guarda secretos que escapan a nuestra comprensión científica convencional y que hay criptas cuyo sello debe ser respetado a cualquier costo. "
            "La sal no es solo un compuesto mineral o un recurso comercial: en las profundidades de la tierra actúa como un conservador universal que retiene tanto la pureza de los océanos fósiles como el confinamiento de terrores milenarios que no deben despertar. "
            "Mi testimonio es un tributo a los mineros olvidados que dieron su vida para sellar aquella galería y una advertencia inquebrantable para quienes confunden la soberbia técnica con la verdadera sabiduría."
        ),
        (
            "Para concluir este relato sobre los abismos de la halita, quiero dejar una última reflexión para todos los exploradores y profesionales que descienden a las entrañas de la tierra. "
            "Cuando la roca comience a crujir con un pulso que no proviene de la gravedad y los ecos de la caverna respondan a tus pasos con ritmos deliberados, no busques respuestas ni intentes desafiar lo desconocido. "
            "Respeta el silencio milenario de los abismos, retrocede hacia la luz del sol y permite que los secretos de la tierra permanezcan sepultados en su lecho de roca por toda la eternidad. "
            "Hay misterios que pertenecen al reino de la oscuridad y que jamás deben ser revelados a la luz de los vivos bajo ninguna circunstancia humana o justificación científica aparente, pues la paz del mundo depende de su sueño imperturbable."
        ),
    ]
    return "\n\n".join(p.strip() for p in paragraphs)
