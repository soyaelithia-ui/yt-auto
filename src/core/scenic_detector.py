"""
src/core/scenic_detector.py - Semantic Scenic Loop and Subtitle Animation Style Detector.

Ports and expands the procedural theme classifier from Temp-/geminiService.ts:
- Maps topic text and channel niche into 7 procedural WebGL/Three.js environments.
- Automatically selects the optimal subtitle retention animation style.
"""
from __future__ import annotations

import re
from typing import Dict, List, Literal, Tuple

ScenicLoopType = Literal[
    "scp_facility",
    "jurassic_dino",
    "eerie_forest",
    "rose_garden",
    "cosmic_nebula",
    "cyber_matrix",
    "deep_ocean",
]

SubtitleAnimationStyle = Literal[
    "tiktok_bounce",
    "vertical_lift",
    "climbing_scroll",
    "karaoke_glow",
    "cinematic_fade",
    "bold_banner",
]

SCENIC_THEMES: Dict[ScenicLoopType, Dict[str, object]] = {
    "scp_facility": {
        "label": "Instalación SCP-2000 Subterránea (Yellowstone)",
        "keywords": [
            "scp", "fundacion", "fundación", "foundation", "thaumiel", "keter",
            "containment", "contención", "contencion", "anomalia", "anomalía",
            "deus ex", "yellowstone", "bunker", "búnker", "laboratorio", "scranton",
        ],
        "default_atmosphere": "dark_cinematic",
    },
    "jurassic_dino": {
        "label": "Bosque Jurásico & Fósiles",
        "keywords": [
            "dino", "t-rex", "tyrannosaurus", "jurassic", "jurásico", "jurasico",
            "prehistori", "prehistórico", "fosil", "fósil", "cretac", "cretácico",
            "reptil", "monstruo", "dinosaurio",
        ],
        "default_atmosphere": "dark_cinematic",
    },
    "eerie_forest": {
        "label": "Bosque Tétrico en Niebla (Horror)",
        "keywords": [
            "bosque", "tetrico", "tétrico", "miedo", "terror", "fantasma", "misterio",
            "dark", "horror", "gothic", "gótico", "pesadilla", "creepy", "sombra",
        ],
        "default_atmosphere": "gothic_horror",
    },
    "rose_garden": {
        "label": "Jardín de Rosas & Pétalos Flotantes",
        "keywords": [
            "rosa", "flor", "amor", "romance", "poesia", "poesía", "pasion", "pasión",
            "belleza", "paz", "meditac", "meditación", "drama", "aita",
        ],
        "default_atmosphere": "dreamy_soft",
    },
    "cosmic_nebula": {
        "label": "Nebulosa Cósmica & Vórtice Cuántico",
        "keywords": [
            "espacio", "universo", "galaxia", "estrella", "cosmos", "cósmico", "cosmico",
            "agujero", "cuantico", "cuántico", "astronauta", "planeta", "astronom",
        ],
        "default_atmosphere": "dark_cinematic",
    },
    "cyber_matrix": {
        "label": "Cyberpunk Matrix & Circuito Cuántico",
        "keywords": [
            "ia", "ai", "tech", "tecnología", "tecnologia", "codigo", "código",
            "programac", "programación", "futuro", "robot", "cyber", "software",
            "crypto", "algoritmo", "developer", "red neuronal",
        ],
        "default_atmosphere": "retro_synth",
    },
    "deep_ocean": {
        "label": "Océano Abisal & Bioluminiscencia",
        "keywords": [
            "oceano", "océano", "mar", "agua", "profund", "abismo", "pez",
            "ballena", "submarino", "tiburon", "tiburón", "kraken", "marino", "marina",
            "acuatico", "acuático", "oceanico", "oceánico",
        ],
        "default_atmosphere": "dark_cinematic",
    },
}

GENERIC_MOOD_WORDS = {"misterio", "miedo", "terror", "dark", "sombra", "drama"}


def detect_scenic_loop(topic: str, niche: str = "") -> ScenicLoopType:
    """
    Analyzes topic and niche to determine the canonical procedural 3D scenic loop.
    Defaults to 'eerie_forest' if no specific keywords match.
    """
    text = f"{topic} {niche}".lower()

    def _matches_kw(kw: str, target_text: str) -> bool:
        if len(kw) <= 3:
            return bool(re.search(rf"\b{re.escape(kw)}\b", target_text))
        return kw in target_text

    # Priority 1: Check SCP first (due to specialized containment assets)
    for kw in SCENIC_THEMES["scp_facility"]["keywords"]:  # type: ignore
        if _matches_kw(kw, text):
            return "scp_facility"

    # Priority 2: Check other themes based on weighted keyword match density
    scores: Dict[ScenicLoopType, int] = {}
    for loop_type, data in SCENIC_THEMES.items():
        if loop_type == "scp_facility":
            continue
        score = 0
        for kw in data["keywords"]:  # type: ignore
            if _matches_kw(kw, text):
                weight = 1 if kw in GENERIC_MOOD_WORDS else 2
                score += weight
        if score > 0:
            scores[loop_type] = score

    if scores:
        best_loop = max(scores, key=scores.get)  # type: ignore
        return best_loop

    return "eerie_forest"


def detect_subtitle_style(format_mode: str, niche: str = "") -> SubtitleAnimationStyle:
    """
    Selects the optimal subtitle retention animation style based on format and niche.
    """
    fmt_lower = format_mode.lower()
    niche_lower = niche.lower()

    if fmt_lower in ("short", "shorts", "9:16", "vertical"):
        if "scp" in niche_lower or "mystery" in niche_lower:
            return "vertical_lift"
        return "tiktok_bounce"

    if "tech" in niche_lower or "cyber" in niche_lower:
        return "karaoke_glow"

    return "cinematic_fade"
