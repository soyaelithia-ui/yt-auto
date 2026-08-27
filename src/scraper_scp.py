"""SCP Foundation Wiki & Crom API Scraper.

Scrapes top-rated SCP anomaly files from the SCP Foundation wiki and Crom API,
extracting Item Number, Object Class, Special Containment Procedures, and Description,
with full CC BY-SA 3.0 attribution metadata.
"""

from __future__ import annotations

import html
import json
import logging
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.log import get_logger

logger = get_logger("scraper_scp")

DEFAULT_LICENSE = "CC BY-SA 3.0"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) YoutubeAutomation/1.0 (SCP Scraper; CC BY-SA 3.0 Compliant)"
CROM_GRAPHQL_ENDPOINT = "https://api.crom.avn.sh/graphql"
SCP_WIKI_BASE_URL = "https://scp-wiki.wikidot.com"
SCP_WIKI_ES_BASE_URL = "http://lafundacionscp.wikidot.com"

# Built-in canonical fallback SCP database (Offline & fail-safe resilience)
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


class _WikidotHTMLCleaner(HTMLParser):
    """HTML Parser that strips navigation, scripts, ratings and extracts article text."""

    def __init__(self) -> None:
        super().__init__()
        self.text_parts: List[str] = []
        self.skip_stack: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag_lower = tag.lower()
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        cls = attrs_dict.get("class", "")
        id_val = attrs_dict.get("id", "")
        skip_classes = (
            "page-rate-widget-box",
            "creditRate",
            "license-box",
            "footer",
            "rate-points",
            "action-area",
            "page-tags",
            "heritage-rating-module",
            "scp-image-block",
        )
        should_skip = (
            tag_lower in ("script", "style", "head", "noscript", "iframe")
            or any(bad in cls for bad in skip_classes)
            or any(bad in id_val for bad in skip_classes)
        )
        if should_skip or self.skip_stack:
            self.skip_stack.append(tag_lower)
            return

        if tag_lower in ("p", "br", "div", "h1", "h2", "h3", "h4", "li", "tr"):
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if self.skip_stack:
            self.skip_stack.pop()
            return
        if tag_lower in ("p", "br", "div", "h1", "h2", "h3", "h4", "li", "tr"):
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_stack and data:
            self.text_parts.append(data)

    def get_clean_text(self) -> str:
        raw = "".join(self.text_parts)
        lines = [line.strip() for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


def parse_scp_text(
    raw_text: str,
    item_number: str = "",
    url: str = "",
    author: str = "SCP Community",
    rating: int = 0,
) -> Dict[str, Any]:
    """Extract SCP fields (Item #, Object Class, Containment Procedures, Description) from text."""
    clean_text = raw_text.strip()
    
    # 1. Item Number
    if not item_number:
        item_match = re.search(
            r"(?i)(?:item\s*#|ítem\s*#|item\s*number|art[ií]culo\s*#)[\s:]*([A-Za-z0-9\-_]+)",
            clean_text,
        )
        if item_match:
            item_number = item_match.group(1).upper()
        else:
            scp_match = re.search(r"(?i)\b(SCP-[0-9]{3,5}[A-Za-z0-9\-]*)\b", clean_text)
            item_number = scp_match.group(1).upper() if scp_match else "SCP-ANOMALY"

    # 2. Object Class
    class_match = re.search(
        r"(?i)(?:object\s*class|clase\s*de\s*objeto|clasificaci[oó]n)[\s:]*([A-Za-z]+)",
        clean_text,
    )
    object_class = class_match.group(1).capitalize() if class_match else "Euclid"

    # 3. Containment Procedures
    containment = ""
    cont_match = re.search(
        r"(?i)(?:special\s*containment\s*procedures|procedimientos\s*especiales\s*de\s*contenci[oó]n)[\s:]*(.*?)(?=\n\s*(?:description|descripci[oó]n)|$)",
        clean_text,
        re.DOTALL,
    )
    if cont_match:
        containment = cont_match.group(1).strip()
    else:
        # Fallback snippet
        containment = f"El objeto {item_number} debe mantenerse bajo estricta contención de nivel estándar en las instalaciones de la Fundación."

    # 4. Description
    description = ""
    desc_match = re.search(
        r"(?i)(?:description|descripci[oó]n)[\s:]*(.*?)(?=\n\s*(?:addendum|anexo|incident|incidente|document|documento|footnotes|notas)|$)",
        clean_text,
        re.DOTALL,
    )
    if desc_match:
        description = desc_match.group(1).strip()
    else:
        description = clean_text[:1500]

    # Clean multi-newlines and leading bold/markdown symbols
    containment = re.sub(r"^[*\-_:\s]+", "", containment)
    description = re.sub(r"^[*\-_:\s]+", "", description)

    title = f"{item_number} - Clase {object_class}"
    if not url:
        url = f"{SCP_WIKI_BASE_URL}/{item_number.lower()}"

    formatted_content = (
        f"Ítem #: {item_number}\n"
        f"Clase de Objeto: {object_class}\n\n"
        f"Procedimientos Especiales de Contención:\n{containment}\n\n"
        f"Descripción:\n{description}"
    )

    return {
        "id": item_number,
        "story_id": item_number,
        "title": title,
        "content": formatted_content,
        "url": url,
        "author": author,
        "score": int(rating),
        "source_license": DEFAULT_LICENSE,
        "item_number": item_number,
        "object_class": object_class,
        "containment_procedures": containment,
        "description": description,
    }


def parse_scp_wikidot_html(
    html_text: str,
    url: str,
    author: str = "SCP Community",
    rating: int = 0,
) -> Optional[Dict[str, Any]]:
    """Parse HTML from an SCP Foundation Wikidot page into a structured SCP story."""
    if not html_text:
        return None

    # Try to extract the page-content container
    content_match = re.search(r'<div\s+id=["\']page-content["\'][^>]*>(.*?)</div>\s*<div\s+id=["\']page-info-break', html_text, re.DOTALL)
    content_html = content_match.group(1) if content_match else html_text

    parser = _WikidotHTMLCleaner()
    try:
        parser.feed(content_html)
        clean_text = parser.get_clean_text()
    except Exception as e:
        logger.warning(f"Error parsing SCP HTML with HTMLParser: {e}")
        clean_text = re.sub(r"<[^>]+>", " ", content_html)

    if not clean_text or len(clean_text) < 50:
        return None

    # Derive item number from URL or text
    import urllib.parse
    url_slug = urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1] if url else ""
    item_number = url_slug.upper() if url_slug.startswith("scp-") else ""

    return parse_scp_text(
        raw_text=clean_text,
        item_number=item_number,
        url=url,
        author=author,
        rating=rating,
    )


def fetch_scp_by_item(item_number: str) -> Optional[Dict[str, Any]]:
    """Fetch and parse a specific SCP article by item number (e.g. 'SCP-096' or '096')."""
    item_clean = item_number.strip().upper()
    if not item_clean.startswith("SCP-"):
        item_clean = f"SCP-{item_clean}"

    # Check canonical fallback first
    for canon in CANONICAL_SCP_STORIES:
        if canon["item_number"].upper() == item_clean:
            return dict(canon)

    import urllib.parse
    url = f"{SCP_WIKI_BASE_URL}/{urllib.parse.quote(item_clean.lower())}"
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            parsed = parse_scp_wikidot_html(resp.text, url=url, rating=100)
            if parsed:
                return parsed
    except Exception as e:
        logger.warning(f"Failed to fetch {item_clean} from Wikidot: {e}")

    # Fallback to first canonical story if not found
    return None


def fetch_top_scp_from_crom(limit: int = 20, min_rating: int = 100) -> List[Dict[str, Any]]:
    """Query Crom API GraphQL endpoint for top-rated SCP articles."""
    query = """
    query GetTopSCPs($limit: Int!, $minRating: Int!) {
      articles(
        filter: {
          wikidotId: 1
          tags: ["scp"]
          rating: { gte: $minRating }
        }
        sort: { rating: DESC }
        first: $limit
      ) {
        edges {
          node {
            url
            wikidotInfo {
              title
              rating
              createdBy {
                name
              }
            }
          }
        }
      }
    }
    """
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "variables": {"limit": limit, "minRating": min_rating},
    }

    try:
        resp = requests.post(CROM_GRAPHQL_ENDPOINT, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            articles = []
            edges = data.get("data", {}).get("articles", {}).get("edges", [])
            for edge in edges:
                node = edge.get("node", {})
                url = node.get("url", "")
                wikidot_info = node.get("wikidotInfo", {})
                title = wikidot_info.get("title", "")
                rating = wikidot_info.get("rating", 0)
                author = wikidot_info.get("createdBy", {}).get("name", "SCP Community")

                if url:
                    # Fetch and parse article body
                    try:
                        page_resp = requests.get(url, headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=8)
                        if page_resp.status_code == 200:
                            parsed = parse_scp_wikidot_html(page_resp.text, url=url, author=author, rating=rating)
                            if parsed:
                                articles.append(parsed)
                    except Exception as err:
                        logger.warning(f"Failed to fetch article body from {url}: {err}")

            if articles:
                logger.info(f"Crom API returned {len(articles)} top SCP articles")
                return articles
    except Exception as e:
        logger.warning(f"Crom API query failed: {e}")

    return []


def fetch_top_scp_articles(
    limit: int = 20,
    min_rating: int = 50,
    tag: str = "scp",
) -> List[Dict[str, Any]]:
    """Fetch top-rated SCP articles with multi-tier fallback (Crom -> Wikidot -> Canonical)."""
    # 1. Attempt Crom GraphQL API
    articles = fetch_top_scp_from_crom(limit=limit, min_rating=min_rating)
    if articles:
        return articles[:limit]

    # 2. Attempt fetching individual high-priority items directly
    common_items = ["SCP-173", "SCP-096", "SCP-049", "SCP-682", "SCP-3008", "SCP-087", "SCP-106", "SCP-999"]
    fetched_direct: List[Dict[str, Any]] = []
    for item in common_items[:limit]:
        art = fetch_scp_by_item(item)
        if art:
            fetched_direct.append(art)
        if len(fetched_direct) >= limit:
            break

    if fetched_direct:
        logger.info(f"Direct SCP fetch returned {len(fetched_direct)} articles")
        return fetched_direct

    # 3. Fallback to canonical built-in database
    logger.info("Using canonical built-in SCP dataset as fail-safe fallback")
    return [dict(s) for s in CANONICAL_SCP_STORIES[:limit]]


def scrape_and_enqueue_scp(
    limit: int = 10,
    db_path: Optional[str] = None,
    lane_id: str = "moku-scp-shorts",
    channel: str = "moku",
) -> int:
    """Scrape SCP articles and enqueue them with CC BY-SA 3.0 license attribution."""
    from src.db import enqueue_story, is_story_processed, is_story_duplicate
    from src.config import DEFAULT_DB_PATH

    path = db_path or DEFAULT_DB_PATH
    articles = fetch_top_scp_articles(limit=limit)
    enqueued = 0

    for art in articles:
        story_id = art["id"]
        title = art["title"]
        content = art["content"]
        url = art["url"]
        rating = int(art.get("score", 0) or 0)
        license_meta = art.get("source_license", DEFAULT_LICENSE)

        if is_story_processed(story_id, db_path=path) or is_story_duplicate(channel, title, content, db_path=path):
            continue

        ok = enqueue_story(
            story_id=story_id,
            title=title,
            content=content,
            url=url,
            channel=channel,
            score=rating,
            lane_id=lane_id,
            source_license=license_meta,
            db_path=path,
        )
        if ok:
            enqueued += 1

    logger.info(f"Enqueued {enqueued} SCP stories into queue for lane [{lane_id}]")
    return enqueued
