"""src/scrapers/local - Local story sources and canonical worksets."""

from __future__ import annotations

from src.scrapers.local.loader import (
    PRESET_CANONICAL_STORIES,
    _load_canonical_stories,
    _parse_frontmatter,
)

__all__ = [
    "PRESET_CANONICAL_STORIES",
    "_parse_frontmatter",
    "_load_canonical_stories",
]
