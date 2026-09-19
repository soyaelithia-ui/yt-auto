"""src/scrapers/scp/parser.py - HTML cleaners and regular expression field extractors for SCP files."""

from __future__ import annotations

import logging
import re
import urllib.parse
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

from src.scrapers.scp.constants import DEFAULT_LICENSE, SCP_WIKI_BASE_URL

logger = logging.getLogger("scraper_scp")


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
        containment = (
            f"El objeto {item_number} debe mantenerse bajo estricta contención de nivel estándar en las instalaciones "
            "de la Fundación."
        )

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

    content_match = re.search(
        r'<div\s+id=["\']page-content["\'][^>]*>(.*?)</div>\s*<div\s+id=["\']page-info-break',
        html_text,
        re.DOTALL,
    )
    content_html = content_match.group(1) if content_match else html_text

    parser = _WikidotHTMLCleaner()
    try:
        parser.feed(content_html)
        clean_text = parser.get_clean_text()
    except Exception as e:
        logger.warning("Error parsing SCP HTML with HTMLParser: %s", e)
        clean_text = re.sub(r"<[^>]+>", " ", content_html)

    if not clean_text or len(clean_text) < 50:
        return None

    url_slug = urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1] if url else ""
    item_number = url_slug.upper() if url_slug.startswith("scp-") else ""

    return parse_scp_text(
        raw_text=clean_text,
        item_number=item_number,
        url=url,
        author=author,
        rating=rating,
    )


__all__ = [
    "_WikidotHTMLCleaner",
    "parse_scp_text",
    "parse_scp_wikidot_html",
]
