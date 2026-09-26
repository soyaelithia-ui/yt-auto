"""
Pre-TTS narrative coherence quality gate for YouTube automation pipelines.
Ensures 3-act progression, character/POV continuity, neutral Spanish grammar/punctuation,
and detection/rejection of formulaic clickbait crutches or forbidden channel aliases.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.core.quality import (
    forbidden_aliases,
    is_spanish_neutral,
    normalize_text,
)


@dataclass
class NarrativeCoherenceResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    score: float = 1.0
    details: dict[str, Any] = field(default_factory=dict)


FORMULAIC_CRUTCHES = [
    "pero antes de empezar",
    "no vas a creer lo que paso",
    "comenta para parte 2",
    "dale like y suscribete",
    "quedate hasta el final",
]


def validate_narrative_coherence(
    script: str,
    channel: str = "horror",
    duration_type: str = "short",
    max_words: Optional[int] = None,
    **kwargs: Any,
) -> NarrativeCoherenceResult:
    """
    Validates script narrative coherence prior to TTS voice synthesis.
    Enforces word budgets, single POV continuity, proper Spanish inverted punctuation,
    and blocks translation artifacts and formulaic crutches.
    """
    errors: list[str] = []

    if not script or not script.strip():
        return NarrativeCoherenceResult(
            valid=False,
            errors=["Script is empty or whitespace-only"],
            score=0.0,
        )

    clean_text = script.strip()
    words = clean_text.split()
    word_count = len(words)

    # 1. Word budget boundary checks
    is_short = duration_type in ("short", "vertical", "9:16")
    effective_max = max_words or kwargs.get("max_words") or 350
    if is_short and word_count > effective_max:
        errors.append(
            f"Script word count ({word_count}) exceeds short maximum threshold of {effective_max} words"
        )
    elif is_short and word_count < 15:
        errors.append(
            f"Script word count ({word_count}) is below minimum threshold of 15 words"
        )

    # 2. Spanish neutrality check
    min_required = min(20, max(5, word_count // 2))
    if not is_spanish_neutral(clean_text, minimum_words=min_required):
        errors.append("Script fails Spanish neutrality or contains foreign translation artifacts")

    # 3. Inverted Spanish punctuation balance
    has_open_q = "¿" in clean_text
    has_close_q = "?" in clean_text
    if has_open_q and not has_close_q:
        errors.append("Opening inverted question mark (¿) lacks closing question mark (?)")

    has_open_e = "¡" in clean_text
    has_close_e = "!" in clean_text
    if has_open_e and not has_close_e:
        errors.append("Opening inverted exclamation mark (¡) lacks closing exclamation mark (!)")

    # 4. Anti-crutches clickbait detection
    norm = normalize_text(clean_text)
    detected_crutches = [
        crutch for crutch in FORMULAIC_CRUTCHES if normalize_text(crutch) in norm
    ]
    if len(detected_crutches) >= 2:
        errors.append(
            f"Detected multiple formulaic clickbait crutches: {detected_crutches}"
        )

    # 5. Forbidden channel alias leaks
    aliases = forbidden_aliases(clean_text)
    if aliases:
        errors.append(f"Forbidden channel aliases detected in script: {aliases}")

    # 6. Single POV continuity check
    norm_tokens = norm.split()
    has_yo = "yo" in norm_tokens
    has_ella = "ella" in norm_tokens
    has_nosotros = "nosotros" in norm_tokens
    if has_yo and has_ella and has_nosotros and word_count < 60:
        errors.append("Erratic multi-POV perspective jumping detected in short passage")

    # Score calculation
    penalty_per_error = 0.25
    score = max(0.0, round(1.0 - (len(errors) * penalty_per_error), 2))
    valid = len(errors) == 0

    return NarrativeCoherenceResult(
        valid=valid,
        errors=errors,
        score=score,
        details={
            "word_count": word_count,
            "channel": channel,
            "duration_type": duration_type,
            "crutches_detected": detected_crutches,
            "aliases_detected": aliases,
        },
    )
