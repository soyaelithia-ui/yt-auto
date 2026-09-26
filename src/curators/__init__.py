"""
Narrative Curators Strategy Package.
"""

from __future__ import annotations

from src.curators.base import (
    INarrativeCurator,
    NarrativeDirector,
    get_narrative_director,
)
from src.curators.drama import DramaCurator
from src.curators.horror import HorrorCurator

__all__ = [
    "DramaCurator",
    "HorrorCurator",
    "INarrativeCurator",
    "NarrativeDirector",
    "get_narrative_director",
]
