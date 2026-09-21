"""
src/templates/loader.py - Structured template loader with in-memory caching.
"""
from __future__ import annotations

import functools
import json
from typing import Any, Dict

from src.config import BASE_DIR

TEMPLATES_DIR = BASE_DIR / "config" / "templates"


@functools.lru_cache(maxsize=16)
def load_template_json(filename: str) -> Dict[str, Any]:
    """Load and cache structured JSON template from config/templates/."""
    # Prevent path traversal attacks
    resolved_dir = TEMPLATES_DIR.resolve()
    file_path = (TEMPLATES_DIR / filename).resolve()
    try:
        file_path.relative_to(resolved_dir)
    except ValueError:
        raise ValueError(f"Security: attempted path traversal with '{filename}'.")

    if not file_path.is_file():
        raise FileNotFoundError(f"Template file not found at {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Template file '{filename}' contains invalid JSON: {exc}") from exc


def clear_template_cache() -> None:
    """Clear in-memory LRU template cache."""
    load_template_json.cache_clear()


def render_paragraphs(paragraphs: Any, subs: Dict[str, Any]) -> str:
    """Render a list of paragraph templates by applying string substitution."""
    if not paragraphs:
        return ""
    rendered = []
    for p in paragraphs:
        if p is None:
            continue
        rendered_p = str(p)
        for k, v in subs.items():
            placeholder = f"{{{k}}}"
            if placeholder in rendered_p:
                rendered_p = rendered_p.replace(placeholder, str(v))
        rendered.append(rendered_p.strip())
    return "\n\n".join(rendered)
