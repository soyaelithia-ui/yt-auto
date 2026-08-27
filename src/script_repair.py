"""Script repair pipeline for editorial-barrier violations.

Layer 1: deterministic sentence removal (src.sanitizer.repair_forbidden_editorial).
Layer 2: AI rewrite through the existing Gemini REST chain, fail-closed —
if the provider is unavailable or returns an unsafe result, the caller must
treat the script as irreparable and fail BEFORE spending images/TTS/render.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("script_repair")

_REWRITE_INSTRUCTIONS = (
    "Reescribe el siguiente relato en español neutro respetando su trama, "
    "tono y extensión aproximada. ELIMINA cualquier saludo, despedida, "
    "llamado a la acción o mención meta al canal/vídeo. Devuelve SOLO el "
    "relato reescrito, sin títulos, sin comentarios y sin comillas.\n\nRELATO:\n"
)


def ai_rewrite_without_violations(script: str, violation: str) -> Optional[str]:
    """Attempt a compliant AI rewrite; return None when unavailable/unsafe."""
    if not script or not violation:
        return None
    try:
        from src.llm import _curate_with_gemini
        from src.sanitizer import check_forbidden_editorial_elements

        rewritten = _curate_with_gemini(_REWRITE_INSTRUCTIONS + script)
    except Exception as exc:  # noqa: BLE001 - fail-closed by contract
        logger.warning("AI rewrite unavailable (%s); treating as irreparable", exc)
        return None
    if not rewritten:
        return None
    rewritten = rewritten.strip().strip('"')
    if len(rewritten) < max(200, int(len(script) * 0.5)):
        logger.warning("AI rewrite too short (%d chars); discarded", len(rewritten))
        return None
    if check_forbidden_editorial_elements(rewritten):
        logger.warning("AI rewrite still violates barrier (%s); discarded", violation)
        return None
    return rewritten
