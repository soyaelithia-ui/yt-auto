"""src/scrapers/reddit/quality.py - Story quality verification and filtering for Reddit."""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from typing import Optional

from src.scrapers.common import _to_float, _to_int

logger = logging.getLogger("scraper")


def _env_min_score() -> int:
    """Read REDDIT_MIN_SCORE at call time (0 disables the filter)."""
    return max(0, _to_int(os.environ.get("REDDIT_MIN_SCORE"), 0))


def _env_min_upvote_ratio() -> float:
    """Read REDDIT_MIN_UPVOTE_RATIO at call time (0.0 disables the filter)."""
    return max(0.0, _to_float(os.environ.get("REDDIT_MIN_UPVOTE_RATIO"), 0.0))


def _is_deleted_or_removed(text: Optional[str]) -> bool:
    """Helper to check if a field contains deleted/removed post markers or HTTP error pages."""
    if not text:
        return False
    lower = text.lower().strip()
    if lower in ("[deleted]", "[removed]"):
        return True
    if "[deleted]" in lower or "[removed]" in lower:
        return True
    if "deleted by" in lower or "removed by" in lower:
        return True
    error_patterns = [
        "error 500", "server error", "404 not found", "504 gateway",
        "gateway timeout", "access denied", "403 forbidden", "too many requests",
        "error 403", "error 502", "error 503", "error 504",
    ]
    if any(pat in lower for pat in error_patterns):
        return True
    return False


def is_high_quality_story(title: str, content: str, min_length: int = 100) -> bool:
    """Filter out low-quality stories (too short or with excessive repetitions)."""
    if not title or not content:
        return False

    clean_content = content.strip()
    if len(clean_content) < min_length:
        return False
    if min_length >= 100 and len(clean_content.split()) < 25:
        return False

    # Filter serialized middle/late parts (e.g. Part 2, Parte 26, [Part 3], Capítulo 4)
    serialized_match = re.search(r'(?i)\b(?:part|parte|capítulo|chapter|pt\.?)\s*([0-9]+)\b', title)
    if serialized_match:
        part_num = int(serialized_match.group(1))
        if part_num > 1:
            logger.info("Skipping serialized middle/late fragment '%s' (Part %d)", title[:50], part_num)
            return False

    parts = re.split(r'[.!?\n]+', content)
    sentences = []
    for p in parts:
        p_clean = re.sub(r'\s+', ' ', p).strip().lower()
        if len(p_clean.split()) >= 4:
            sentences.append(p_clean)

    if sentences:
        counter = Counter(sentences)
        for sent, count in counter.items():
            if count > 3:
                return False
        duplicates = sum(count for sent, count in counter.items() if count > 1)
        if len(sentences) > 5 and (duplicates / len(sentences)) > 0.15:
            return False

    return True


__all__ = [
    "_env_min_score",
    "_env_min_upvote_ratio",
    "_is_deleted_or_removed",
    "is_high_quality_story",
]
