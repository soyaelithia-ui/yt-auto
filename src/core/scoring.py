"""Intelligent Selector & 2-Stage Hybrid Scoring Filter (Milestone M2 - R2).

Provides a high-throughput, two-stage story evaluation engine:
1. Stage 1 Fast Heuristics:
   - Normalized engagement (score, upvote ratio, comment volume, comment velocity).
   - Retention length scoring against lane target word count budgets.
   - 0-100 character opening hook detection (high-stakes tension/dilemma vs conversational fluff).
   - Fast rejection short-circuit gate.
2. Stage 2 Semantic / Viral Potential Evaluation:
   - LLM-as-judge scoring for dramatic potential, viewer retention, surprise factor, channel alignment.
   - Robust deterministic offline fallback for test and quota-exhausted environments.
3. Hybrid Scoring Synthesis:
   - Weighted score synthesis mapped to [0, 1000] integer for SQL index sorting.
   - Quality threshold gate filtering out low-score content prior to queue insertion.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

try:
    from src.log import get_logger
    logger = get_logger("scoring")
except ImportError:
    logger = logging.getLogger("scoring")

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


# ---------------------------------------------------------------------------
# Stage 1: Hook Detection
# ---------------------------------------------------------------------------
def _strip_accents(text: str) -> str:
    """Strip accents and diacritics for uniform keyword matching."""
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _normalize_hook_text(text: str) -> str:
    """Lowercase and diacritic-insensitive normalization preserving question marks."""
    if not text:
        return ""
    normalized = _strip_accents(text.lower())
    return re.sub(r"\s+", " ", normalized).strip()


# Hook dictionaries
_POSITIVE_QUESTION_PATTERNS = [
    r"¿",
    r"\?",
    r"\bsoy el malo\b",
    r"\bsoy la mala\b",
    r"\baita\b",
    r"\bam i the asshole\b",
    r"\bam i the jerk\b",
    r"\bque deberia hacer\b",
    r"\bque harian ustedes\b",
    r"\bque harias\b",
    r"\bpor que nadie me cree\b",
    r"\bpor que no debi\b",
    r"\bpor que nunca debi\b",
    r"\bque harias si\b",
    r"\bwould you\b",
    r"\bwhat would you do\b",
]

_POSITIVE_TENSION_KEYWORDS = [
    r"\bprohibid[oa]s?\b",
    r"\bmuerte\b",
    r"\bmatar\b",
    r"\bsangre\b",
    r"\bsecreto\b",
    r"\bdescubr[íi]\b",
    r"\bdescubri\b",
    r"\bnunca\b",
    r"\batrapad[oa]s?\b",
    r"\bgrit[oó]\b",
    r"\bgrito\b",
    r"\bregla\b",
    r"\breglas\b",
    r"\bhuye\b",
    r"\bhuyan\b",
    r"\bdemonio\b",
    r"\banomal[íi]a\b",
    r"\banomalia\b",
    r"\bcontenci[óo]n\b",
    r"\bcontencion\b",
    r"\binfidelidad\b",
    r"\bherencia\b",
    r"\btraici[óo]n\b",
    r"\btraicion\b",
    r"\bno deb[íi]\b",
    r"\bno debi\b",
    r"\bemergencia\b",
    r"\basesinat[oó]\b",
    r"\basesinato\b",
    r"\bcad[áa]ver\b",
    r"\bcadaver\b",
    r"\bpeligro\b",
    r"\bterror\b",
    r"\bscp-\d+\b",
    r"\bb[úu]nker\b",
    r"\bbunker\b",
    r"\bpesadilla\b",
    r"\bamenaza\b",
    r"\bdesaparici[óo]n\b",
    r"\bdesaparicion\b",
    r"\benterrad[oa]s?\b",
    r"\bmonstruo\b",
    r"\bcriatura\b",
    r"\bsombra\b",
    r"\bentidad\b",
    r"\bclaustrofobia\b",
    r"\bveneno\b",
    r"\bsiniestr[oa]\b",
    r"\bparanormal\b",
    r"\bmaldici[óo]n\b",
    r"\bmaldicion\b",
]

_POSITIVE_IN_MEDIAS_RES = [
    r"\bescuch[éé]\b",
    r"\bescuche\b",
    r"\bvi\b",
    r"\bencontr[éé]\b",
    r"\bencontre\b",
    r"\bme obligaron\b",
    r"\bestaba sol[oa]\b",
    r"\ba las \d+(?::\d+)?\s*(?:am|pm|horas|hrs)?\b",
    r"\beran las \d+(?::\d+)?\b",
    r"\bdespert[éé]\b",
    r"\bdesperte\b",
    r"\bsent[íi]\b",
    r"\bsenti\b",
    r"\bcorr[íi]\b",
    r"\bcorri\b",
    r"\bentr[éé]\b",
    r"\bentre\b",
    r"\bi heard\b",
    r"\bi saw\b",
    r"\bi found\b",
    r"\bi woke up\b",
    r"\bit was \d+\s*(?:am|pm)\b",
    r"\blocked in\b",
]

_POSITIVE_STAKES_PATTERNS = [
    r"\b\d+\s*minutos?\b",
    r"\b\d+\s*segundos?\b",
    r"\b\d+\s*horas?\b",
    r"\b\d+\s*(?:a[ñn]os|years)\b",
    r"\b[úu]nica regla\b",
    r"\bunica regla\b",
    r"\buna regla\b",
    r"\bsolo hay una regla\b",
    r"\bprimera regla\b",
    r"\bsegunda regla\b",
    r"\btercera regla\b",
    r"\bregla n[úu]mero \d+\b",
    r"\b\d+\s*reglas\b",
    r"\b[úu]ltima advertencia\b",
    r"\bultima advertencia\b",
    r"\buna advertencia\b",
    r"\bdespu[ée]s de \d+\s*a[ñn]os\b",
    r"\bdespues de \d+\s*anos\b",
    r"\bhace \d+\s*a[ñn]os\b",
    r"\bhace \d+\s*anos\b",
    r"\bonly one rule\b",
    r"\blast warning\b",
]

_NEGATIVE_GREETING_PATTERNS = [
    r"\bhola a todos\b",
    r"\bbuenas noches\b",
    r"\bbuenos d[íi]as\b",
    r"\bbuenos dias\b",
    r"\bbuenas tardes\b",
    r"\bhola gente\b",
    r"\bhola reddit\b",
    r"\bsaludos a todos\b",
    r"\bhello everyone\b",
    r"\bhi all\b",
    r"\bhey guys\b",
    r"\bhello reddit\b",
    r"\bhi everyone\b",
]

_NEGATIVE_PREAMBLE_PATTERNS = [
    r"\bsoy nuevo en este sub\b",
    r"\bprimer post\b",
    r"\bprimero que nada\b",
    r"\bperd[óo]n por mi ortograf[íi]a\b",
    r"\bperdon por mi ortografia\b",
    r"\beste es un post largo\b",
    r"\bdisculpen el formato\b",
    r"\bdisculpen la ortograf[íi]a\b",
    r"\bfirst time posting\b",
    r"\bsorry for my english\b",
    r"\bthrowaway account\b",
    r"\bcuenta secundaria\b",
    r"\blargo tiempo leyendo\b",
    r"\bpara ponerlos en contexto\b",
    r"\bantes de empezar\b",
    r"\bsiempre he sido una persona normal\b",
    r"\bsiempre fui una persona com[úu]n\b",
    r"\bsiempre he sido una persona comun\b",
    r"\bno s[ée] por d[óo]nde empezar\b",
    r"\bno se por donde empezar\b",
    r"\bespero que les guste\b",
]


def detect_opening_hook_strength(
    title: str,
    content: str,
) -> tuple[float, list[str], list[str]]:
    """Analyzes title and first 100 characters of content for high-stakes opening hooks vs conversational chatter.

    Returns:
        tuple of (hook_score, positive_markers_found, negative_penalties_found)
    """
    clean_title = (title or "").strip()
    clean_content = (content or "").strip()

    if not clean_title and not clean_content:
        return 0.0, [], ["empty_input"]

    opening_100 = clean_content[:100]
    combined_hook_area = f"{clean_title} {opening_100}"
    normalized_opening = _normalize_hook_text(opening_100)
    normalized_combined = _normalize_hook_text(combined_hook_area)

    positive_markers: list[str] = []
    negative_penalties: list[str] = []

    base_score = 0.50
    positive_bonus = 0.0
    negative_penalty = 0.0

    # 1. Negative penalties (strictly in opening 100 characters or beginning of text)
    greeting_matched = False
    for pat in _NEGATIVE_GREETING_PATTERNS:
        if re.search(pat, normalized_opening):
            negative_penalties.append(f"conversational_greeting: {pat.replace(r'\b', '')}")
            greeting_matched = True
            break

    if greeting_matched:
        negative_penalty += 0.40

    preamble_matched = False
    for pat in _NEGATIVE_PREAMBLE_PATTERNS:
        if re.search(pat, normalized_opening):
            negative_penalties.append(f"exposition_or_meta_preamble: {pat.replace(r'\b', '')}")
            preamble_matched = True
            break

    if preamble_matched:
        negative_penalty += 0.35

    # 2. Positive indicators (in title or opening 100 characters)
    # Questions / Dilemmas
    question_found = False
    for pat in _POSITIVE_QUESTION_PATTERNS:
        if re.search(pat, combined_hook_area, flags=re.IGNORECASE) or re.search(pat, normalized_combined):
            positive_markers.append("question_or_moral_dilemma")
            question_found = True
            break
    if question_found:
        positive_bonus += 0.25

    # High-tension / Urgent conflict keywords
    matched_tension: list[str] = []
    for pat in _POSITIVE_TENSION_KEYWORDS:
        if re.search(pat, normalized_combined):
            matched_tension.append(pat.replace(r"\b", ""))
            if len(matched_tension) >= 2:
                break
    if matched_tension:
        positive_markers.append(f"high_tension_keywords: {', '.join(matched_tension)}")
        positive_bonus += min(0.35, 0.20 + 0.10 * len(matched_tension))

    # In medias res / Immersive first person
    matched_in_medias: list[str] = []
    for pat in _POSITIVE_IN_MEDIAS_RES:
        if re.search(pat, normalized_opening):
            matched_in_medias.append(pat.replace(r"\b", ""))
            break
    if matched_in_medias:
        positive_markers.append(f"in_medias_res_opening: {', '.join(matched_in_medias)}")
        positive_bonus += 0.25

    # Numerical stakes / time constraints
    matched_stakes: list[str] = []
    for pat in _POSITIVE_STAKES_PATTERNS:
        if re.search(pat, normalized_combined):
            matched_stakes.append(pat.replace(r"\b", ""))
            break
    if matched_stakes:
        positive_markers.append(f"stakes_or_time_constraint: {', '.join(matched_stakes)}")
        positive_bonus += 0.20

    raw_score = base_score + positive_bonus - negative_penalty
    clamped_score = max(0.0, min(1.0, raw_score))

    return round(clamped_score, 4), positive_markers, negative_penalties


# ---------------------------------------------------------------------------
# Stage 1: Retention Length Scoring
# ---------------------------------------------------------------------------
def evaluate_retention_length_score(
    word_count: int,
    words_min: int = 160,
    words_max: Optional[int] = 340,
    words_target: int = 250,
) -> float:
    """Scores story word length against lane budget target and bounds.

    Returns:
        float score in [0.0, 1.0]
    """
    if word_count <= 0:
        return 0.0

    w_min = max(1, words_min)
    w_target = max(w_min, words_target)

    # 1. Under minimum word count (severe penalty)
    if word_count < w_min:
        score = (word_count / float(w_min)) * 0.50
        return round(max(0.0, min(1.0, score)), 4)

    # 2. Open-ended longform (words_max is None)
    if words_max is None:
        if word_count >= w_target:
            return 1.0
        denom = max(1, w_target - w_min)
        score = 0.80 + 0.20 * ((word_count - w_min) / float(denom))
        return round(max(0.0, min(1.0, score)), 4)

    # 3. Constrained format with words_max (e.g. Shorts)
    w_max = max(w_target, words_max)
    if w_min <= word_count <= w_max:
        denom = max(w_target - w_min, w_max - w_target, 1)
        score = 1.0 - 0.20 * (abs(word_count - w_target) / float(denom))
        return round(max(0.0, min(1.0, score)), 4)

    # 4. Over maximum word count
    score = 1.0 - 0.50 * ((word_count - w_max) / float(w_max))
    return round(max(0.0, min(1.0, score)), 4)


# ---------------------------------------------------------------------------
# Stage 1: Fast Heuristics Orchestration
# ---------------------------------------------------------------------------
def evaluate_fast_heuristics(
    title: str,
    content: str,
    score: int = 0,
    upvote_ratio: float = 0.0,
    num_comments: int = 0,
    created_utc: Optional[float] = None,
    lane: Optional[Any] = None,
    min_heuristic_threshold: float = DEFAULT_HEURISTIC_THRESHOLD,
) -> HeuristicScoreReport:
    """Evaluates Stage 1 Fast Heuristics: engagement, retention length, and opening hook."""
    clean_title = (title or "").strip()
    clean_content = (content or "").strip()

    # 1. Normalize Engagement Metrics
    s_score = min(1.0, max(0.0, float(score)) / 500.0)
    s_ratio = max(0.0, min(1.0, float(upvote_ratio)))
    s_comments = min(1.0, max(0.0, float(num_comments)) / 100.0)

    if created_utc is not None and created_utc > 0:
        now_ts = time.time()
        delta_hours = max(0.0, (now_ts - float(created_utc)) / 3600.0)
        velocity = float(num_comments) / (delta_hours + 1.0)
        s_velocity = min(1.0, max(0.0, velocity / 20.0))
        engagement_score = (
            0.35 * s_ratio
            + 0.30 * s_score
            + 0.20 * s_comments
            + 0.15 * s_velocity
        )
    else:
        engagement_score = 0.40 * s_ratio + 0.35 * s_score + 0.25 * s_comments

    engagement_score = round(max(0.0, min(1.0, engagement_score)), 4)

    # 2. Opening Hook Detection
    hook_score, pos_markers, neg_penalties = detect_opening_hook_strength(clean_title, clean_content)

    # 3. Word Budget & Retention Length Scoring
    words = re.findall(r"\b\w+\b", clean_content)
    word_count = len(words)

    # Resolve lane constraints
    words_min = 160
    words_max: Optional[int] = 340
    words_target = 250

    if lane is not None:
        if isinstance(lane, dict):
            words_dict = lane.get("words", {})
            words_min = words_dict.get("min", lane.get("words_min", 160))
            words_max = words_dict.get("max", lane.get("words_max", 340))
            duration_target = lane.get("duration", {}).get("target_sec", 150)
            words_target = max(words_min, int(duration_target * 1.6))
        elif hasattr(lane, "words_min"):
            words_min = getattr(lane, "words_min", 160)
            words_max = getattr(lane, "words_max", 340)
            dur_target = getattr(lane, "duration_target_sec", 150)
            if words_max is not None:
                words_target = (words_min + words_max) // 2
            else:
                words_target = max(words_min, int(dur_target * 2.2))
        elif isinstance(lane, str):
            lane_str = lane.lower()
            if "long" in lane_str or "compilation" in lane_str:
                words_min = 2600
                words_max = None
                words_target = 3000
            elif "short" in lane_str:
                words_min = 160
                words_max = 340
                words_target = 250

    retention_length_score = evaluate_retention_length_score(
        word_count=word_count,
        words_min=words_min,
        words_max=words_max,
        words_target=words_target,
    )

    # 4. Composite Fast Heuristic Score
    composite_heuristic_score = (
        0.35 * engagement_score
        + 0.30 * hook_score
        + 0.35 * retention_length_score
    )
    composite_heuristic_score = round(max(0.0, min(1.0, composite_heuristic_score)), 4)

    passed_stage1 = composite_heuristic_score >= min_heuristic_threshold

    # 5. Build rejection reasons
    reasons: list[str] = []
    if not passed_stage1:
        reasons.append("composite_heuristic_score_below_threshold")
    if retention_length_score < 0.30:
        reasons.append("insufficient_word_length_retention")
    if hook_score < 0.25:
        reasons.append("weak_opening_hook")
    if engagement_score < 0.15:
        reasons.append("low_engagement_metrics")
    for neg in neg_penalties:
        reasons.append(neg)

    return HeuristicScoreReport(
        engagement_score=engagement_score,
        retention_length_score=retention_length_score,
        hook_score=hook_score,
        composite_heuristic_score=composite_heuristic_score,
        passed_stage1=passed_stage1,
        rejection_reasons=tuple(reasons),
    )


# ---------------------------------------------------------------------------
# Stage 2: Semantic / Viral Potential Evaluation (LLM & Deterministic Fallback)
# ---------------------------------------------------------------------------
def _evaluate_semantic_deterministically(
    title: str,
    content: str,
    channel_lane: str = "moku-horror-long",
    target_format: str = "longform",
    min_semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
) -> SemanticScoreReport:
    """Genuine, deterministic offline heuristic calculation of semantic viral dimensions."""
    clean_title = (title or "").strip()
    clean_content = (content or "").strip()
    full_text = f"{clean_title}\n\n{clean_content}"
    normalized = _strip_accents(full_text.lower())

    detected_hooks: list[str] = []
    rejection_reasons: list[str] = []

    # 1. Dramatic Potential (1.0 - 10.0)
    d_score = 5.0

    # Conflict / stakes themes
    conflict_matches = 0
    conflict_patterns = [
        r"\bconflicto\b", r"\bpelea\b", r"\bdiscusi[óo]n\b", r"\bamenaza\b",
        r"\bterror\b", r"\bpeligro\b", r"\bmuerte\b", r"\bgrito\b",
        r"\bsangre\b", r"\bhuir\b", r"\batrapad[oa]\b", r"\bemergencia\b",
        r"\bmiedo\b", r"\bp[áa]nico\b", r"\bdesesperaci[óo]n\b", r"\btraici[óo]n\b",
        r"\binfidelidad\b", r"\bdemanda\b", r"\babogad[oa]\b", r"\bc[áa]rcel\b",
        r"\bpolic[íi]a\b", r"\baccidente\b", r"\bvenganza\b", r"\brepresalia\b",
        r"\bpesadilla\b", r"\baterrador\b", r"\bcontenci[óo]n\b", r"\bb[úu]nker\b",
        r"\bsecreto\b", r"\brompi[óo]\b", r"\bfall[óo]\b", r"\bdestrucci[óo]n\b",
        r"\bherencia\b", r"\benga[ñn]o\b", r"\bdeuda\b", r"\bexigi[óo]\b",
        r"\bpresi[óo]n\b", r"\bdesastre\b", r"\banomal[íi]a\b", r"\bscp\b",
    ]
    for pat in conflict_patterns:
        if re.search(pat, normalized):
            conflict_matches += 1

    d_score += min(4.0, 0.60 * conflict_matches)
    if conflict_matches >= 3:
        detected_hooks.append("high_conflict_stakes")

    # Narrative turning points / Escalation markers
    escalation_matches = 0
    escalation_patterns = [
        r"\bde repente\b", r"\bde pronto\b", r"\ben ese momento\b",
        r"\bentonces\b", r"\bfinalmente\b", r"\bal d[íi]a siguiente\b",
        r"\blas cosas empeoraron\b", r"\btodo cambi[óo]\b", r"\ba partir de ah[íi]\b",
        r"\bsuddenly\b", r"\bwithout warning\b",
    ]
    for pat in escalation_patterns:
        if re.search(pat, normalized):
            escalation_matches += 1

    d_score += min(2.0, 0.60 * escalation_matches)
    if escalation_matches >= 1:
        detected_hooks.append("escalating_narrative_pacing")

    # Dialogue presence (active dramatization)
    if re.search(r'["«“—]', full_text):
        d_score += 0.5
        detected_hooks.append("active_dialogue")

    dramatic_potential = round(max(1.0, min(10.0, d_score)), 2)

    # 2. Viewer Retention (1.0 - 10.0)
    r_score = 5.0

    # Curiosity gaps and cliffhanger markers
    curiosity_matches = 0
    curiosity_patterns = [
        r"\bno van a creer\b", r"\blo que pas[óo] despu[ée]s\b", r"\bno esperaba\b",
        r"\bhasta que vi\b", r"\bla raz[óo]n por la que\b", r"\blo peor fue\b",
        r"\bnadie sab[íi]a\b", r"\bsecreto\b", r"\bdescubr[íi]\b",
        r"\blo que encontr[ée]\b", r"\bwhat happened next\b", r"\bnever expected\b",
    ]
    for pat in curiosity_patterns:
        if re.search(pat, normalized):
            curiosity_matches += 1

    r_score += min(2.5, 0.60 * curiosity_matches)
    if curiosity_matches >= 2:
        detected_hooks.append("curiosity_gap_retention")

    # Opening hook integration
    hook_val, _, _ = detect_opening_hook_strength(clean_title, clean_content)
    if hook_val >= 0.80:
        r_score += 1.5
        detected_hooks.append("strong_opening_hook")
    elif hook_val >= 0.50:
        r_score += 0.5
    elif hook_val < 0.20:
        r_score -= 1.5

    # Paragraph structure & pacing
    paragraphs = [p for p in clean_content.split("\n\n") if p.strip()]
    if len(paragraphs) >= 3:
        r_score += 0.5

    viewer_retention = round(max(1.0, min(10.0, r_score)), 2)

    # 3. Surprise / Twist Factor (1.0 - 10.0)
    t_score = 4.5

    twist_matches = 0
    twist_patterns = [
        r"\bresult[óo] que\b", r"\bresulta que\b", r"\bla verdad era\b",
        r"\ben realidad\b", r"\bpara mi sorpresa\b", r"\bnunca me imagin[ée]\b",
        r"\bplot twist\b", r"\bresult[óo] ser\b", r"\bdescubrimos que\b",
        r"\bresult[óo] estar\b", r"\bit turned out\b", r"\bthe truth was\b",
        r"\bto my surprise\b", r"\bdescubr[íi] que\b", r"\btraici[óo]n\b",
        r"\benga[ñn]o\b", r"\bsecreto\b",
    ]
    for pat in twist_patterns:
        if re.search(pat, normalized):
            twist_matches += 1

    t_score += min(3.5, 0.85 * twist_matches)
    if twist_matches >= 1:
        detected_hooks.append("twist_revelation")

    irony_patterns = [
        r"\bir[óo]nicamente\b", r"\bal contrario\b", r"\btodo lo contrario\b",
        r"\bno era quien dec[íi]a\b", r"\benga[ñn]ad[oa]\b", r"\bmentira\b",
        r"\bfals[oa]\b", r"\btrampa\b",
    ]
    for pat in irony_patterns:
        if re.search(pat, normalized):
            t_score += 0.5
            break

    surprise_factor = round(max(1.0, min(10.0, t_score)), 2)

    # 4. Tone & Channel Alignment (1.0 - 10.0)
    a_score = 5.5
    lane_lower = channel_lane.lower()

    if any(k in lane_lower for k in ("moku", "horror", "scp", "terror")):
        horror_matches = 0
        horror_patterns = [
            r"\bscp\b", r"\banomal[íi]a\b", r"\bcontenci[óo]n\b", r"\bentidad\b",
            r"\bobjeto\b", r"\bsujeto\b", r"\bclase\b", r"\beuclid\b", r"\bketer\b",
            r"\bmonstruo\b", r"\bcriatura\b", r"\bsombra\b", r"\bbosque\b",
            r"\bb[úu]nker\b", r"\bpesadilla\b", r"\bmiedo\b", r"\baterrador\b",
            r"\bsiniestr[oa]\b", r"\bcad[áa]ver\b", r"\bsangre\b", r"\bgrito\b",
            r"\bdemonio\b", r"\bfantasma\b", r"\bparanormal\b", r"\boscur[oa]\b",
            r"\bnoche\b", r"\bcreepypasta\b",
        ]
        for pat in horror_patterns:
            if re.search(pat, normalized):
                horror_matches += 1
        a_score += min(4.5, 0.55 * horror_matches)
        if horror_matches >= 2:
            detected_hooks.append("horror_atmospheric_alignment")
    elif any(k in lane_lower for k in ("aelithia", "aita", "drama", "moral", "relaciones")):
        drama_matches = 0
        drama_patterns = [
            r"\bfamilia\b", r"\bespos[oa]\b", r"\bnovi[oa]\b", r"\bherman[oa]\b",
            r"\bmadre\b", r"\bpadre\b", r"\bsuegr[oa]\b", r"\bboda\b",
            r"\bherencia\b", r"\bdinero\b", r"\bdivorcio\b", r"\binfidelidad\b",
            r"\benga[ñn]o\b", r"\bamig[oa]\b", r"\btrabajo\b", r"\bjefe\b",
            r"\bmoral\b", r"\bculpa\b", r"\bmal[oa]\b", r"\baita\b",
            r"\bopinan\b", r"\bconsejo\b", r"\bdiscusi[óo]n\b", r"\bexigi[óo]\b",
            r"\bdeuda\b", r"\btraici[óo]n\b",
        ]
        for pat in drama_patterns:
            if re.search(pat, normalized):
                drama_matches += 1
        a_score += min(4.5, 0.55 * drama_matches)
        if drama_matches >= 2:
            detected_hooks.append("moral_drama_alignment")
    else:
        a_score = 7.5

    tone_alignment = round(max(1.0, min(10.0, a_score)), 2)

    # 5. Composite Normalized Semantic Score [0.0, 1.0]
    raw_semantic = (
        0.30 * dramatic_potential
        + 0.35 * viewer_retention
        + 0.20 * surprise_factor
        + 0.15 * tone_alignment
    ) / 10.0
    overall_semantic_score = round(max(0.0, min(1.0, raw_semantic)), 4)

    verdict = "ACCEPTED" if overall_semantic_score >= min_semantic_threshold else "REJECTED"

    # Hook quality tier
    if overall_semantic_score >= 0.85:
        hook_quality = "excellent"
    elif overall_semantic_score >= 0.70:
        hook_quality = "strong"
    elif overall_semantic_score >= 0.50:
        hook_quality = "acceptable"
    else:
        hook_quality = "poor"

    if verdict == "REJECTED":
        if dramatic_potential < 5.0:
            rejection_reasons.append("low_dramatic_potential")
        if viewer_retention < 5.0:
            rejection_reasons.append("low_viewer_retention")
        if surprise_factor < 4.0:
            rejection_reasons.append("low_surprise_twist_factor")
        if tone_alignment < 5.0:
            rejection_reasons.append("poor_channel_tone_alignment")
        rejection_reasons.append("semantic_score_below_threshold")

    return SemanticScoreReport(
        dramatic_potential=dramatic_potential,
        viewer_retention=viewer_retention,
        surprise_factor=surprise_factor,
        tone_alignment=tone_alignment,
        overall_semantic_score=overall_semantic_score,
        verdict=verdict,
        hook_quality=hook_quality,
        rejection_reasons=tuple(rejection_reasons),
        detected_viral_hooks=tuple(detected_hooks),
    )


def _parse_llm_json_response(raw_resp: str) -> Optional[dict[str, Any]]:
    """Robust JSON extraction from LLM response text."""
    if not raw_resp:
        return None
    cleaned = raw_resp.strip()
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if json_match:
        cleaned = json_match.group(1).strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            data = json.loads(cleaned[first_brace : last_brace + 1])
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return None


def evaluate_semantic_viral_potential(
    title: str,
    content: str,
    channel_lane: str = "moku-horror-long",
    target_format: str = "longform",
    client: Optional[Any] = None,
    min_semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
) -> SemanticScoreReport:
    """Stage 2 Semantic & Viral Evaluation (LLM-as-judge with deterministic offline fallback).

    Rates dramatic potential, viewer retention, surprise factor, and channel tone alignment (1-10 scale).
    """
    if client is not None:
        try:
            prompt = (
                "You are an expert viral narrative producer and script evaluator. "
                "Analyze the following story for YouTube production potential and respond STRICTLY in valid JSON.\n\n"
                f"Lane: {channel_lane} | Format: {target_format}\n"
                f"Title: {title}\n"
                f"Content:\n{content[:2000]}\n\n"
                "JSON format:\n"
                "{\n"
                '  "dramatic_potential": 1.0-10.0,\n'
                '  "viewer_retention": 1.0-10.0,\n'
                '  "surprise_factor": 1.0-10.0,\n'
                '  "tone_alignment": 1.0-10.0,\n'
                '  "verdict": "ACCEPTED" | "REJECTED",\n'
                '  "hook_quality": "poor" | "acceptable" | "strong" | "excellent",\n'
                '  "key_strengths": ["..."],\n'
                '  "rejection_reasons": ["..."]\n'
                "}"
            )
            raw_result = None
            if hasattr(client, "generate_content"):
                res = client.generate_content(prompt)
                raw_result = getattr(res, "text", str(res))
            elif hasattr(client, "create"):
                res = client.create(messages=[{"role": "user", "content": prompt}])
                raw_result = str(res)
            elif callable(client):
                res = client(prompt)
                raw_result = str(res)

            if raw_result:
                parsed = _parse_llm_json_response(raw_result)
                if parsed and "dramatic_potential" in parsed:
                    d = float(parsed.get("dramatic_potential", 5.0))
                    r = float(parsed.get("viewer_retention", 5.0))
                    t = float(parsed.get("surprise_factor", 5.0))
                    a = float(parsed.get("tone_alignment", 5.0))
                    raw_s = (0.30 * d + 0.35 * r + 0.20 * t + 0.15 * a) / 10.0
                    overall = round(max(0.0, min(1.0, raw_s)), 4)
                    verdict = "ACCEPTED" if overall >= min_semantic_threshold else "REJECTED"
                    hq = str(parsed.get("hook_quality", "acceptable"))
                    reasons = parsed.get("rejection_reasons", [])
                    hooks = parsed.get("key_strengths", [])
                    return SemanticScoreReport(
                        dramatic_potential=round(d, 2),
                        viewer_retention=round(r, 2),
                        surprise_factor=round(t, 2),
                        tone_alignment=round(a, 2),
                        overall_semantic_score=overall,
                        verdict=verdict,
                        hook_quality=hq,
                        rejection_reasons=tuple(str(x) for x in reasons),
                        detected_viral_hooks=tuple(str(x) for x in hooks),
                    )
        except Exception as e:
            logger.warning(f"LLM semantic evaluation failed ({e}), falling back to deterministic analyzer.")

    return _evaluate_semantic_deterministically(
        title=title,
        content=content,
        channel_lane=channel_lane,
        target_format=target_format,
        min_semantic_threshold=min_semantic_threshold,
    )


async def async_evaluate_semantic_viral_potential(
    title: str,
    content: str,
    channel_lane: str = "moku-horror-long",
    target_format: str = "longform",
    client: Optional[Any] = None,
    min_semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
) -> SemanticScoreReport:
    """Async wrapper for Stage 2 Semantic & Viral Evaluation."""
    if client is not None and asyncio.iscoroutinefunction(getattr(client, "generate_content", None)):
        try:
            prompt = (
                "You are an expert viral narrative producer and script evaluator. "
                "Analyze the following story for YouTube production potential and respond STRICTLY in valid JSON.\n\n"
                f"Lane: {channel_lane} | Format: {target_format}\n"
                f"Title: {title}\n"
                f"Content:\n{content[:2000]}\n\n"
                "JSON format:\n"
                "{\n"
                '  "dramatic_potential": 1.0-10.0,\n'
                '  "viewer_retention": 1.0-10.0,\n'
                '  "surprise_factor": 1.0-10.0,\n'
                '  "tone_alignment": 1.0-10.0,\n'
                '  "verdict": "ACCEPTED" | "REJECTED",\n'
                '  "hook_quality": "poor" | "acceptable" | "strong" | "excellent",\n'
                '  "key_strengths": ["..."],\n'
                '  "rejection_reasons": ["..."]\n'
                "}"
            )
            res = await client.generate_content(prompt)
            raw_result = getattr(res, "text", str(res))
            if raw_result:
                parsed = _parse_llm_json_response(raw_result)
                if parsed and "dramatic_potential" in parsed:
                    d = float(parsed.get("dramatic_potential", 5.0))
                    r = float(parsed.get("viewer_retention", 5.0))
                    t = float(parsed.get("surprise_factor", 5.0))
                    a = float(parsed.get("tone_alignment", 5.0))
                    raw_s = (0.30 * d + 0.35 * r + 0.20 * t + 0.15 * a) / 10.0
                    overall = round(max(0.0, min(1.0, raw_s)), 4)
                    verdict = "ACCEPTED" if overall >= min_semantic_threshold else "REJECTED"
                    hq = str(parsed.get("hook_quality", "acceptable"))
                    reasons = parsed.get("rejection_reasons", [])
                    hooks = parsed.get("key_strengths", [])
                    return SemanticScoreReport(
                        dramatic_potential=round(d, 2),
                        viewer_retention=round(r, 2),
                        surprise_factor=round(t, 2),
                        tone_alignment=round(a, 2),
                        overall_semantic_score=overall,
                        verdict=verdict,
                        hook_quality=hq,
                        rejection_reasons=tuple(str(x) for x in reasons),
                        detected_viral_hooks=tuple(str(x) for x in hooks),
                    )
        except Exception as e:
            logger.warning(f"Async LLM evaluation error ({e}), falling back to deterministic analyzer.")

    return evaluate_semantic_viral_potential(
        title=title,
        content=content,
        channel_lane=channel_lane,
        target_format=target_format,
        client=client,
        min_semantic_threshold=min_semantic_threshold,
    )


# ---------------------------------------------------------------------------
# Hybrid Scoring Synthesis & Filtering Gate
# ---------------------------------------------------------------------------
def compute_hybrid_story_score(
    heuristic: HeuristicScoreReport,
    semantic: Optional[SemanticScoreReport] = None,
    alpha: float = DEFAULT_ALPHA,
    hybrid_threshold: float = DEFAULT_HYBRID_THRESHOLD,
    story_id: str = "",
) -> StoryScoringVerdict:
    """Synthesizes Stage 1 Fast Heuristics and Stage 2 Semantic reports into a composite score.

    Score formula:
        S_hybrid = alpha * S_heur + (1 - alpha) * S_llm (if semantic present)
        S_hybrid = S_heur (if semantic absent)
    Mapped to [0, 1000] integer for SQL index sorting.
    """
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

    rejection_summary = "; ".join(rejection_parts) if rejection_parts else ""

    return StoryScoringVerdict(
        story_id=story_id,
        passed=passed,
        hybrid_score=hybrid_score,
        db_rank_score=db_rank_score,
        heuristic_report=heuristic,
        semantic_report=semantic,
        rejection_summary=rejection_summary,
    )


def filter_and_score_story(
    story: Dict[str, Any],
    lane: Any = None,
    llm_client: Optional[Any] = None,
    heuristic_threshold: float = DEFAULT_HEURISTIC_THRESHOLD,
    semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
    hybrid_threshold: float = DEFAULT_HYBRID_THRESHOLD,
    alpha: float = DEFAULT_ALPHA,
) -> StoryScoringVerdict:
    """End-to-end 2-Stage Story Scoring and Quality Gate Filter.

    Short-circuits Stage 2 if Stage 1 Fast Heuristics fails.
    """
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

    # Stage 1: Fast Heuristics
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

    # Fast short-circuit: do NOT execute Stage 2 LLM if Stage 1 failed
    if not heuristic_report.passed_stage1:
        return compute_hybrid_story_score(
            heuristic=heuristic_report,
            semantic=None,
            alpha=alpha,
            hybrid_threshold=hybrid_threshold,
            story_id=story_id,
        )

    # Stage 2: Semantic / Viral Potential
    lane_id = getattr(lane, "id", str(lane or "moku-horror-long"))
    target_format = "short" if "short" in lane_id.lower() else "longform"

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

    lane_id = getattr(lane, "id", str(lane or "moku-horror-long"))
    target_format = "short" if "short" in lane_id.lower() else "longform"

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
