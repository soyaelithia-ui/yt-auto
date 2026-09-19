"""src/scrapers/scp/canonical.py - Built-in canonical fallback SCP dataset (CC BY-SA 3.0)."""

from __future__ import annotations

from typing import Any, Dict, List

from src.scrapers.scp.constants import DEFAULT_LICENSE

CANONICAL_SCP_STORIES: List[Dict[str, Any]] = [
    {
        "id": "SCP-173",
        "story_id": "SCP-173",
        "title": "SCP-173 - La Escultura",
        "item_number": "SCP-173",
        "object_class": "Euclid",
        "author": "Moto42",
        "rating": 5200,
        "url": "https://scp-wiki.wikidot.com/scp-173",
        "source_license": DEFAULT_LICENSE,
        "containment_procedures": (
            "El elemento SCP-173 debe mantenerse en un contenedor cerrado en todo momento. "
            "Cuando el personal deba ingresar al contenedor de SCP-173, no menos de 3 personas deben entrar a la vez "
            "y la puerta debe cerrarse detrás de ellos. Dos personas deben mantener contacto visual continuo con SCP-173 "
            "hasta que todo el personal haya desocupado el contenedor y la puerta haya sido cerrada y bloqueada."
        ),
        "description": (
            "Trasladado al Sitio-19 en 1993. Su origen es aún desconocido. Está construido de hormigón y barras de refuerzo "
            "con rastros de pintura en aerosol marca Krylon. SCP-173 está animado y es extremadamente hostil. El objeto "
            "no puede moverse mientras esté en una línea de visión directa. La línea de visión no debe romperse en ningún "
            "momento hacia SCP-173. El personal asignado debe advertirse mutuamente antes de parpadear. El objeto ataca "
            "rompiendo el cuello desde la base del cráneo o por estrangulación."
        ),
        "content": (
            "Ítem #: SCP-173\n"
            "Clase de Objeto: Euclid\n\n"
            "Procedimientos Especiales de Contención:\n"
            "El elemento SCP-173 debe mantenerse en un contenedor cerrado en todo momento. Cuando el personal deba ingresar "
            "al contenedor de SCP-173, no menos de 3 personas deben entrar a la vez y la puerta debe cerrarse detrás de ellos. "
            "Dos personas deben mantener contacto visual continuo con SCP-173 hasta que todo el personal haya desocupado el contenedor.\n\n"
            "Descripción:\n"
            "Trasladado al Sitio-19 en 1993. Su origen es aún desconocido. Está construido de hormigón y barras de refuerzo con rastros "
            "de pintura en aerosol. SCP-173 está animado y es extremadamente hostil. El objeto no puede moverse mientras esté en una "
            "línea de visión directa. El personal asignado debe advertirse mutuamente antes de parpadear. En caso de ataque, el personal "
            "reporta sonidos de raspado de piedra procedentes del interior del contenedor."
        ),
    },
    {
        "id": "SCP-096",
        "story_id": "SCP-096",
        "title": "SCP-096 - El Chico Tímido",
        "item_number": "SCP-096",
        "object_class": "Euclid",
        "author": "Dr Dan",
        "rating": 4800,
        "url": "https://scp-wiki.wikidot.com/scp-096",
        "source_license": DEFAULT_LICENSE,
        "containment_procedures": (
            "SCP-096 debe mantenerse en su celda de contención, un cubo de acero hermético de 5 m x 5 m x 5 m, en todo momento. "
            "Se realizarán verificaciones semanales para detectar grietas o agujeros. No debe haber cámaras de vigilancia ni "
            "instrumentos ópticos de ningún tipo dentro de la celda de SCP-096. El personal de seguridad utilizará sensores de presión "
            "y detectores láser instalados para asegurar la presencia de SCP-096 dentro de la celda."
        ),
        "description": (
            "SCP-096 es una criatura humanoide que mide aproximadamente 2.38 metros de altura. El sujeto muestra muy poca masa muscular, "
            "con análisis preliminares de masa corporal sugiriendo desnutrición leve. Los brazos están desproporcionados con el resto "
            "del cuerpo, con una longitud aproximada de 1.5 metros cada uno. La piel carece en su mayoría de pigmentación, sin signos "
            "de vello corporal. La mandíbula de SCP-096 puede abrirse cuatro veces más que la de un humano promedio.\n\n"
            "SCP-096 es normalmente extremadamente dócil. Sin embargo, cuando alguien ve el rostro de SCP-096, ya sea directamente, "
            "a través de una grabación de video o incluso una fotografía, entrará en una fase de angustia emocional severa. "
            "Aproximadamente uno a dos minutos después de la primera visualización, SCP-096 comenzará a correr hacia la persona que vio "
            "su rostro (denominada SCP-096-1) a velocidades registradas de hasta cientos de kilómetros por hora. Ninguna barrera conocida "
            "puede detener su avance."
        ),
        "content": (
            "Ítem #: SCP-096\n"
            "Clase de Objeto: Euclid\n\n"
            "Procedimientos Especiales de Contención:\n"
            "SCP-096 debe mantenerse en su celda, un cubo de acero hermético de 5 m x 5 m x 5 m, en todo momento. Queda terminantemente "
            "prohibida cualquier cámara de vigilancia o dispositivo óptico dentro del recinto.\n\n"
            "Descripción:\n"
            "SCP-096 es un humanoide de 2.38 metros de altura, con piel pálida desprovista de vello y extremidades desproporcionadamente largas. "
            "Permanece dócil hasta que un individuo observa su rostro, ya sea en persona o mediante fotografías. En ese instante, SCP-096 "
            "emite alaridos ensordecedores y persigue a la persona sin importar la distancia física, atravesando cualquier estructura "
            "hasta eliminar por completo al objetivo."
        ),
    },
    {
        "id": "SCP-049",
        "story_id": "SCP-049",
        "title": "SCP-049 - El Doctor de la Plaga",
        "item_number": "SCP-049",
        "object_class": "Euclid",
        "author": "Gabriel Jade",
        "rating": 4500,
        "url": "https://scp-wiki.wikidot.com/scp-049",
        "source_license": DEFAULT_LICENSE,
        "containment_procedures": (
            "SCP-049 está contenido dentro de una celda de contención estándar para humanoides asegurada en el Sector-02 del Sitio-19. "
            "SCP-049 debe ser sedado antes de cualquier intento de transporte. Durante el transporte, SCP-049 debe asegurarse dentro de "
            "un arnés de contención humanoide de Clase III y ser monitoreado por al menos dos guardias armados."
        ),
        "description": (
            "SCP-049 es una entidad humanoide de aproximadamente 1.9 metros de estatura, que tiene la apariencia de un médico de la peste medieval. "
            "Aunque SCP-049 parece llevar las túnicas gruesas y la máscara de cerámica características de esa profesión, las prendas parecen "
            "haber crecido a partir del cuerpo de SCP-049 a lo largo del tiempo, y ahora son casi indistinguibles de cualquier forma que haya "
            "debajo de ellas. Los rayos X indican que SCP-049 tiene una estructura esquelética humanoide debajo de su capa exterior.\n\n"
            "SCP-049 es capaz de hablar en varios idiomas, prefiriendo el inglés o el francés medieval. Aunque SCP-049 es generalmente "
            "cordial y cooperativo con el personal de la Fundación, puede volverse muy agitado si siente la presencia de lo que llama "
            "'La Gran Pestilencia'. El contacto con la piel de SCP-049 es invariablemente letal para los seres humanos, a los cuales intenta "
            "posteriormente 'curar' mediante una compleja cirugía rudimentaria que los reanima como entidades zombificadas."
        ),
        "content": (
            "Ítem #: SCP-049\n"
            "Clase de Objeto: Euclid\n\n"
            "Procedimientos Especiales de Contención:\n"
            "SCP-049 está contenido en una celda para humanoides en el Sitio-19. Cualquier interacción requiere escolta armada y trajes de protección.\n\n"
            "Descripción:\n"
            "SCP-049 aparenta ser un médico de la peste negra del siglo XV. Sus vestiduras y máscara de pico son parte integral de su tejido biológico. "
            "Su tacto directo detiene instantáneamente todas las funciones biológicas humanas. Tras matar a una víctima, realiza cirugías arcanas con las "
            "herramientas de su maletín de cuero para resucitarlas como marionetas biológicas desprovistas de consciencia, afirmando estar curándolas "
            "de la Pestilencia."
        ),
    },
    {
        "id": "SCP-682",
        "story_id": "SCP-682",
        "title": "SCP-682 - Reptil Difícil de Destruir",
        "item_number": "SCP-682",
        "object_class": "Keter",
        "author": "Dr Gears",
        "rating": 4900,
        "url": "https://scp-wiki.wikidot.com/scp-682",
        "source_license": DEFAULT_LICENSE,
        "containment_procedures": (
            "SCP-682 debe ser destruido tan pronto como sea posible. Actualmente no hay medios disponibles capaces de destruir a SCP-682, "
            "sólo capaces de causarle daño físico masivo. SCP-682 debe mantenerse en una cámara de 5 m x 5 m x 5 m revestida con placas de "
            "acero resistentes a los ácidos reforzadas. La cámara de contención debe llenarse con ácido clorhídrico hasta que SCP-682 quede "
            "completamente sumergido e incapacitado."
        ),
        "description": (
            "SCP-682 es una criatura grande, de aspecto vagamente reptiliano, de origen desconocido. Parece ser extremadamente inteligente, "
            "y fue observado entablando una comunicación compleja con SCP-079 durante su breve tiempo de exposición. SCP-682 parece manifestar "
            "un odio inextinguible hacia toda forma de vida, lo cual ha expresado en múltiples entrevistas durante su contención.\n\n"
            "Siempre se ha observado que SCP-682 tiene una fuerza, velocidad y reflejos extremadamente altos. Su cuerpo físico crece y cambia "
            "muy rápidamente, aumentando o disminuyendo de tamaño a medida que consume o arroja materia. SCP-682 obtiene energía de todo lo "
            "que ingiere, orgánico o inorgánico. Su capacidad de regeneración y adaptación a cualquier forma de daño físico o químico es casi "
            "ilimitada."
        ),
        "content": (
            "Ítem #: SCP-682\n"
            "Clase de Objeto: Keter\n\n"
            "Procedimientos Especiales de Contención:\n"
            "SCP-682 debe permanecer sumergido permanentemente en una cuba de 5 m x 5 m x 5 m de ácido clorhídrico concentrado en el Sitio-19.\n\n"
            "Descripción:\n"
            "SCP-682 es un colosal reptil con adaptación biológica instantánea y odio absoluto hacia toda forma de vida. Su tejido celular puede "
            "regenerarse a partir de un remanente del 1% de su masa original, desarrollando caparazones blindados, glándulas de fuego o defensas "
            "radiactivas frente a cualquier intento de terminación."
        ),
    },
    {
        "id": "SCP-3008",
        "story_id": "SCP-3008",
        "title": "SCP-3008 - Un IKEA Totalmente Normal",
        "item_number": "SCP-3008",
        "object_class": "Euclid",
        "author": "Mortos",
        "rating": 4100,
        "url": "https://scp-wiki.wikidot.com/scp-3008",
        "source_license": DEFAULT_LICENSE,
        "containment_procedures": (
            "El edificio que contiene a SCP-3008 ha sido adquirido por la Fundación y convertido en el Sitio-118. Todas las entradas públicas "
            "al interior de SCP-3008 están bloqueadas y vigiladas por guardias vestidos de seguridad civil. Cualquier civil que intente entrar "
            "debe ser detenido y administrado amnésicos de Clase A."
        ),
        "description": (
            "SCP-3008 es una tienda minorista que anteriormente pertenecía a la cadena de muebles IKEA. Las personas que ingresan a través de "
            "las puertas principales son transportadas a SCP-3008-1, un espacio extradimensional no euclidiano que se asemeja al interior de una "
            "tienda de muebles que se extiende infinitamente sin límites visibles.\n\n"
            "Dentro de SCP-3008-1 residen colonias de civiles atrapados y entidades humanoides conocidas como SCP-3008-2. Estas entidades visten "
            "el uniforme de los empleados de IKEA, pero carecen de rasgos faciales y presentan proporciones anatómicas distorsionadas. Durante las "
            "horas de 'luces apagadas', SCP-3008-2 se vuelven violentamente hostiles, repitiendo la frase: 'La tienda está cerrada, por favor "
            "salga del edificio'."
        ),
        "content": (
            "Ítem #: SCP-3008\n"
            "Clase de Objeto: Euclid\n\n"
            "Procedimientos Especiales de Contención:\n"
            "El exterior de la tienda permanece clausurado y catalogado como Sitio-118 de la Fundación.\n\n"
            "Descripción:\n"
            "SCP-3008 es una sucursal de IKEA cuyo interior conforma un laberinto infinito no euclidiano. Los supervivientes atrapados construyen "
            "fortalezas con camas y armarios para defenderse durante la noche de los Empleados (SCP-3008-2), humanoides sin rostro de 2 metros de altura "
            "que cazan a los clientes cuando las luces se apagan."
        ),
    },
]

__all__ = ["CANONICAL_SCP_STORIES"]
