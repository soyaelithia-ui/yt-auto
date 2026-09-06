"""Shared FFmpeg lavfi gradient palettes for near-zero-RAM loop fallbacks.

Single source for proc_engine + loop_worker category colors.
"""
from __future__ import annotations

from typing import Dict, Tuple

# (c0, c1) hex colors for lavfi gradients=
LAVFI_CATEGORY_PALETTES: Dict[str, Tuple[str, str]] = {
    "drama_aita": ("0x2d3436", "0x636e72"),
    "cosmic_horror": ("0x0c101c", "0x2c1f3d"),
    "scp": ("0x1a252f", "0x34495e"),
    "classified_terminal": ("0x1a252f", "0x34495e"),
    "dark_forest": ("0x0f2417", "0x1e452e"),
    "dark_ambient": ("0x181a1b", "0x2f3542"),
    "monsters": ("0x231515", "0x452222"),
    "space_abyss": ("0x0a0e17", "0x1d273a"),
    "atmospheric_landscape": ("0x181a1b", "0x34495e"),
    "cosmic_singularity": ("0x0c101c", "0x2c1f3d"),
}

DEFAULT_LAVFI_PALETTE: Tuple[str, str] = ("0x181a1b", "0x34495e")


def normalize_palette_key(category: str | None) -> str:
    return (category or "").strip().lower().replace("-", "_").replace(" ", "_")


def resolve_lavfi_palette(category: str | None) -> Tuple[str, str]:
    """Return (c0, c1) for a thematic category."""
    return LAVFI_CATEGORY_PALETTES.get(normalize_palette_key(category), DEFAULT_LAVFI_PALETTE)


__all__ = [
    "DEFAULT_LAVFI_PALETTE",
    "LAVFI_CATEGORY_PALETTES",
    "normalize_palette_key",
    "resolve_lavfi_palette",
]
