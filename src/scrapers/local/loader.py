"""src/scrapers/local/loader.py - Local canonical and fallback story workset loader."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.scrapers.common import _to_int

logger = logging.getLogger("scraper")

PRESET_CANONICAL_STORIES: List[Dict[str, Any]] = [
    {
        "id": "CANONICAL-TERROR-001",
        "title": "Las escaleras ocultas en la estación abandonada",
        "content": (
            "Trabajé durante tres años como inspector nocturno en el sistema de túneles del metro subterráneo de la ciudad. "
            "Mi turno comenzaba a medianoche, cuando el silencio abrumador se apoderaba por completo de las vías subterráneas. "
            "Una madrugada helada de octubre, mientras revisaba el tramo entre dos estaciones antiguas clausuradas en los años setenta, "
            "noté un pasadizo sin marcar en los planos oficiales. Al atravesar el umbral de ladrillo, descubrí una escalera de concreto "
            "húmedo que descendía en espiral hacia las profundidades desconocidas. Llevado por la curiosidad profesional, bajé varios niveles "
            "sintiendo cómo la temperatura caía drásticamente y el aire se volvía pesado y enrarecido. Al llegar al final de la escalera, "
            "las luces de mi linterna iluminaron una sala circular con marcas alucinantes y extrañas esculpidas en las paredes de piedra. En el centro "
            "exacto de la estancia había una puerta metálica pesada con una pequeña ventanilla de observación sellada desde el exterior. "
            "Cuando acerqué la luz a la mirilla, escuché claramente un murmullo rasposo y helado que pronunció mi nombre completo y la fecha exacta "
            "de esa misma noche. Aterrorizado por el hallazgo, retrocedí corriendo desesperadamente por los escalones mientras sentía pasos pesados "
            "que subían detrás de mí a escasa distancia. Logré salir al túnel principal y sellé la entrada de emergencia, pero desde aquella noche fatal, "
            "cada vez que paso cerca de ese tramo en penumbras, los manómetros de presión fallan y escucho golpeteos rítmicos desquiciantes desde el otro lado de la pared."
        ),
        "url": "https://reddit.com/r/nosleep/comments/canonical001",
    },
    {
        "id": "CANONICAL-AITA-001",
        "title": "¿Soy la mala por negarme a vender mi apartamento heredado para pagar las deudas de mi hermano?",
        "content": (
            "Mi abuela materna me heredó un apartamento pequeño pero bien ubicado cuando falleció hace dos años. "
            "Ella dejó muy claro en su testamento que esa propiedad era para garantizar mi estabilidad económica, "
            "ya que pasé años cuidándola pacientemente durante su larga enfermedad mientras el resto de la familia la ignoraba por completo. Recientemente, "
            "mi hermano mayor acumuló deudas masivas por inversiones arriesgadas en criptomonedas y préstamos personales sin garantía. "
            "Mis padres me llamaron a una reunión familiar sorpresa en su casa para exigirme formalmente que ponga en venta el apartamento de inmediato para "
            "cubrir toda la deuda de mi hermano y evitar que enfrente acciones legales complejas. Les dije firmemente que no lo haría bajo ninguna "
            "circunstancia, ya que ese patrimonio representa el esfuerzo de toda la vida de mi abuela y mi propio futuro financiero. Mis padres se enfurecieron "
            "conmigo y me acusaron de ser una persona fría, egoísta y desalmada por priorizar un inmueble sobre la tranquilidad de mi propio hermano. "
            "Desde ese día, me han excluido de las reuniones familiares, envían mensajes acusatorios constantemente al grupo familiar de chat y varios parientes "
            "me presionan diariamente diciendo que soy la única culpable de la ruina económica de mi hermano. Sin embargo, mi hermano nunca ha mostrado "
            "arrepentimiento por sus decisiones irresponsables ni ha buscado trabajo adicional para resolver sus deudas por cuenta propia. ¿Soy yo la mala por mantener firme mi postura?"
        ),
        "url": "https://reddit.com/r/AmItheAsshole/comments/canonical002",
    },
]


def _parse_frontmatter(lines: List[str]) -> Dict[str, str]:
    """Parse an OPTIONAL leading '---' frontmatter block from pre-cleaned lines."""
    if not lines or lines[0] != "---":
        return {}
    closing = None
    for idx in range(1, len(lines)):
        if lines[idx] == "---":
            closing = idx
            break
    if closing is None:
        return {}
    meta: Dict[str, str] = {}
    for raw_line in lines[1:closing]:
        if ":" not in raw_line:
            continue
        key, _, value = raw_line.partition(":")
        key = key.strip().lower()
        if key:
            meta[key] = value.strip()
    return meta


def _resolve_canonical_dir(path_cls: Any) -> Path:
    base_dir = path_cls(__file__).resolve().parent.parent
    canonical_dir = base_dir / "data" / "worksets" / "canonical"
    if canonical_dir.exists():
        return canonical_dir
    for parent in path_cls(__file__).resolve().parents:
        cand = parent / "data" / "worksets" / "canonical"
        if cand.exists():
            return cand
    return canonical_dir


def _load_canonical_json_files(canonical_dir: Path, min_length: int) -> List[Dict[str, Any]]:
    stories: List[Dict[str, Any]] = []
    for json_file in sorted(canonical_dir.rglob("*.json")):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                post_id = str(item.get("id") or item.get("story_id") or json_file.stem)
                title = str(item.get("title") or "").strip()
                content = str(item.get("content") or item.get("selftext") or "").strip()
                url = str(item.get("url") or f"https://reddit.com/r/canonical/{post_id}")

                if title and content and len(content) >= min_length:
                    stories.append({
                        "id": post_id,
                        "title": title,
                        "content": content,
                        "url": url,
                    })
        except Exception as e:
            logger.warning("Error loading canonical JSON from %s: %s", json_file, e)
    return stories


def _load_canonical_text_files(canonical_dir: Path, min_length: int) -> List[Dict[str, Any]]:
    stories: List[Dict[str, Any]] = []
    for text_file in sorted(list(canonical_dir.rglob("*.txt")) + list(canonical_dir.rglob("*.md"))):
        try:
            text = text_file.read_text(encoding="utf-8").strip()
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if lines:
                meta = _parse_frontmatter(lines)
                if meta:
                    closing = next((i for i in range(1, len(lines)) if lines[i] == "---"), 1)
                    body = lines[closing + 1:]
                    title = body[0] if body else ""
                    content = "\n".join(body[1:]) if len(body) > 1 else title
                else:
                    title = lines[0]
                    content = "\n".join(lines[1:]) if len(lines) > 1 else lines[0]
                post_id = f"FILE-{text_file.stem}"
                url = f"https://reddit.com/r/canonical/{post_id}"
                if title and content and len(content) >= min_length:
                    story: Dict[str, Any] = {
                        "id": post_id,
                        "title": title,
                        "content": content,
                        "url": url,
                    }
                    if meta:
                        story["score"] = _to_int(meta.get("score"), 0)
                        tags_value = str(meta.get("tags") or "")
                        if tags_value:
                            story["tags"] = [
                                t.strip() for t in tags_value.split(",") if t.strip()
                            ]
                    stories.append(story)
        except Exception as e:
            logger.warning("Error loading canonical text file from %s: %s", text_file, e)
    return stories


def _filter_stories_by_niche(
    loaded_stories: List[Dict[str, Any]],
    subreddit: Optional[str],
    min_length: int,
    limit: int,
) -> List[Dict[str, Any]]:
    sub_lower = (subreddit or "").lower()
    is_horror = any(k in sub_lower for k in ("nosleep", "scp", "horror", "creepypasta", "scary", "terror", "moku"))
    is_confession = any(
        k in sub_lower
        for k in ("amitheasshole", "aita", "confession", "relationship", "tifu", "aelithia", "drama", "trueoffmychest", "offmychest")
    )

    def story_matches(story: Dict[str, Any]) -> bool:
        combined = f"{story.get('id', '')} {story.get('title', '')} {story.get('url', '')} {' '.join(story.get('tags', []))}".lower()
        if is_horror:
            forbidden = ("aelithia", "aita", "amitheasshole", "confesion", "confesión", "heredado", "hermano", "hermana", "boda", "infidelidad", "desalojo", "pareja", "esposo", "esposa", "fideicomiso")
            return not any(k in combined for k in forbidden)
        if is_confession:
            forbidden = ("moku", "terror", "horror", "scp", "anomalia", "monstruo", "tunel", "estacion", "creepy", "faro", "sanatorio")
            return not any(k in combined for k in forbidden)
        return True

    matched = [s for s in loaded_stories if story_matches(s)]
    if not matched:
        preset_matched = [
            s for s in PRESET_CANONICAL_STORIES if len(s["content"]) >= min_length and story_matches(s)
        ]
        return preset_matched[:limit] if preset_matched else []
    return matched[:limit]


def _load_canonical_stories(
    subreddit: Optional[str] = None,
    limit: int = 50,
    min_length: int = 10,
) -> List[Dict[str, Any]]:
    """Scan data/worksets/canonical/ for .json, .txt, and .md files, with built-in fallbacks."""
    scraper_mod = sys.modules.get("src.scraper")
    path_cls = getattr(scraper_mod, "Path", Path) if scraper_mod else Path
    canonical_dir = _resolve_canonical_dir(path_cls)

    loaded_stories: List[Dict[str, Any]] = []
    if canonical_dir.exists():
        loaded_stories.extend(_load_canonical_json_files(canonical_dir, min_length))
        loaded_stories.extend(_load_canonical_text_files(canonical_dir, min_length))

    if not loaded_stories:
        logger.warning(
            "No canonical story files found on disk in data/worksets/canonical/. Using preset built-in fallback stories."
        )
        loaded_stories = [s for s in PRESET_CANONICAL_STORIES if len(s["content"]) >= min_length]

    return _filter_stories_by_niche(loaded_stories, subreddit, min_length, limit)


__all__ = [
    "PRESET_CANONICAL_STORIES",
    "_parse_frontmatter",
    "_load_canonical_stories",
]
