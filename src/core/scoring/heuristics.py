"""
src/core/scoring/heuristics.py - Fast stage 1 heuristics, hook detection, and engagement scoring.

Provides deterministic regex-based opening hook evaluation, spoken duration estimation,
word count retention scoring against lane budgets, and compound heuristic scoring.
"""
from __future__ import annotations

import re
import time
import unicodedata
from typing import Any, Optional

from src.core.scoring.models import DEFAULT_HEURISTIC_THRESHOLD, HeuristicScoreReport

_POSITIVE_QUESTION_PATTERNS = [
    r"¿", r"\?", r"\bsoy el malo\b", r"\bsoy la mala\b", r"\baita\b",
    r"\bam i the asshole\b", r"\bam i the jerk\b", r"\bque deberia hacer\b",
    r"\bque harian ustedes\b", r"\bque harias\b", r"\bpor que nadie me cree\b",
    r"\bpor que no debi\b", r"\bpor que nunca debi\b", r"\bque harias si\b",
    r"\bwould you\b", r"\bwhat would you do\b",
]

_POSITIVE_TENSION_KEYWORDS = [
    r"\bprohibid[oa]s?\b", r"\bmuerte\b", r"\bmatar\b", r"\bsangre\b",
    r"\bsecreto\b", r"\bdescubr[íi]\b", r"\bdescubri\b", r"\bnunca\b",
    r"\batrapad[oa]s?\b", r"\bgrit[oó]\b", r"\bgrito\b", r"\bregla\b",
    r"\breglas\b", r"\bhuye\b", r"\bhuyan\b", r"\bdemonio\b",
    r"\banomal[íi]a\b", r"\banomalia\b", r"\bcontenci[óo]n\b", r"\bcontencion\b",
    r"\binfidelidad\b", r"\bherencia\b", r"\btraici[óo]n\b", r"\btraicion\b",
    r"\bno deb[íi]\b", r"\bno debi\b", r"\bemergencia\b", r"\basesinat[oó]\b",
    r"\basesinato\b", r"\bcad[áa]ver\b", r"\bcadaver\b", r"\bpeligro\b",
    r"\bterror\b", r"\bscp-\d+\b", r"\bb[úu]nker\b", r"\bbunker\b",
    r"\bpesadilla\b", r"\bamenaza\b", r"\bdesaparici[óo]n\b", r"\bdesaparicion\b",
    r"\benterrad[oa]s?\b", r"\bmonstruo\b", r"\bcriatura\b", r"\bsombra\b",
    r"\bentidad\b", r"\bclaustrofobia\b", r"\bveneno\b", r"\bsiniestr[oa]\b",
    r"\bparanormal\b", r"\bmaldici[óo]n\b", r"\bmaldicion\b",
]

_POSITIVE_IN_MEDIAS_RES = [
    r"\bescuch[éé]\b", r"\bescuche\b", r"\bvi\b", r"\bencontr[éé]\b",
    r"\bencontre\b", r"\bme obligaron\b", r"\bestaba sol[oa]\b",
    r"\ba las \d+(?::\d+)?\s*(?:am|pm|horas|hrs)?\b", r"\beran las \d+(?::\d+)?\b",
    r"\bdespert[éé]\b", r"\bdesperte\b", r"\bsent[íi]\b", r"\bsenti\b",
    r"\bcorr[íi]\b", r"\bcorri\b", r"\bentr[éé]\b", r"\bentre\b",
    r"\bi heard\b", r"\bi saw\b", r"\bi found\b", r"\bi woke up\b",
    r"\bit was \d+\s*(?:am|pm)\b", r"\blocked in\b",
]

_POSITIVE_STAKES_PATTERNS = [
    r"\b\d+\s*minutos?\b", r"\b\d+\s*segundos?\b", r"\b\d+\s*horas?\b",
    r"\b\d+\s*(?:a[ñn]os|years)\b", r"\b[úu]nica regla\b", r"\bunica regla\b",
    r"\buna regla\b", r"\bsolo hay una regla\b", r"\bprimera regla\b",
    r"\bsegunda regla\b", r"\btercera regla\b", r"\bregla n[úu]mero \d+\b",
    r"\b\d+\s*reglas\b", r"\b[úu]ltima advertencia\b", r"\bultima advertencia\b",
    r"\buna advertencia\b", r"\bdespu[ée]s de \d+\s*a[ñn]os\b",
    r"\bdespues de \d+\s*anos\b", r"\bhace \d+\s*a[ñn]os\b",
    r"\bhace \d+\s*anos\b", r"\bonly one rule\b", r"\blast warning\b",
]

_NEGATIVE_GREETING_PATTERNS = [
    r"\bhola a todos\b", r"\bbuenas noches\b", r"\bbuenos d[íi]as\b",
    r"\bbuenos dias\b", r"\bbuenas tardes\b", r"\bhola gente\b",
    r"\bhola reddit\b", r"\bsaludos a todos\b", r"\bhello everyone\b",
    r"\bhi all\b", r"\bhey guys\b", r"\bhello reddit\b", r"\bhi everyone\b",
]

_NEGATIVE_PREAMBLE_PATTERNS = [
    r"\bsoy nuevo en este sub\b", r"\bprimer post\b", r"\bprimero que nada\b",
    r"\bperd[óo]n por mi ortograf[íi]a\b", r"\bperdon por mi ortografia\b",
    r"\beste es un post largo\b", r"\bdisculpen el formato\b",
    r"\bdisculpen la ortograf[íi]a\b", r"\bfirst time posting\b",
    r"\bsorry for my english\b", r"\bthrowaway account\b", r"\bcuenta secundaria\b",
    r"\blargo tiempo leyendo\b", r"\bpara ponerlos en contexto\b",
    r"\bantes de empezar\b", r"\bsiempre he sido una persona normal\b",
    r"\bsiempre fui una persona com[úu]n\b", r"\bsiempre he sido una persona comun\b",
    r"\bno s[ée] por d[óo]nde empezar\b", r"\bno se por donde empezar\b",
    r"\bespero que les guste\b",
]


def _strip_accents(text: str) -> str:
    """Remove Latin accents from string."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def _normalize_hook_text(text: str) -> str:
    """Lowercase and diacritic-insensitive normalization preserving question marks."""
    if not text:
        return ""
    normalized = _strip_accents(text.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def estimate_spoken_seconds(text: str, *, words_per_sec: float = 2.7) -> float:
    """Rough Spanish narration duration from word count (~2.7 wps)."""
    words = re.findall(r"\b\w+\b", text or "")
    if not words or words_per_sec <= 0:
        return 0.0
    return round(len(words) / float(words_per_sec), 3)


def first_spoken_hook(text: str, *, max_seconds: float = 3.0, words_per_sec: float = 2.7) -> str:
    """Return the leading clause intended as <=max_seconds spoken hook."""
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if not clean:
        return ""
    parts = re.split(r"(?<=[.!?…])\s+", clean)
    candidate = parts[0] if parts else clean
    max_words = max(1, int(max_seconds * words_per_sec))
    words = re.findall(r"\S+", candidate)
    if len(words) > max_words:
        candidate = " ".join(words[:max_words]).rstrip(",;:") + "."
    return candidate


def opening_hook_within_budget(
    title: str,
    content: str,
    *,
    max_seconds: float = 3.0,
) -> tuple[bool, float, str]:
    """True when the natural first spoken sentence fits within max_seconds."""
    clean = re.sub(r"\s+", " ", (content or title or "").strip())
    parts = re.split(r"(?<=[.!?…])\s+", clean) if clean else [""]
    natural = parts[0] if parts else ""
    secs = estimate_spoken_seconds(natural)
    trimmed = first_spoken_hook(clean, max_seconds=max_seconds)
    return secs <= max_seconds + 0.05, secs, trimmed


def detect_opening_hook_strength(
    title: str,
    content: str,
) -> tuple[float, list[str], list[str]]:
    """Analyzes title and first 100 characters of content for high-stakes opening hooks."""
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

    # Negative penalties in opening 100 characters
    for pat in _NEGATIVE_GREETING_PATTERNS:
        if re.search(pat, normalized_opening):
            clean_pat = pat.replace("\\b", "")
            negative_penalties.append(f"conversational_greeting: {clean_pat}")
            negative_penalty += 0.40
            break

    for pat in _NEGATIVE_PREAMBLE_PATTERNS:
        if re.search(pat, normalized_opening):
            clean_pat = pat.replace("\\b", "")
            negative_penalties.append(f"exposition_or_meta_preamble: {clean_pat}")
            negative_penalty += 0.35
            break

    # Positive indicators
    question_found = False
    for pat in _POSITIVE_QUESTION_PATTERNS:
        if re.search(pat, combined_hook_area, flags=re.IGNORECASE) or re.search(pat, normalized_combined):
            positive_markers.append("question_or_moral_dilemma")
            question_found = True
            break
    if question_found:
        positive_bonus += 0.25

    matched_tension: list[str] = []
    for pat in _POSITIVE_TENSION_KEYWORDS:
        if re.search(pat, normalized_combined):
            matched_tension.append(pat.replace(r"\b", ""))
            if len(matched_tension) >= 2:
                break
    if matched_tension:
        positive_markers.append(f"high_tension_keywords: {', '.join(matched_tension)}")
        positive_bonus += min(0.35, 0.20 + 0.10 * len(matched_tension))

    for pat in _POSITIVE_IN_MEDIAS_RES:
        if re.search(pat, normalized_opening):
            clean_pat = pat.replace("\\b", "")
            positive_markers.append(f"in_medias_res_opening: {clean_pat}")
            positive_bonus += 0.25
            break

    for pat in _POSITIVE_STAKES_PATTERNS:
        if re.search(pat, normalized_combined):
            clean_pat = pat.replace("\\b", "")
            positive_markers.append(f"stakes_or_time_constraint: {clean_pat}")
            positive_bonus += 0.20
            break

    within, hook_secs, _ = opening_hook_within_budget(clean_title, clean_content, max_seconds=3.0)
    if within and positive_bonus > 0:
        positive_bonus += 0.10
        positive_markers.append(f"spoken_hook_within_3s:{hook_secs:.2f}s")
    elif (not within) and hook_secs > 4.5 and positive_bonus < 0.25:
        negative_penalty += 0.15
        negative_penalties.append(f"spoken_hook_too_long:{hook_secs:.2f}s")

    raw_score = base_score + positive_bonus - negative_penalty
    clamped_score = max(0.0, min(1.0, raw_score))

    return round(clamped_score, 4), positive_markers, negative_penalties


def evaluate_retention_length_score(
    word_count: int,
    words_min: int = 160,
    words_max: Optional[int] = 340,
    words_target: int = 250,
) -> float:
    """Scores story word length against lane budget target and bounds."""
    if word_count <= 0:
        return 0.0

    w_min = max(1, words_min)
    w_target = max(w_min, words_target)

    if word_count < w_min:
        return round(max(0.0, min(1.0, (word_count / float(w_min)) * 0.50)), 4)

    if words_max is None:
        if word_count >= w_target:
            return 1.0
        denom = max(1, w_target - w_min)
        return round(max(0.0, min(1.0, 0.80 + 0.20 * ((word_count - w_min) / float(denom)))), 4)

    w_max = max(w_target, words_max)
    if w_min <= word_count <= w_max:
        denom = max(w_target - w_min, w_max - w_target, 1)
        return round(max(0.0, min(1.0, 1.0 - 0.20 * (abs(word_count - w_target) / float(denom)))), 4)

    return round(max(0.0, min(1.0, 1.0 - 0.50 * ((word_count - w_max) / float(w_max)))), 4)


def _resolve_lane_word_bounds(lane: Any) -> tuple[int, Optional[int], int]:
    """Helper to parse lane word target and bounds."""
    words_min, words_max, words_target = 160, 340, 250
    if lane is None:
        return words_min, words_max, words_target

    if isinstance(lane, dict):
        words_dict = lane.get("words", {})
        words_min = words_dict.get("min", lane.get("words_min", 160))
        words_max = words_dict.get("max", lane.get("words_max", 340))
        dur_target = lane.get("duration", {}).get("target_sec", 150)
        words_target = max(words_min, int(dur_target * 1.6))
    elif hasattr(lane, "words_min"):
        words_min = getattr(lane, "words_min", 160)
        words_max = getattr(lane, "words_max", 340)
        dur_target = getattr(lane, "duration_target_sec", 150)
        words_target = (words_min + words_max) // 2 if words_max is not None else max(words_min, int(dur_target * 2.2))
    elif isinstance(lane, str):
        lane_str = lane.lower()
        if "long" in lane_str or "compilation" in lane_str:
            words_min, words_max, words_target = 2600, None, 3000
        elif "short" in lane_str:
            words_min, words_max, words_target = 160, 340, 250

    return words_min, words_max, words_target


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

    s_score = min(1.0, max(0.0, float(score)) / 500.0)
    s_ratio = max(0.0, min(1.0, float(upvote_ratio)))
    s_comments = min(1.0, max(0.0, float(num_comments)) / 100.0)

    if created_utc is not None and created_utc > 0:
        now_ts = time.time()
        delta_hours = max(0.0, (now_ts - float(created_utc)) / 3600.0)
        velocity = float(num_comments) / (delta_hours + 1.0)
        s_velocity = min(1.0, max(0.0, velocity / 20.0))
        engagement_score = 0.35 * s_ratio + 0.30 * s_score + 0.20 * s_comments + 0.15 * s_velocity
    else:
        engagement_score = 0.40 * s_ratio + 0.35 * s_score + 0.25 * s_comments

    engagement_score = round(max(0.0, min(1.0, engagement_score)), 4)
    hook_score, _, neg_penalties = detect_opening_hook_strength(clean_title, clean_content)

    words = re.findall(r"\b\w+\b", clean_content)
    words_min, words_max, words_target = _resolve_lane_word_bounds(lane)

    retention_length_score = evaluate_retention_length_score(
        word_count=len(words),
        words_min=words_min,
        words_max=words_max,
        words_target=words_target,
    )

    composite_heuristic_score = round(
        max(0.0, min(1.0, 0.35 * engagement_score + 0.30 * hook_score + 0.35 * retention_length_score)),
        4,
    )
    passed_stage1 = composite_heuristic_score >= min_heuristic_threshold

    reasons: list[str] = []
    if not passed_stage1:
        reasons.append("composite_heuristic_score_below_threshold")
    if retention_length_score < 0.30:
        reasons.append("insufficient_word_length_retention")
    if hook_score < 0.25:
        reasons.append("weak_opening_hook")
    if engagement_score < 0.15:
        reasons.append("low_engagement_metrics")
    reasons.extend(neg_penalties)

    return HeuristicScoreReport(
        engagement_score=engagement_score,
        retention_length_score=retention_length_score,
        hook_score=hook_score,
        composite_heuristic_score=composite_heuristic_score,
        passed_stage1=passed_stage1,
        rejection_reasons=tuple(reasons),
    )
