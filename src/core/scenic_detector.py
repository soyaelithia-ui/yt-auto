"""
src/core/scenic_detector.py - Intelligent Semantic Scenic Setting & Subtitle Style Classifier.

Dynamically and contextually infers the optimal procedural visual archetype and subtitle animation
from story narrative context, scene keywords, title, and channel niche.
Supports canonical scenic archetypes (names aligned with WGSL catalog; render is FFmpeg on hot path):
- tactical_chamber: Subways, metro tunnels, underground stairs, bunkers, vaults, corridors, containment.
- dark_forest: Haunted woods, misty wilderness, nocturnal roads, secluded cabins.
- arctic_desolation: Snowy blizzards, freezing mountains, ice tundras, SCP-096 expeditions.
- cosmic_singularity: Deep space, black holes, event horizons, alien rifts.
- arcade_vector_flight: Retro 80s vector spaceship shooter, laser beams, asteroid targets.
- parkour_runner: Isometric 3D blocky parkour course, jumping voxel runner.
- cozy_hearth: Warm rainy cabin interior, hearth fireplace embers, domestic confessions.
- synaptic_network: Neural somas, psychological dilemmas, mental introspection.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Literal, Tuple

logger = logging.getLogger(__name__)

# Mirror of native_procedural.VALID_ARCHETYPES — kept local so scenic detection
# (pipeline hot path) never imports wgpu / NativeProceduralEngine.
VALID_ARCHETYPES = {
    "arcade_vector_flight",
    "arctic_desolation",
    "cosmic_singularity",
    "cozy_hearth",
    "dark_forest",
    "maritime_lighthouse",
    "parkour_runner",
    "synaptic_network",
    "tactical_chamber",
}

SubtitleAnimationStyle = Literal[
    "tiktok_bounce",
    "vertical_lift",
    "climbing_scroll",
    "karaoke_glow",
    "cinematic_fade",
    "bold_banner",
]

# Canonical 9 Native Procedural Archetypes
CANONICAL_ARCHETYPES = tuple(sorted(VALID_ARCHETYPES))

ADAPTIVE_ENVIRONMENT_KEYWORDS: Dict[str, List[Tuple[str, int]]] = {
    "maritime_lighthouse": [
        # Lighthouse, sea, ocean, coastal cliffs, storms, maritime mystery (High weight = 5)
        ("faro", 6), ("faro de sindicado", 6), ("faro abandonado", 6), ("farero", 5),
        ("mar", 4), ("oceano", 4), ("océano", 4), ("costa", 4), ("acantilado", 5),
        ("olas", 4), ("playa", 4), ("naufragio", 5), ("muelle", 5), ("puerto", 4),
        ("isla", 4), ("isla desierta", 5), ("pescador", 4), ("barco", 4), ("barco fantasma", 5),
        ("luz del faro", 6), ("maritimo", 4), ("marítimo", 4), ("tormenta en el mar", 5),
    ],
    "tactical_chamber": [
        # Underground, subway, metro, and urban infrastructure (High weight = 5)
        ("estacion", 5), ("estación", 5), ("metro", 5), ("subterraneo", 5), ("subterráneo", 5),
        ("tunel", 5), ("túnel", 5), ("escalera", 5), ("escaleras", 5), ("vias", 4), ("vías", 4),
        ("vagon", 4), ("vagón", 4), ("anden", 4), ("andén", 4), ("pasadizo", 5),
        # Industrial, bunkers, containment labs
        ("bunker", 5), ("búnker", 5), ("laboratorio", 5), ("scranton", 5), ("celda", 4),
        ("pasillo", 4), ("puerta de acero", 5), ("puerta metalica", 5), ("puerta metálica", 5),
        ("compuerta", 5), ("instalacion", 4), ("instalación", 4), ("hormigon", 4), ("hormigón", 4),
        ("concreto", 4), ("contencion", 4), ("contención", 4), ("containment", 4),
        ("experimento", 3), ("bloqueo", 3), ("boveda", 4), ("bóveda", 4), ("camara", 4), ("cámara", 4),
        ("scp-173", 5), ("scp-106", 5), ("scp-049", 5), ("sotano", 4), ("sótano", 4),
    ],
    "dark_forest": [
        # Woods, trees, wilderness, night road
        ("bosque", 5), ("arbol", 4), ("árbol", 4), ("arboles", 4), ("árboles", 4),
        ("selva", 4), ("jungla", 4), ("pantano", 4), ("woods", 4), ("forest", 4),
        ("sendero", 4), ("camino de tierra", 4), ("carretera nocturna", 5), ("cementerio", 4),
        ("tumbas", 4), ("niebla espesa", 4), ("sombras en los arboles", 5), ("ramas", 3),
        ("cabaña en el bosque", 5), ("madera podrida", 4), ("tetrico", 3), ("tétrico", 3),
    ],
    "arctic_desolation": [
        # Polar, snow, mountains, ice blizzard
        ("nieve", 5), ("nevado", 5), ("nevada", 5), ("artico", 5), ("ártico", 5),
        ("glaciar", 5), ("ventisca", 5), ("tundra", 5), ("hielo", 4), ("ice", 4),
        ("polar", 4), ("congelado", 4), ("cordillera", 4), ("montaña nevada", 5),
        ("campo nevado", 5), ("chico timido", 5), ("chico tímido", 5), ("shy guy", 5),
        ("096", 5), ("scp-096", 6),
    ],
    "cosmic_singularity": [
        # Space, black holes, astrophysics, sci-fi void
        ("espacio", 4), ("universo", 4), ("galaxia", 5), ("agujero negro", 5),
        ("singularidad", 5), ("vortice", 4), ("vórtice", 4), ("cosmos", 4),
        ("cosmico", 4), ("cósmico", 4), ("planeta", 4), ("astronauta", 5),
        ("orbita", 4), ("órbita", 4), ("horizonte de sucesos", 5), ("dimension", 4),
        ("dimensión", 4), ("astronomia", 4), ("astronomía", 4), ("interestelar", 5),
    ],
    "arcade_vector_flight": [
        # Retro gaming, spaceships shooting lasers, arcade
        ("arcade", 5), ("videojuego", 5), ("nave espacial disparando", 5), ("laser", 4),
        ("láser", 4), ("vector", 4), ("asteroide", 4), ("disparos", 4), ("retro", 4),
        ("juego de naves", 5), ("triangulo disparando", 5), ("triángulo disparando", 5),
        ("score", 3), ("space shooter", 5),
    ],
    "parkour_runner": [
        # Platformer jumps, blocky obstacles, roblox/minecraft
        ("parkour", 5), ("roblox", 5), ("minecraft", 5), ("saltos", 4),
        ("bloques", 4), ("plataformas", 4), ("carrera de obstaculos", 5),
        ("carrera de obstáculos", 5), ("voxel", 4), ("obstaculo", 4), ("obstáculo", 4),
    ],
    "cozy_hearth": [
        # Domestic interiors, rainy window, fireplace, relationships
        ("chimenea", 5), ("lluvia en la ventana", 5), ("fuego", 3), ("sala", 3),
        ("apartamento", 3), ("casa", 3), ("habitacion", 3), ("habitación", 3),
        ("esposo", 3), ("esposa", 3), ("herencia", 4), ("divorcio", 4),
        ("deuda", 3), ("deudas", 3), ("familia", 3), ("confesion", 4),
        ("confesión", 4), ("aita", 4), ("soy el malo", 4), ("soy la mala", 4),
    ],
    "synaptic_network": [
        # Mind, psychological terror, neurobiology, memories
        ("neuronal", 5), ("sinapsis", 5), ("cerebro", 4), ("mente", 3),
        ("psicologico", 4), ("psicológico", 4), ("recuerdo", 3), ("memoria", 3),
        ("conciencia", 3), ("alucinacion", 4), ("alucinación", 4), ("delirio", 4),
    ],
}


def _matches_kw(kw: str, text: str) -> bool:
    kw_norm = kw.lower().strip()
    if len(kw_norm) <= 3:
        return bool(re.search(rf"\b{re.escape(kw_norm)}\b", text))
    return kw_norm in text


def detect_adaptive_theme(topic: str, script: str = "", niche: str = "") -> str:
    """
    Intelligently determines the best procedural visual setting archetype
    from narrative script context, title, and channel niche.
    """
    topic_clean = str(topic or "").lower()
    script_clean = str(script or "").lower()
    full_text = f"{topic_clean} {script_clean}"
    
    scores: Dict[str, int] = {arch: 0 for arch in CANONICAL_ARCHETYPES}

    # 1. High-priority title matching (x2.5 multiplier for direct title setting markers)
    for arch, kw_list in ADAPTIVE_ENVIRONMENT_KEYWORDS.items():
        for kw, weight in kw_list:
            if _matches_kw(kw, topic_clean):
                scores[arch] += int(weight * 2.5)
            elif _matches_kw(kw, full_text):
                scores[arch] += weight

    best_arch = max(scores, key=scores.get)  # type: ignore
    best_score = scores[best_arch]

    if best_score > 0:
        logger.info("Semantic Scenic Detector selected '%s' (score: %d) for topic '%s'", best_arch, best_score, topic[:50])
        return best_arch

    # 2. Channel & Niche intelligent fallback
    niche_lower = f"{niche} {topic_clean}".lower()
    if any(k in niche_lower for k in ("aita", "drama", "confesion", "confesión", "relacion", "relación", "aelithia")):
        return "cozy_hearth"
    if any(k in niche_lower for k in ("scifi", "espacio", "cosmos", "ciencia ficcion")):
        return "cosmic_singularity"
    if any(k in niche_lower for k in ("scp", "fundacion", "clasificado")):
        return "tactical_chamber"
    if any(k in niche_lower for k in ("moku", "terror", "horror", "creepypasta", "nosleep")):
        return "dark_forest"

    return "dark_forest"


ScenicLoopType = Literal[
    "scp_facility",
    "jurassic_dino",
    "eerie_forest",
    "rose_garden",
    "cosmic_nebula",
    "cyber_matrix",
    "deep_ocean",
]

SCENIC_THEMES: Dict[str, Dict[str, object]] = {
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
            "agujeros negros", "vórtice", "vortice",
        ],
        "default_atmosphere": "dark_cinematic",
    },
    "cyber_matrix": {
        "label": "Cyberpunk Matrix & Circuito Cuántico",
        "keywords": [
            "ia", "ai", "tech", "tecnología", "tecnologia", "codigo", "código",
            "programac", "programación", "futuro", "robot", "cyber", "software",
            "crypto", "algoritmo", "developer", "red neuronal", "redes neuronales",
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


def detect_scenic_loop(topic: str, niche: str = "") -> str:
    """
    Analyzes topic and niche to determine the canonical procedural 3D scenic loop.
    Defaults to 'eerie_forest' if no specific keywords match.
    """
    text = f"{topic} {niche}".lower()

    # Priority 1: Check SCP first (due to specialized containment assets)
    for kw in SCENIC_THEMES["scp_facility"]["keywords"]:  # type: ignore
        if _matches_kw(kw, text):
            return "scp_facility"

    # Priority 2: Check other themes based on weighted keyword match density
    scores: Dict[str, int] = {}
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
        if "scp" in niche_lower or "mystery" in niche_lower or "terror" in niche_lower:
            return "vertical_lift"
        return "tiktok_bounce"

    if "tech" in niche_lower or "cyber" in niche_lower or "scifi" in niche_lower:
        return "karaoke_glow"

    return "cinematic_fade"


STORY_MOTIF_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "carnival": ("caramelo", "caramelos", "dulce", "dulces", "golosina", "golosinas", "feria", "circo", "carnival", "payaso", "ferris"),
    "morgue": ("morgue", "autopsia", "cadaver", "cadáver", "forense", "médico", "medico"),
    "asylum": ("manicomio", "asilo", "psiquiátrico", "psiquiatrico", "sanatorio", "ward"),
    "mar": ("mar", "océano", "oceano", "costa", "playa", "faro", "naufragio", "barco", "pescador", "isla", "olas", "marítimo", "maritimo"),
    "cabin": ("cabaña", "cabana", "casa en el bosque", "caserío", "mansión", "mansion", "ático", "atico"),
    "cemetery": ("cementerio", "tumba", "tumbas", "cripta", "panteón", "panteon", "lápida", "lapida"),
    "dark_forest": ("bosque", "árboles", "arboles", "selva", "jungla", "pantano", "wilderness", "pines"),
    "highway": ("carretera", "autopista", "camino", "ruta", "highway", "headlights"),
    "diner": ("diner", "cafetería", "cafeteria", "restaurante", "bar", "comedor"),
    "subway": ("subway", "metro", "túnel", "tunel", "vías", "vias", "vagón", "vagon", "estación subterránea"),
    "backrooms": ("backrooms", "oficina abandonada", "alfombra amarilla", "fluorescente"),
    "bunker": ("búnker", "bunker", "laboratorio", "contención", "contencion", "scranton", "instalación", "instalacion"),
    "lake": ("lago", "laguna", "estanque", "hielo", "congelado", "inundado", "inundación", "sótano inundado"),
    "space": ("espacio", "universo", "galaxia", "estrella", "planeta", "órbita", "orbita", "nebulosa", "agujero negro", "interestelar"),
    "bakery": ("panadería", "panaderia", "pan", "horno", "repostería", "reposteria"),
    "boda": ("boda", "matrimonio", "casamiento", "novia", "novio", "damas de honor", "recepción", "recepcion"),
    "apartamento": ("apartamento", "herencia", "heredado", "departamento", "propiedad", "casa propia"),
    "deudas": ("deuda", "deudas", "fianza", "préstamo", "prestamo", "bancarrota", "dinero"),
    "hermano": ("hermano", "hermana", "suegra", "cuñado", "cunado", "cuñada", "cunada", "primo", "prima"),
}


def extract_story_motifs(topic: str, script: str = "") -> List[str]:
    """
    Extracts physical narrative motifs from the story title and script content.
    Decouples stories from generic channel labels by identifying specific visual subjects
    (e.g., 'caramelos' -> carnival/candy, 'faro' -> mar/ocean, 'cabana' -> cabin/forest).
    Returns a ranked list of detected motif keywords.
    """
    topic_clean = str(topic or "").lower()
    script_clean = str(script or "").lower()
    full_text = f"{topic_clean} {script_clean}"

    detected_scores: Dict[str, int] = {}

    for motif, keywords in STORY_MOTIF_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if _matches_kw(kw, topic_clean):
                score += 5  # Strong preference for title motifs
            elif _matches_kw(kw, full_text):
                score += 1
        if score > 0:
            detected_scores[motif] = score

    if not detected_scores:
        return []

    # Sort descending by score
    sorted_motifs = sorted(detected_scores.keys(), key=lambda m: detected_scores[m], reverse=True)
    return sorted_motifs

