"""src/sanitizer/hashing.py - SimHash script deduplication and Hamming distance evaluation."""

from __future__ import annotations

from typing import Any

from src.core.repository import (
    compute_simhash_64,
    hamming_distance_64,
)


def evaluate_script_simhash(
    candidate_text: str,
    history_hashes: list[int] | tuple[int, ...] | set[int] | Any = None,
    min_hamming_distance: int = 4,
    *,
    repository: Any = None,
    channel: str = "moku",
) -> bool:
    """Returns True if candidate text is sufficiently distinct (Hamming >= min_hamming_distance) against history."""
    candidate_hash = compute_simhash_64(candidate_text)
    if candidate_hash == 0:
        return True

    target_repo = repository or (history_hashes if hasattr(history_hashes, "has_near_duplicate") else None)
    if target_repo is not None and hasattr(target_repo, "has_near_duplicate"):
        return not target_repo.has_near_duplicate(
            channel, candidate_hash, max_distance=min_hamming_distance - 1
        )

    if isinstance(history_hashes, (list, tuple, set)):
        for hist_h in history_hashes:
            if hist_h is not None:
                dist = hamming_distance_64(candidate_hash, int(hist_h))
                if dist < min_hamming_distance:
                    return False
        return True

    return True


__all__ = [
    "compute_simhash_64",
    "hamming_distance_64",
    "evaluate_script_simhash",
]
