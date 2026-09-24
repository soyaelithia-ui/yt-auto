"""
src/core/scoring - Intelligent Selector & 2-Stage Hybrid Scoring Filter Package.

Provides high-throughput, two-stage story evaluation engine:
1. Fast Heuristics: engagement, word retention budget, 0-3s opening hooks, fast reject gate.
2. Semantic / Viral Potential: dramatic potential, viewer retention, surprise factor, tone alignment.
3. Hybrid Scoring Synthesis: composite scoring mapped to [0, 1000] integer for SQL index sorting.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from src.core.scoring.heuristics import (
    _NEGATIVE_GREETING_PATTERNS,
    _NEGATIVE_PREAMBLE_PATTERNS,
    _POSITIVE_IN_MEDIAS_RES,
    _POSITIVE_QUESTION_PATTERNS,
    _POSITIVE_STAKES_PATTERNS,
    _POSITIVE_TENSION_KEYWORDS,
    _normalize_hook_text,
    _strip_accents,
    detect_opening_hook_strength,
    estimate_spoken_seconds,
    evaluate_fast_heuristics,
    evaluate_retention_length_score,
    first_spoken_hook,
    opening_hook_within_budget,
)
from src.core.scoring.models import (
    DEFAULT_ALPHA,
    DEFAULT_HEURISTIC_THRESHOLD,
    DEFAULT_HYBRID_THRESHOLD,
    DEFAULT_SEMANTIC_THRESHOLD,
    HeuristicScoreReport,
    SemanticScoreReport,
    StoryScoringVerdict,
)
from src.core.scoring.semantic import (
    _CONFLICT_PATTERNS,
    _CURIOSITY_PATTERNS,
    _DRAMA_PATTERNS,
    _ESCALATION_PATTERNS,
    _HORROR_PATTERNS,
    _IRONY_PATTERNS,
    _TWIST_PATTERNS,
    _build_semantic_eval_prompt,
    _build_semantic_report_from_llm,
    _evaluate_semantic_deterministically,
    _parse_llm_json_response,
    async_evaluate_semantic_viral_potential,
    evaluate_semantic_viral_potential,
)


def compute_hybrid_story_score(
    heuristic: HeuristicScoreReport,
    semantic: Optional[SemanticScoreReport] = None,
    alpha: float = DEFAULT_ALPHA,
    hybrid_threshold: float = DEFAULT_HYBRID_THRESHOLD,
    story_id: str = "",
) -> StoryScoringVerdict:
    """Synthesizes Stage 1 Fast Heuristics and Stage 2 Semantic reports into a composite score."""
    if semantic is not None:
        raw_hybrid = (
            alpha * heuristic.composite_heuristic_score
            + (1.0 - alpha) * semantic.overall_semantic_score
        )
        semantic_passed = semantic.verdict == "ACCEPTED" and semantic.overall_semantic_score >= 0.50
    else:
        raw_hybrid = heuristic.composite_heuristic_score
        semantic_passed = False

    hybrid_score = round(max(0.0, min(1.0, raw_hybrid)), 4)
    db_rank_score = int(round(hybrid_score * 1000))

    passed = (
        heuristic.passed_stage1
        and (semantic is None or semantic_passed)
        and (hybrid_score >= hybrid_threshold)
    )

    rejection_parts: list[str] = []
    if not heuristic.passed_stage1:
        rejection_parts.extend(heuristic.rejection_reasons)
    if semantic is not None and not semantic_passed:
        rejection_parts.extend(semantic.rejection_reasons)
    if hybrid_score < hybrid_threshold:
        rejection_parts.append("hybrid_score_below_threshold")

    return StoryScoringVerdict(
        story_id=story_id,
        passed=passed,
        hybrid_score=hybrid_score,
        db_rank_score=db_rank_score,
        heuristic_report=heuristic,
        semantic_report=semantic,
        rejection_summary="; ".join(rejection_parts) if rejection_parts else "",
    )


def _extract_story_fields(story: Dict[str, Any]) -> tuple[str, str, str, int, float, int, Optional[float]]:
    """Extract and normalize standard metadata fields from a story mapping."""
    story_id = str(story.get("id") or story.get("story_id") or "")
    title = str(story.get("title") or "")
    content = str(
        story.get("content")
        or story.get("body")
        or story.get("selftext")
        or story.get("text")
        or ""
    )
    score = int(story.get("score") or story.get("ups") or 0)
    upvote_ratio = float(story.get("upvote_ratio") or 0.0)
    num_comments = int(story.get("num_comments") or story.get("comments") or 0)
    created_utc = story.get("created_utc") or story.get("created")
    if created_utc is not None:
        try:
            created_utc = float(created_utc)
        except (ValueError, TypeError):
            created_utc = None
    return story_id, title, content, score, upvote_ratio, num_comments, created_utc


def filter_and_score_story(
    story: Dict[str, Any],
    lane: Any = None,
    llm_client: Optional[Any] = None,
    heuristic_threshold: float = DEFAULT_HEURISTIC_THRESHOLD,
    semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
    hybrid_threshold: float = DEFAULT_HYBRID_THRESHOLD,
    alpha: float = DEFAULT_ALPHA,
) -> StoryScoringVerdict:
    """End-to-end 2-Stage Story Scoring and Quality Gate Filter (short-circuits Stage 2 if Stage 1 fails)."""
    story_id, title, content, score, upvote_ratio, num_comments, created_utc = _extract_story_fields(story)

    heuristic_report = evaluate_fast_heuristics(
        title=title,
        content=content,
        score=score,
        upvote_ratio=upvote_ratio,
        num_comments=num_comments,
        created_utc=created_utc,
        lane=lane,
        min_heuristic_threshold=heuristic_threshold,
    )

    if not heuristic_report.passed_stage1:
        return compute_hybrid_story_score(
            heuristic=heuristic_report,
            semantic=None,
            alpha=alpha,
            hybrid_threshold=hybrid_threshold,
            story_id=story_id,
        )

    lane_id = getattr(lane, "id", str(lane or "horror-horror-long"))
    target_format = "short" if "short" in str(lane_id).lower() else "longform"

    semantic_report = evaluate_semantic_viral_potential(
        title=title,
        content=content,
        channel_lane=lane_id,
        target_format=target_format,
        client=llm_client,
        min_semantic_threshold=semantic_threshold,
    )

    return compute_hybrid_story_score(
        heuristic=heuristic_report,
        semantic=semantic_report,
        alpha=alpha,
        hybrid_threshold=hybrid_threshold,
        story_id=story_id,
    )


async def async_filter_and_score_story(
    story: Dict[str, Any],
    lane: Any = None,
    llm_client: Optional[Any] = None,
    heuristic_threshold: float = DEFAULT_HEURISTIC_THRESHOLD,
    semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
    hybrid_threshold: float = DEFAULT_HYBRID_THRESHOLD,
    alpha: float = DEFAULT_ALPHA,
) -> StoryScoringVerdict:
    """Async end-to-end 2-Stage Story Scoring and Quality Gate Filter."""
    story_id, title, content, score, upvote_ratio, num_comments, created_utc = _extract_story_fields(story)

    heuristic_report = evaluate_fast_heuristics(
        title=title,
        content=content,
        score=score,
        upvote_ratio=upvote_ratio,
        num_comments=num_comments,
        created_utc=created_utc,
        lane=lane,
        min_heuristic_threshold=heuristic_threshold,
    )

    if not heuristic_report.passed_stage1:
        return compute_hybrid_story_score(
            heuristic=heuristic_report,
            semantic=None,
            alpha=alpha,
            hybrid_threshold=hybrid_threshold,
            story_id=story_id,
        )

    lane_id = getattr(lane, "id", str(lane or "horror-horror-long"))
    target_format = "short" if "short" in str(lane_id).lower() else "longform"

    semantic_report = await async_evaluate_semantic_viral_potential(
        title=title,
        content=content,
        channel_lane=lane_id,
        target_format=target_format,
        client=llm_client,
        min_semantic_threshold=semantic_threshold,
    )

    return compute_hybrid_story_score(
        heuristic=heuristic_report,
        semantic=semantic_report,
        alpha=alpha,
        hybrid_threshold=hybrid_threshold,
        story_id=story_id,
    )


__all__ = [
    "DEFAULT_ALPHA",
    "DEFAULT_HEURISTIC_THRESHOLD",
    "DEFAULT_HYBRID_THRESHOLD",
    "DEFAULT_SEMANTIC_THRESHOLD",
    "HeuristicScoreReport",
    "SemanticScoreReport",
    "StoryScoringVerdict",
    "async_evaluate_semantic_viral_potential",
    "async_filter_and_score_story",
    "compute_hybrid_story_score",
    "detect_opening_hook_strength",
    "estimate_spoken_seconds",
    "evaluate_fast_heuristics",
    "evaluate_retention_length_score",
    "evaluate_semantic_viral_potential",
    "filter_and_score_story",
    "first_spoken_hook",
    "opening_hook_within_budget",
]
