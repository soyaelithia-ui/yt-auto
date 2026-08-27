"""
src/core/scp_lore.py - Canonical SCP Lore Knowledge Base & Grounding Engine.

Provides structured canonical knowledge, sensory cues, visual prompt descriptors,
and deterministic validation for major SCP anomalies across the YT_auto video pipeline.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class SCPLoreEntry:
    """Structured canonical representation of an SCP anomaly."""
    scp_id: str
    canonical_name: Dict[str, str]
    object_class: str
    aliases: Tuple[str, ...]
    key_facts: Tuple[str, ...]
    sensory_cues: Dict[str, str]
    visual_descriptors: Tuple[str, ...]
    required_keywords: Tuple[str, ...]
    forbidden_misconceptions: Dict[str, str]
    narrative_hooks: Tuple[str, ...]
    containment_summary: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


SCP_LORE_DATABASE: Dict[str, SCPLoreEntry] = {
    "SCP-087": SCPLoreEntry(
        scp_id="SCP-087",
        canonical_name={"es": "El Pozo de las Escaleras", "en": "The Stairwell"},
        object_class="Euclid",
        aliases=(
            "087", "scp087", "the stairwell", "el pozo de las escaleras",
            "la escalera", "escalera infinita", "escalera oscura", "stairwell"
        ),
        key_facts=(
            "Un tramo de escaleras de plataforma sin fin que desciende indefinidamente en completa oscuridad.",
            "Absorbe la luz visible: ninguna fuente lumínica puede iluminar más de un tramo y medio (aproximadamente 38 escalones).",
            "Se escuchan constantemente los sollozos y súplicas de un niño a cientos de metros bajo tierra, pero descender no reduce la distancia acústica.",
            "Manifestación de SCP-087-1: un rostro humanoide pálido y flotante, sin boca visible, sin fosas nasales ni pupilas definidas, inmóvil en la penumbra.",
            "Ubicado en el campus de una universidad no revelada, protegido por una puerta de acero reforzado con cerradura electromecánica.",
            "Se realizaron 4 exploraciones oficiales con personal Clase D antes de que la entrada fuera sellada permanentemente con 75 cm de hormigón.",
        ),
        sensory_cues={
            "visual": "Oscuridad absoluta e impenetrable que devora los haces de linterna, peldaños de concreto desgastados de 38 grados, rostro pálido e inexpresivo flotando en la sombra.",
            "auditory": "Llanto infantil distante en eco continuo, pasos lentos que resuenan en el vacío de concreto, silencio opresivo entre descansillos.",
            "tactile": "Descenso gélido de temperatura conforme se baja, paredes de hormigón húmedas y frías.",
        },
        visual_descriptors=(
            "endless dark concrete stairwell descending into pitch blackness",
            "flashlight beam swallowed by supernatural darkness in stairwell",
            "pale floating humanoid face without pupils or mouth emerging from shadows",
            "heavy industrial steel containment door in university basement with warning signs",
        ),
        required_keywords=(
            "escalera", "oscuridad", "llanto", "rostro", "peldaño", "087-1",
            "linterna", "descenso", "profundidad", "universidad"
        ),
        forbidden_misconceptions={
            "escalera que sube": "SCP-087 solo desciende indefinidamente; nunca asciende.",
            "monstruo con garras": "SCP-087-1 es un rostro flotante sin cuerpo discernible ni garras.",
            "llegó al fondo": "Ninguna exploración llegó jamás a un fondo o piso final.",
        },
        narrative_hooks=(
            "¿Bajarías una escalera infinita donde los llantos de un niño nunca se acercan?",
            "Esta escalera devora la luz de tu linterna al tercer escalón, y algo abajo te está mirando.",
            "Cuatro exploradores bajaron por esta escalera universitaria: ninguno volvió a ser el mismo.",
        ),
        containment_summary="Puerta de acero reforzado con cerradura electro-magnética en sótano universitario, sellada con 75 cm de hormigón tras Exploración IV.",
    ),

    "SCP-096": SCPLoreEntry(
        scp_id="SCP-096",
        canonical_name={"es": "El Chico Tímido", "en": "The Shy Guy"},
        object_class="Euclid",
        aliases=(
            "096", "scp096", "the shy guy", "el chico timido",
            "el timido", "shy guy", "el hombre timido"
        ),
        key_facts=(
            "Humanoide de aproximadamente 2.38 metros de altura, con piel pálida desprovista de pigmentación y brazos desproporcionadamente largos de 1.5 metros.",
            "Mandíbula capaz de abrirse hasta cuatro veces el tamaño de la de un humano normal.",
            "Dócil e inofensivo mientras nadie observe su rostro; pasa el tiempo caminando en círculos y sollozando.",
            "Al observar su rostro (en persona, por grabación o en fotografía, incluso 4 píxeles), entra en un estado de angustia extrema, cubre su rostro, grita y balbucea.",
            "Tras 1-2 minutos entra en fase de persecución imparable: corre a velocidades de más de 35 km/h hacia SCP-096-1 sin que ningún blindaje pueda detenerlo.",
            "Los dibujos artísticos no desencadenan su reacción hostil.",
        ),
        sensory_cues={
            "visual": "Humanoide alto, demacrado, piel translúcida y pálida, brazos larguísimos, mandíbula desencajada de forma monstruosa, lágrimas de angustia.",
            "auditory": "Llanto agónico y balbuceos iniciales que escalan a un alarido ensordecedor e histérico durante la persecución.",
            "tactile": "Impactos demoledores de fuerza bruta contra muros de acero y concreto.",
        },
        visual_descriptors=(
            "tall emaciated pale humanoid sitting in corner weeping covering face",
            "distressed white figure with elongated arms and unhinged jaw screaming",
            "unbreakable pursuit breaking through steel reinforced containment walls",
            "scramble visor goggles static interference in dark military facility",
        ),
        required_keywords=(
            "rostro", "cara", "mirar", "ver", "foto", "fotografía",
            "perseguir", "mandíbula", "gritar", "llanto", "píxeles", "096-1"
        ),
        forbidden_misconceptions={
            "ataca a ciegas": "SCP-096 solo ataca a quien ha visto su rostro; es totalmente pacífico con quienes no lo han visto.",
            "los dibujos lo enfurecen": "Los dibujos y bocetos artísticos NO provocan su furia; solo fotos y video.",
            "se puede matar con balas comunes": "El tejido y esqueleto de SCP-096 resisten fuego antitanque y destrucción física masiva.",
        },
        narrative_hooks=(
            "Si viste solo cuatro píxeles de su rostro en una foto de fondo, ya estás muerto.",
            "No importa si estás a diez mil kilómetros de distancia: una vez que viste su cara, nada lo detendrá.",
            "Este ser llora en un rincón, pero si cruzas miradas con él, desatarás una pesadilla imparable.",
        ),
        containment_summary="Celda de acero hermética de 5m x 5m x 5m sin cámaras ni sensores ópticos. Monitoreo por sensores de presión y láseres perimetrales.",
    ),

    "SCP-173": SCPLoreEntry(
        scp_id="SCP-173",
        canonical_name={"es": "La Escultura", "en": "The Sculpture"},
        object_class="Euclid",
        aliases=(
            "173", "scp173", "the sculpture", "la escultura",
            "el cacahuate", "peanut", "the original", "la estatua"
        ),
        key_facts=(
            "Estatua construida de hormigón y barras de refuerzo metálicas, con pintura en aerosol marca Krylon.",
            "Completamente animada y extremadamente hostil.",
            "Incapaz de moverse mientras se encuentre dentro de una línea de visión directa e ininterrumpida de cualquier observador.",
            "En el instante en que el contacto visual se rompe (incluso un parpadeo de medio segundo), se desplaza a velocidad extrema y rompe el cuello en la base del cráneo.",
            "Produce una mezcla rojiza de heces y sangre en el suelo de su celda que debe ser limpiada periódicamente por 3 personales Clase D.",
        ),
        sensory_cues={
            "visual": "Figura de hormigón desgastado con cabeza bulbosa y manchas de pintura facial verde y negra; charcos rojizos en el suelo.",
            "auditory": "Sonido chirriante de raspado de piedra sobre hormigón en la celda vacía; chasquido seco de vértebras quebrándose.",
            "tactile": "Hormigón áspero, frío y macizo.",
        },
        visual_descriptors=(
            "concrete and rebar statue with bulbous head and spray-painted face in containment cell",
            "three class-d personnel in orange jumpsuits maintaining strict eye contact",
            "dark concrete chamber with reddish-brown biological residue on floor",
            "motion blur snap instant neck snap in containment facility",
        ),
        required_keywords=(
            "parpadear", "parpadeo", "hormigón", "concreto", "contacto visual",
            "mirada", "cuello", "estatua", "escultura", "clase d", "raspar"
        ),
        forbidden_misconceptions={
            "se mueve mientras lo miras": "SCP-173 queda completamente inmóvil bajo la mirada directa; solo se mueve al pestañear o romper visión.",
            "está hecho de metal y carne": "Está compuesto de hormigón, barras de refuerzo y pintura en aerosol.",
        },
        narrative_hooks=(
            "No parpadees. Si cierras los ojos un solo segundo, tu cuello estará roto.",
            "Tres hombres entraron a limpiar su celda: uno parpadeó sin avisar y el sonido del chasquido fue instantáneo.",
            "Esta escultura de concreto parece inmóvil, pero se mueve más rápido que la luz cuando no la miras.",
        ),
        containment_summary="Celda cerrada de hormigón. Toda entrada requiere 3 personas; 2 deben mantener contacto visual constante avisando antes de pestañear.",
    ),

    "SCP-049": SCPLoreEntry(
        scp_id="SCP-049",
        canonical_name={"es": "El Doctor de la Peste", "en": "Plague Doctor"},
        object_class="Euclid",
        aliases=(
            "049", "scp049", "plague doctor", "el doctor de la peste",
            "doctor de la peste", "el doctor de la plaga", "el medico de la peste", "doctor plaga"
        ),
        key_facts=(
            "Entidad humanoide que viste las ropas y máscara picuda de un médico de la peste medieval del siglo XV.",
            "Las prendas y la máscara son crecimientos de tejido biológico fusionados con su cuerpo.",
            "Capaz de hablar múltiples idiomas (con preferencia por el francés y latín) y tiene modales refinados y elocuentes.",
            "Su toque directo a la piel humana detiene todas las funciones biológicas causando muerte instantánea.",
            "Afirma que la humanidad está infectada por 'La Gran Pestilencia' y realiza cirugías toscas con su maletín de instrumentos para reanimar cadáveres (SCP-049-2).",
        ),
        sensory_cues={
            "visual": "Túnica de cuero negro y máscara de cuervo pálida de aspecto óseo; instrumental quirúrgico arcaico oxidado.",
            "auditory": "Voz pausada, culta y educada con ligero acento antiguo; tintineo metálico de bisturíes; silencio mortal tras su roce.",
            "tactile": "Guantes de piel orgánica fríos y letales al contacto.",
        },
        visual_descriptors=(
            "humanoid plague doctor in black robes with pointed ceramic beak mask in sterile interrogation room",
            "leather medical bag with antique surgical instruments on metal table",
            "calm ominous figure reaching gloved hand toward camera",
            "reanimated surgical subject rising from operating table",
        ),
        required_keywords=(
            "peste", "pestilencia", "cura", "máscara", "doctor", "médico",
            "cirugía", "toque", "túnica", "049-2", "reanimar"
        ),
        forbidden_misconceptions={
            "es un humano con disfraz": "Sus ropas y máscara son tejido vivo y cuero orgánico que crecieron de su cuerpo.",
            "cura enfermedades comunes": "La 'Pestilencia' es una afección anómala que solo él percibe; su cura reanima a los muertos sin consciencia.",
        },
        narrative_hooks=(
            "Dice tener la cura definitiva para la humanidad, pero su toque detiene tu corazón al instante.",
            "Bajo esa máscara de médico medieval no hay porcelana ni tela: es su propia piel y hueso vivo.",
            "No intentes razonar cuando te diga que hueles a 'La Pestilencia': serás su próximo paciente.",
        ),
        containment_summary="Celda humanoide reforzada en Sitio-19. Sedado con sedantes en aerosol antes de interactuar y escoltado con varas de choque.",
    ),

    "SCP-3008": SCPLoreEntry(
        scp_id="SCP-3008",
        canonical_name={"es": "Un IKEA Infinito", "en": "A Perfectly Normal, Regular Old IKEA"},
        object_class="Euclid",
        aliases=(
            "3008", "scp3008", "infinite ikea", "ikea infinito",
            "ikea interminable", "un ikea totalmente normal", "ikea"
        ),
        key_facts=(
            "Entrada a través de una tienda IKEA que conduce a un espacio no euclidiano de dimensiones infinitas sin salida visible.",
            "Alberga asentamientos y fortalezas construidas con sofás y muebles por civiles atrapados de por vida.",
            "Tiene un ciclo de día y noche gobernado por la iluminación del techo.",
            "Durante la noche (luces apagadas), las instancias de SCP-3008-2 (empleados sin rostro en camisas amarillas) se vuelven agresivas y cazan a los humanos.",
            "Durante el día, los empleados son completamente pasivos e ignoran a los humanos.",
        ),
        sensory_cues={
            "visual": "Pasillos interminables de estanterías y muebles; fortalezas de sofás; luces parpadeantes; humanoides sin rostro con camisetas a rayas.",
            "auditory": "Mensaje en megafonía: 'La tienda está cerrada, por favor abandone el edificio'; pisadas pesadas en la oscuridad nocturna.",
            "tactile": "Desorientación espacial en un laberinto infinito de pasillos idénticos.",
        },
        visual_descriptors=(
            "endless infinite interior of furniture megastore with towering shelves reaching horizon",
            "fortress built from stacked sofas tables and mattresses in vast warehouse",
            "faceless tall humanoid staff in yellow and blue polo shirt in dark aisle",
            "dim emergency lighting with shadows between endless furniture displays",
        ),
        required_keywords=(
            "ikea", "tienda", "muebles", "infinito", "laberinto", "empleados",
            "sin rostro", "3008-2", "cerrada", "luces", "atrapados", "fortaleza"
        ),
        forbidden_misconceptions={
            "es una tienda con muchas salidas": "Es un espacio no euclidiano infinito sin salida fija ni mapa.",
            "empleados normales": "Las instancias 3008-2 son entidades humanoides desproporcionadas sin rostro ni órganos faciales.",
        },
        narrative_hooks=(
            "Entraste a comprar un mueble y ahora estás atrapado en un laberinto infinito de miles de kilómetros.",
            "Cuando las luces de este IKEA se apagan, los empleados sin rostro comienzan su cacería nocturna.",
            "En esta tienda infinita, los supervivientes construyen fortalezas con sofás para no ser devorados de noche.",
        ),
        containment_summary="Edificio exterior rodeado por perímetro militar Sitio-Mil-Tres con acceso bajo vigilancia constante.",
    ),

    "SCP-682": SCPLoreEntry(
        scp_id="SCP-682",
        canonical_name={"es": "El Reptil Difícil de Destruir", "en": "Hard-to-Destroy Reptile"},
        object_class="Keter",
        aliases=(
            "682", "scp682", "hard to destroy reptile", "el reptil",
            "reptil dificil de destruir", "el reptil indestructible", "reptil indestructible"
        ),
        key_facts=(
            "Criatura reptiliana gigante con odio implacable y absoluto hacia toda forma de vida orgánica.",
            "Capacidad de regeneración y adaptación evolutiva casi instantánea ante cualquier forma de daño, ácido, toxina o radiación.",
            "Permanece sumergido constantemente en ácido clorhídrico concentrado para ralentizar su crecimiento.",
            "Posee alta inteligencia y habla con desprecio y hostilidad.",
        ),
        sensory_cues={
            "visual": "Masa reptiliana titánica con escamas corroidas, piel pudriéndose y regenerándose simultáneamente, ojos llenos de desprecio.",
            "auditory": "Gruñido gutural profundo y chasquido de mandíbulas triturando acero.",
            "tactile": "Ácido burbujeante caliente, vibración sísmica en la celda de contención.",
        },
        visual_descriptors=(
            "massive monstrous decaying reptile submerged in giant vat of bubbling green acid",
            "heavy reinforced acid-resistant steel chamber with blast doors and observation window",
            "regenerating reptilian beast with exposed bone and necrotic tissue roaring in fury",
        ),
        required_keywords=(
            "reptil", "regeneración", "ácido", "inmortal", "adaptación", "odio",
            "destruir", "keter", "tanque", "ácido clorhídrico", "vida"
        ),
        forbidden_misconceptions={
            "es un dinosaurio común": "Es una entidad anómala de origen desconocido con adaptación trascendental.",
            "se puede matar con balas comunes": "Las armas convencionales solo ralentizan su crecimiento; se regenera e inmuniza.",
        },
        narrative_hooks=(
            "La Fundación ha intentado destruirlo con bombas nucleares y ácido, pero cada intento solo lo hace más fuerte.",
            "Odia a toda la vida en el universo y no existe arma conocida capaz de matarlo.",
        ),
        containment_summary="Tanque sellado revestido con placas de aleación resistentes a ácidos, completamente sumergido en ácido clorhídrico concentrado.",
    ),

    "SCP-106": SCPLoreEntry(
        scp_id="SCP-106",
        canonical_name={"es": "El Anciano", "en": "The Old Man"},
        object_class="Keter",
        aliases=(
            "106", "scp106", "the old man", "el anciano",
            "radical larry", "el viejo", "anciano corrosivo"
        ),
        key_facts=(
            "Humanoide anciano en avanzado estado de descomposición recubierto de lodo negro corrosivo.",
            "Atraviesa superficies sólidas y arrastra a sus presas hacia su 'Dimensión de Bolsillo'.",
            "La contención emplea el protocolo del 'Femur Breaker' para atraerlo con el sonido del dolor de un Clase D.",
        ),
        sensory_cues={
            "visual": "Figura cadavérica goteando lodo negro espeso, corrosión oxidada extendiéndose por paredes.",
            "auditory": "Siseo corrosivo de materia derritiéndose y chapoteo viscoso de pisadas.",
            "tactile": "Lodo negro cáustico que quema la piel, olor a carne descompuesta.",
        },
        visual_descriptors=(
            "decayed elderly humanoid coated in black corrosive sludge phasing through solid steel wall",
            "rusted multi-layered lead lined containment cell suspended by magnetic fields",
            "dark pocket dimension labyrinth with decaying endless corridors and black liquid floors",
        ),
        required_keywords=(
            "anciano", "corrosión", "corrosivo", "dimensión de bolsillo", "lodo negro",
            "atravesar", "fémur", "descomposición", "presa", "materia"
        ),
        forbidden_misconceptions={
            "es un fantasma intangible": "Es una entidad física que secreta sustancia corrosiva real.",
        },
        narrative_hooks=(
            "Puede atravesar paredes sólidas dejando un rastro de lodo negro que derrite el acero.",
            "Si te atrapa, no te matará de inmediato: te llevará a su dimensión de bolsillo para cazarle en la oscuridad.",
        ),
        containment_summary="Celda de plomo suspendida magnéticamente dentro de 43 capas concéntricas. Protocolo de cebo 106-Erec.",
    ),

    "SCP-093": SCPLoreEntry(
        scp_id="SCP-093",
        canonical_name={"es": "El Objeto del Mar Rojo", "en": "Red Sea Object"},
        object_class="Euclid",
        aliases=(
            "093", "scp093", "red sea object", "el objeto del mar rojo",
            "disco rojo", "objeto del mar rojo", "espejo del mar rojo"
        ),
        key_facts=(
            "Disco rojo de cinabrio que convierte los espejos en portales a una realidad paralela devastada.",
            "El mundo alterno fue aniquilado por entidades colosales de carne deformes llamadas 'Los Inmundos'.",
            "El color del disco cambia según la psique de quien lo sostiene.",
        ),
        sensory_cues={
            "visual": "Disco de piedra roja pulida vibrando; superficie del espejo ondulando como líquido.",
            "auditory": "Zumbido armónico de cristal resonando; gemidos guturales pesados en la distancia.",
            "tactile": "Superficie de espejo que se siente como mercurio tibio.",
        },
        visual_descriptors=(
            "red stone disk with intricate carved circular runes resting against large full-length mirror",
            "mirror surface rippling like liquid portal showing desolate wasteland on other side",
            "massive grotesque fleshy torso of unclean being crawling across sepia colored desert",
        ),
        required_keywords=(
            "disco", "espejo", "portal", "realidad", "mar rojo", "inmundos",
            "cinabrio", "color", "exploración", "lágrimas"
        ),
        forbidden_misconceptions={
            "portal al infierno religioso": "Conduce a un universo paralelo alternativo colapsado por una biomasa anómala.",
        },
        narrative_hooks=(
            "Coloca este disco rojo sobre un espejo y el cristal se convertirá en la puerta a un mundo muerto.",
            "Cinco colores, cinco exploraciones y un planeta entero devastado por gigantes de carne deforme.",
        ),
        containment_summary="Contenedor sellado de plata en Sitio-██. Pruebas con espejos requieren autorización Nivel 4.",
    ),

    "SCP-999": SCPLoreEntry(
        scp_id="SCP-999",
        canonical_name={"es": "El Monstruo de las Cosquillas", "en": "The Tickle Monster"},
        object_class="Safe",
        aliases=(
            "999", "scp999", "the tickle monster", "el monstruo de las cosquillas",
            "monstruo de cosquillas", "gelatina naranja"
        ),
        key_facts=(
            "Masa gelatinosa naranja dócil y afectuosa con consistencia similar a mantequilla de maní.",
            "Al tocar a una persona induce euforia y cura permanentemente la depresión y el estrés postraumático.",
            "Se alimenta exclusivamente de golosinas, chocolate y galletas.",
            "Logró calmar temporalmente a SCP-682 haciéndole cosquillas.",
        ),
        sensory_cues={
            "visual": "Gota gelatinosa naranja brillante que extiende pseudópodos amistosos.",
            "auditory": "Gorjeos agudos de risa y risas incontrolables de quienes lo abrazan.",
            "tactile": "Textura elástica y tibia con aroma a chocolate y galletas.",
        },
        visual_descriptors=(
            "cute friendly translucent orange gelatinous slime blob extending hugging pseudopods",
            "smiling SCP foundation researcher playing with orange jelly creature on floor",
            "bright colorful candies and chocolate wafers around playful blob in containment pen",
        ),
        required_keywords=(
            "gelatina", "naranja", "cosquillas", "euforia", "alegría", "dulces",
            "682", "felicidad", "depresión", "afección"
        ),
        forbidden_misconceptions={
            "es una criatura peligrosa": "Es genuinamente benévolo y completamente incapaz de dañar a nadie.",
        },
        narrative_hooks=(
            "En un mundo de monstruos aterradores, esta masa de gelatina naranja es lo más puro que existe.",
            "Un solo abrazo de esta criatura cura cualquier depresión y logró hacer reír al temible SCP-682.",
        ),
        containment_summary="Permitido deambular libremente por el Sitio-19. Se le proporciona un corral de juegos con golosinas.",
    ),

    "SCP-055": SCPLoreEntry(
        scp_id="SCP-055",
        canonical_name={"es": "[Desconocido] / Antimemético", "en": "[unknown]"},
        object_class="Keter",
        aliases=(
            "055", "scp055", "unknown", "desconocido",
            "antimemetico", "antimeme", "no es redondo"
        ),
        key_facts=(
            "Objeto auto-censurador: toda información sobre su naturaleza se borra de la mente tras observarlo.",
            "Solo puede describirse por negación: el hecho comprobado más célebre es que 'No es redondo'.",
            "Nadie sabe quién lo descubrió ni qué peligro representa en realidad.",
        ),
        sensory_cues={
            "visual": "Cámara sellada donde los observadores salen con la mente en blanco.",
            "auditory": "Silencio cognitivo y preguntas confusas de investigadores.",
            "tactile": "Sensación de vacío mnémico en el pensamiento.",
        },
        visual_descriptors=(
            "heavy sealed vault door with red digital question mark display in sterile corridor",
            "confused scientist staring at blank clipboard in high security containment hallway",
            "glitch visual static distortion censoring center of containment chamber",
        ),
        required_keywords=(
            "antimeme", "antimemético", "olvidar", "redondo", "memoria", "desconocido",
            "información", "mente", "secreto", "censura"
        ),
        forbidden_misconceptions={
            "es un monstruo invisible": "No es invisibilidad óptica; es un efecto antimemético que borra la información de la memoria.",
        },
        narrative_hooks=(
            "Está contenido en la celda más segura de la Fundación, pero nadie recuerda qué hay adentro.",
            "Solo sabemos una cosa sobre este objeto clasificado: definitivamente NO es redondo.",
        ),
        containment_summary="Habitación blindada en Sitio-19 con acceso restringido. Todo registro debe formularse en términos negativos.",
    ),

    "SCP-3000": SCPLoreEntry(
        scp_id="SCP-3000",
        canonical_name={"es": "Anantashesha", "en": "Anantashesha"},
        object_class="Thaumiel",
        aliases=(
            "3000", "scp3000", "anantashesha", "la anguila gigante",
            "bahia de bengala", "anguila cosmica", "dios serpiente"
        ),
        key_facts=(
            "Anguila marina colosal de 600 a 900 kilómetros en la Bahía de Bengala.",
            "Ejerce un campo memético que disuelve la memoria y la identidad humana en las profundidades.",
            "Secreta el compuesto Y-909 al alimentarse, indispensable para fabricar todos los amnésicos de la Fundación.",
        ),
        sensory_cues={
            "visual": "Oscuridad abisal del fondo oceánico; ojos gigantescos que emergen de la fosa marina.",
            "auditory": "Crujido de presión submarina en el casco de buceo; susurros incoherentes en la mente.",
            "tactile": "Presión aplastante y frío glacial del océano profundo.",
        },
        visual_descriptors=(
            "colossal abyssal sea serpent eel coiled in pitch black ocean trench",
            "deep sea submersible searchlights illuminating giant glowing reptilian eye in dark water",
            "dark oily substance Y-909 dispersing in underwater research station harvest tube",
        ),
        required_keywords=(
            "anguila", "serpiente", "amnésicos", "y-909", "memoria", "bahía de bengala",
            "profundidades", "abisal", "olvido", "thaumiel", "anantashesha"
        ),
        forbidden_misconceptions={
            "pez gigante común": "Es una entidad transdimensional que disuelve la mente humana.",
        },
        narrative_hooks=(
            "Mide seiscientos kilómetros de largo y vive en la fosa más oscura del océano devorando recuerdos.",
            "Cada vez que la Fundación borra tu memoria, están usando el líquido que extraen de este dios serpiente.",
        ),
        containment_summary="Contenido in situ en la Bahía de Bengala por el submarino SCPS Eremita y estaciones ATLS-12.",
    ),

    "SCP-5000": SCPLoreEntry(
        scp_id="SCP-5000",
        canonical_name={"es": "¿Por qué? (Pietro Wilson)", "en": "Why?"},
        object_class="Safe",
        aliases=(
            "5000", "scp5000", "why", "por que", "el traje",
            "pietro wilson", "el traje de exclusion", "traje absoluto"
        ),
        key_facts=(
            "Traje de exclusión mecánica encontrado con el cadáver de Pietro Wilson en la cámara de SCP-579.",
            "Registra una línea temporal alterna donde el Consejo O5 descubrió algo aterrador y declaró la guerra total para exterminar a la humanidad.",
            "Pietro Wilson llevó SCP-055 hasta SCP-579 para reiniciar la realidad antes de morir.",
        ),
        sensory_cues={
            "visual": "Traje táctico dañado con visor roto; pantalla parpadeando con la palabra '¿Por qué?'.",
            "auditory": "Grabaciones de audio distorsionadas de Pietro Wilson; estática de radio de bases destruidas.",
            "tactile": "Armadura pesada de aleación con soporte vital agotado.",
        },
        visual_descriptors=(
            "futuristic high-tech mechanical stealth suit damaged and kneeling in abandoned chamber",
            "post-apocalyptic ruined city with foundation aircraft spraying anomalous toxins",
            "classified tablet terminal displaying blinking text WHY alongside SCP logo",
        ),
        required_keywords=(
            "traje", "pietro wilson", "exterminio", "humanidad", "o5", "055",
            "579", "reiniciar", "guerra", "por qué", "registro"
        ),
        forbidden_misconceptions={
            "traje con magia": "Es tecnología de camuflaje no anómala en sí misma que portaba los registros temporales.",
        },
        narrative_hooks=(
            "¿Qué descubrió la Fundación SCP para decidir que la única solución era exterminar a toda la humanidad?",
            "Un solo hombre cruzó un mundo en ruinas mientras la Fundación liberaba a todos sus monstruos para matarnos.",
        ),
        containment_summary="Guardado en bóveda de almacenamiento estándar en el Sitio-22.",
    ),

    "SCP-4666": SCPLoreEntry(
        scp_id="SCP-4666",
        canonical_name={"es": "El Hombre de Navidad", "en": "The Yule Man"},
        object_class="Keter",
        aliases=(
            "4666", "scp4666", "the yule man", "el hombre de navidad",
            "el monstruo de navidad", "yule man", "weissnacht"
        ),
        key_facts=(
            "Humanoide anciano esquelético y desnudo que se manifiesta en el invierno boreal durante los 12 días del Evento Weissnacht.",
            "Acecha casas aisladas con niños menores de 8 años; asesina a la familia y secuestra a un niño.",
            "Deja juguetes rústicos toscamente fabricados con restos óseos y partes humanas de víctimas anteriores.",
        ),
        sensory_cues={
            "visual": "Silueta pálida esquelética sobre tejados nevados; juguetes manchados de sangre bajo el árbol.",
            "auditory": "Pasos sobre el tejado en la noche de Navidad; respiración helada en la ventana.",
            "tactile": "Viento polar helado; madera tosca con fragmentos de hueso.",
        },
        visual_descriptors=(
            "tall emaciated naked pale humanoid standing in blizzard on snowy roof of isolated cabin",
            "disturbing handcrafted wooden and bone toy sitting under lit christmas tree",
            "barefoot tracks in deep white snow leading to dark winter forest",
        ),
        required_keywords=(
            "navidad", "yule", "weissnacht", "invierno", "nieve", "niño",
            "juguetes", "familia", "hueso", "keter", "secuestro"
        ),
        forbidden_misconceptions={
            "santa claus mágico": "Es una de las entidades más sádicas y aterradoras del universo SCP.",
        },
        narrative_hooks=(
            "Durante las doce noches de Navidad, este ser acecha casas aisladas en la nieve buscando a su próxima víctima.",
            "Los juguetes que deja bajo el árbol no están hechos de plástico: están tallados con huesos de niños secuestrados.",
        ),
        containment_summary="Monitoreo satelital y de frecuencias de emergencia en el hemisferio norte durante el Evento Weissnacht.",
    ),
}


# Pre-build reverse alias index for fast lookups
_ALIAS_INDEX: Dict[str, str] = {}
for _canonical_id, _entry in SCP_LORE_DATABASE.items():
    # Canonical ID variations
    _ALIAS_INDEX[_canonical_id.lower()] = _canonical_id
    _ALIAS_INDEX[_canonical_id.lower().replace("-", "")] = _canonical_id
    _ALIAS_INDEX[_canonical_id.lower().replace("-", " ")] = _canonical_id
    # Canonical names
    for _name in _entry.canonical_name.values():
        _norm_name = _name.lower().strip()
        _ALIAS_INDEX[_norm_name] = _canonical_id
    # Aliases
    for _alias in _entry.aliases:
        _norm_alias = _alias.lower().strip()
        _ALIAS_INDEX[_norm_alias] = _canonical_id


def _normalize_str(text: str) -> str:
    """Normalize string for robust pattern and keyword matching."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text.lower()))


def normalize_scp_lookup_key(query: str) -> str:
    """
    Normalizes any user or pipeline input into a canonical lookup key.
    Examples: 'SCP-087' -> 'SCP-087', '087' -> 'SCP-087', 'the stairwell' -> 'SCP-087'.
    """
    if not query or not isinstance(query, str):
        return ""
    q = query.strip()
    if not q:
        return ""

    # Check numeric SCP pattern: e.g. "SCP-087", "scp87", "87", "3008"
    num_match = re.search(r"(?i)\b(?:scp[-_\s]*)?0*(\d+)\b", q)
    if num_match:
        digits = num_match.group(1)
        padded = digits.zfill(3) if len(digits) < 3 else digits
        canonical_key = f"SCP-{padded}"
        if canonical_key in SCP_LORE_DATABASE:
            return canonical_key
        # If the input was explicitly an SCP number (e.g. "SCP-99999" or "8888"),
        # do not fall through to loose substring matching that might accidentally match a prefix
        if re.search(r"(?i)\bscp[-_\s]*\d+\b", q) or q.isdigit():
            return canonical_key

    # Check alias index (exact match)
    normalized_q = _normalize_str(q)
    if normalized_q in _ALIAS_INDEX:
        return _ALIAS_INDEX[normalized_q]

    # Word boundary alias match
    for alias, canon_id in _ALIAS_INDEX.items():
        if len(alias) >= 4 and re.search(rf"\b{re.escape(alias)}\b", normalized_q):
            return canon_id

    return q


def get_scp_canonical_lore(scp_id_or_name: str) -> Optional[Dict[str, Any]]:
    """
    Returns dict of canonical elements, key facts, sensory cues, visual descriptions,
    required keywords, and narrative hooks for a given SCP identifier or name.
    Returns None if not found in curated canonical knowledge base.
    """
    key = normalize_scp_lookup_key(scp_id_or_name)
    entry = SCP_LORE_DATABASE.get(key)
    if entry:
        return entry.to_dict()
    return None


lookup_scp = get_scp_canonical_lore


def get_all_canonical_scps() -> List[str]:
    """Returns list of all catalogued canonical SCP IDs."""
    return sorted(list(SCP_LORE_DATABASE.keys()))


def is_scp_topic(topic: str) -> bool:
    """Returns True if the topic refers to an SCP anomaly."""
    if not topic or not isinstance(topic, str):
        return False
    if re.search(r"(?i)\bscp[-_\s]*\d+\b", topic):
        return True
    return get_scp_canonical_lore(topic) is not None


def get_scp_opening_hook(scp_id_or_name: str, index: int = 0) -> Optional[str]:
    """Returns a high-retention 0-3s hook grounded in official canon for the SCP."""
    lore = get_scp_canonical_lore(scp_id_or_name)
    if not lore or not lore.get("narrative_hooks"):
        return None
    hooks = lore["narrative_hooks"]
    return hooks[index % len(hooks)]


def get_scp_visual_descriptors(scp_id_or_name: str) -> List[str]:
    """Returns visual prompt descriptors for storyboard and scene generator."""
    lore = get_scp_canonical_lore(scp_id_or_name)
    if not lore or not lore.get("visual_descriptors"):
        return []
    return list(lore["visual_descriptors"])


# Forbidden out-of-genre markers for SCP/Horror scripts (AITA/domestic drama leakage)
FORBIDDEN_GENRE_POLLUTION_MARKERS: Tuple[str, ...] = (
    "soy el malo", "yo soy el malo", "mi suegra", "mi esposa me engañó",
    "herencia familiar", "aita", "infidelidad", "divorcio",
    "reddit", "subforo", "upvotes", "hilo de reddit", "consejos de pareja"
)


def validate_scp_lore(
    text: str,
    scp_id_or_name: str,
    *,
    min_keyword_matches: int = 2,
    strict_genre_check: bool = True,
) -> Tuple[bool, List[str]]:
    """
    Validates presence of core canonical elements, required lore facts, and absence of
    forbidden misconceptions or out-of-genre pollution in the generated script text.

    Returns:
        (is_valid: bool, issues: List[str])
    """
    if not text or not isinstance(text, str) or not text.strip():
        return False, ["Script text is empty or invalid."]

    lore = get_scp_canonical_lore(scp_id_or_name)
    if not lore:
        # If topic is not in curated database, pass with informative notice
        if is_scp_topic(scp_id_or_name):
            return True, [f"SCP '{scp_id_or_name}' not in curated canonical database (skipped strict lore check)."]
        return True, []

    issues: List[str] = []
    normalized_text = _normalize_str(text)
    scp_id = lore["scp_id"]

    # 1. Required Keywords Check
    req_keywords = lore.get("required_keywords", ())
    matched_keywords: List[str] = []
    for kw in req_keywords:
        norm_kw = _normalize_str(kw)
        if norm_kw and norm_kw in normalized_text:
            matched_keywords.append(kw)

    # Check numeric identifier presence (e.g. "087" or "87")
    num_match = re.search(r"\d+", scp_id)
    if num_match:
        num_str = num_match.group(0)
        raw_num = num_str.lstrip("0") or "0"
        if num_str in normalized_text or raw_num in normalized_text:
            if scp_id not in matched_keywords:
                matched_keywords.append(scp_id)

    if len(matched_keywords) < min_keyword_matches:
        issues.append(
            f"Missing core canonical lore elements for {scp_id}: found {len(matched_keywords)} "
            f"keyword(s) ({matched_keywords}), expected at least {min_keyword_matches} from {list(req_keywords)}."
        )

    # 2. Forbidden Misconceptions Check
    misconceptions = lore.get("forbidden_misconceptions", {})
    for trigger, explanation in misconceptions.items():
        norm_trigger = _normalize_str(trigger)
        if norm_trigger and norm_trigger in normalized_text:
            issues.append(f"Lore contradiction detected for {scp_id}: {explanation}")

    # 3. Strict Genre Check (prohibits AITA / family drama in SCP narratives)
    if strict_genre_check:
        for marker in FORBIDDEN_GENRE_POLLUTION_MARKERS:
            norm_marker = _normalize_str(marker)
            if norm_marker in normalized_text:
                issues.append(f"Genre pollution detected in {scp_id} script: contains domestic/AITA drama marker '{marker}'.")

    return len(issues) == 0, issues
