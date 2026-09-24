"""
src/core/scoring/models.py - Data contracts and scoring configuration thresholds.

Provides strongly typed reports for heuristic, semantic, and hybrid story evaluation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Default Configurable Thresholds & Weights
# ---------------------------------------------------------------------------
DEFAULT_HEURISTIC_THRESHOLD: float = float(
    os.environ.get("SCORING_HEURISTIC_THRESHOLD", "0.40")
)
DEFAULT_SEMANTIC_THRESHOLD: float = float(
    os.environ.get("SCORING_SEMANTIC_THRESHOLD", os.environ.get("SCORING_LLM_THRESHOLD", "0.65"))
)
DEFAULT_HYBRID_THRESHOLD: float = float(
    os.environ.get("SCORING_HYBRID_THRESHOLD", "0.60")
)
DEFAULT_ALPHA: float = float(os.environ.get("SCORING_ALPHA", "0.30"))


# ---------------------------------------------------------------------------
# Data Structures & Contract Reports
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HeuristicScoreReport:
    """Stage 1 Fast Heuristic Evaluation Report."""

    engagement_score: float  # 0.0 - 1.0
    retention_length_score: float  # 0.0 - 1.0
    hook_score: float  # 0.0 - 1.0
    composite_heuristic_score: float  # 0.0 - 1.0
    passed_stage1: bool
    rejection_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "engagement_score": self.engagement_score,
            "retention_length_score": self.retention_length_score,
            "hook_score": self.hook_score,
            "composite_heuristic_score": self.composite_heuristic_score,
            "passed_stage1": self.passed_stage1,
            "rejection_reasons": list(self.rejection_reasons),
        }


@dataclass(frozen=True)
class SemanticScoreReport:
    """Stage 2 Semantic / Viral Potential Evaluation Report."""

    dramatic_potential: float  # 1.0 - 10.0
    viewer_retention: float  # 1.0 - 10.0
    surprise_factor: float  # 1.0 - 10.0
    tone_alignment: float  # 1.0 - 10.0
    overall_semantic_score: float  # 0.0 - 1.0
    verdict: str  # "ACCEPTED" | "REJECTED"
    hook_quality: str  # "poor" | "acceptable" | "strong" | "excellent"
    rejection_reasons: tuple[str, ...] = ()
    detected_viral_hooks: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "dramatic_potential": self.dramatic_potential,
            "viewer_retention": self.viewer_retention,
            "surprise_factor": self.surprise_factor,
            "tone_alignment": self.tone_alignment,
            "overall_semantic_score": self.overall_semantic_score,
            "verdict": self.verdict,
            "hook_quality": self.hook_quality,
            "rejection_reasons": list(self.rejection_reasons),
            "detected_viral_hooks": list(self.detected_viral_hooks),
        }


@dataclass(frozen=True)
class StoryScoringVerdict:
    """Final Synthesis & Enqueue Gate Verdict."""

    story_id: str
    passed: bool
    hybrid_score: float  # 0.0 - 1.0
    db_rank_score: int  # 0 - 1000 integer for SQL index sorting
    heuristic_report: HeuristicScoreReport
    semantic_report: Optional[SemanticScoreReport] = None
    rejection_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "story_id": self.story_id,
            "passed": self.passed,
            "hybrid_score": self.hybrid_score,
            "db_rank_score": self.db_rank_score,
            "heuristic_report": self.heuristic_report.to_dict(),
            "semantic_report": self.semantic_report.to_dict() if self.semantic_report else None,
            "rejection_summary": self.rejection_summary,
        }
