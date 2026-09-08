"""Local media asset resolution helpers.

Provides lookup against local template / workset directories and canonical
web-reference caches. AI image generation has been removed from the active
pipeline (LoopVideoEngine renders a continuous atmospheric loop instead), so
this module now exposes the offline-only utility functions.
"""

import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, List

from src.config import BASE_DIR
from src.log import get_logger

logger = get_logger("asset_provider")

TEMPLATES_DIR = Path(BASE_DIR) / "assets" / "templates"
WORKSETS_DIR = Path(BASE_DIR) / "data" / "worksets"


def check_local_templates(
    channel_type: str,
    scene_query: str,
    *,
    match_only: bool = False,
    scene_index: int = 0,
) -> Optional[str]:
    """Tier 1 lookup: local channel templates and workset directories.

    ``match_only`` keeps the function strict so callers can probe before
    falling back; the legacy deterministic generic-pick behavior is preserved
    for callers outside the active loop pipeline.
    """
    norm_channel = channel_type.lower().strip()

    # Map channel_type aliases to template and workset folders
    channel_folder_map = {
        "horror": ["moku", "horror"],
        "moku_terror": ["moku", "moku_terror", "creepypasta", "terror"],
        "aita_drama": ["aelithia", "aita_drama", "aita", "drama"],
        "terror": ["moku", "moku_terror", "creepypasta"],
        "moku": ["moku", "moku_terror", "creepypasta"],
        "aelithia": ["aelithia", "aita_drama", "aita"],
        "soy_el_malo": ["aelithia", "aita_drama", "aita"],
    }

    folders_to_check = channel_folder_map.get(norm_channel, [norm_channel])

    search_dirs: List[Path] = []
    visual_bank_dir = Path(BASE_DIR) / "assets" / "visual_bank"
    for f in folders_to_check:
        search_dirs.append(visual_bank_dir / f / "scenery")
        search_dirs.append(visual_bank_dir / f)
        search_dirs.append(TEMPLATES_DIR / f)
        search_dirs.append(WORKSETS_DIR / f)

    search_dirs.extend([
        WORKSETS_DIR / "generated",
        visual_bank_dir / "moku" / "scenery",
        visual_bank_dir / "aelithia" / "scenery",
        visual_bank_dir,
        TEMPLATES_DIR,
        WORKSETS_DIR,
        Path(BASE_DIR) / "assets",
    ])

    query_words = set(re.findall(r"\w+", scene_query.lower()))
    # Semantic context keyword expansions
    context_map = {
        "escalera": "stairs", "escaleras": "stairs", "descenso": "stairs",
        "camara": "monitors", "camaras": "monitors", "seguridad": "monitors",
        "celda": "cell", "anomalia": "cell", "anomalía": "cell",
        "contencion": "containment", "contención": "containment",
        "pasillo": "corridor", "corredor": "corridor",
        "bosque": "forest", "arboles": "forest", "asilo": "asylum",
        "sotano": "basement", "sótano": "basement",
        "cocina": "kitchen", "banquete": "kitchen", "comida": "kitchen", "disputa": "dispute",
        "sala": "living", "familia": "living", "sofa": "living",
        "auto": "car", "carro": "car", "lluvia": "rainy",
        "juicio": "courtroom", "abogado": "courtroom", "tribunal": "courtroom",
        "cafe": "coffee", "café": "coffee", "calle": "suburban", "vecindario": "suburban",
    }
    expanded_words = set(query_words)
    for w in query_words:
        if w in context_map:
            expanded_words.add(context_map[w])

    for s_dir in search_dirs:
        if not s_dir.exists() or not s_dir.is_dir():
            continue

        # Skip quarantined title cards / non-scenery layers if search walks into them
        _skip_markers = {
            "_quarantine_title_cards", "quarantine_title_cards",
            "title_cards", "prebaked", "ambient_gifs", "overlays",
        }
        _skip_name_tokens = ("bitácora", "bitacora", "advertencia")
        candidates = sorted([
            p for p in s_dir.glob("*")
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".mp4"}
            and p.is_file()
            and not any(m in {part.lower() for part in p.parts} for m in _skip_markers)
            and not any(tok in f"{p.stem.lower()} {p.name.lower()}" for tok in _skip_name_tokens)
        ])

        if not candidates:
            continue

        # Match candidates by word overlap or rotate across all candidates
        scored_cands = []
        for cand in candidates:
            cand_stem = cand.stem.lower().replace("_", " ")
            cand_words = set(re.findall(r"\w+", cand_stem))
            overlap = len(expanded_words.intersection(cand_words))
            scored_cands.append((overlap, cand))

        direct_matches = [c for s, c in scored_cands if s > 0]
        if direct_matches:
            chosen = direct_matches[scene_index % len(direct_matches)]
            logger.info(f"Found contextual local template asset ({chosen.name}) for scene {scene_index}")
            return str(chosen)

        # Diverse candidate rotation across full candidate list for this scene
        chosen = candidates[scene_index % len(candidates)]
        logger.info(f"Using rotated local template asset ({chosen.name}) for scene {scene_index}")
        return str(chosen)

    return None


async def search_reference_image_web(entity_id: str, scene_query: str) -> Optional[str]:
    """Tier 2: find a cached web reference asset (image or video) for the entity.

    Offline-safe: only resolves assets present in the local workset cache.
    """
    norm_entity = (entity_id or scene_query or "video").strip().upper()
    cache_dir = WORKSETS_DIR / "canonical" / norm_entity
    cache_dir.mkdir(parents=True, exist_ok=True)

    cached_assets = sorted([
        p for p in cache_dir.glob("*")
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".mp4", ".webm", ".mov"}
        and p.stat().st_size > 1000
    ])
    if cached_assets:
        logger.info(f"Retrieved cached canonical web asset for {norm_entity}: {cached_assets[0]}")
        return str(cached_assets[0])

    return None


async def generate_ai_image(scene_query: str, channel_type: str, scene_index: int = 0) -> Optional[str]:
    """Local-template fallback for any external caller.

    Loop-mode pipelines no longer invoke AI image generation: scene visuals
    are an atmospheric loop video resolved by ``LoopVideoEngine``. This helper
    remains for non-loop callers that still request an image asset.
    """
    try:
        template_path = check_local_templates(channel_type, scene_query, scene_index=scene_index)
        if template_path and os.path.exists(template_path):
            logger.info(f"Using local template for AI fallback query '{scene_query[:30]}': {template_path}")
            return template_path
    except Exception as e:
        logger.warning(f"AI image generation note: {e}")

    return None
