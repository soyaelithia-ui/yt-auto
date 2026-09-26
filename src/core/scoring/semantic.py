"""
src/core/scoring/semantic.py - Stage 2 Semantic / Viral Potential Evaluation.

Provides LLM-as-judge prompt synthesis, response parsing, and deterministic offline
fallback analyzer evaluating dramatic potential, viewer retention, and channel tone alignment.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Optional

from src.core.scoring.heuristics import _strip_accents, detect_opening_hook_strength
from src.core.scoring.models import DEFAULT_SEMANTIC_THRESHOLD, SemanticScoreReport

try:
    from src.log import get_logger
    logger = get_logger("scoring.semantic")
except ImportError:
    logger = logging.getLogger("scoring.semantic")

_CONFLICT_PATTERNS = (
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
)

_ESCALATION_PATTERNS = (
    r"\bde repente\b", r"\bde pronto\b", r"\ben ese momento\b",
    r"\bentonces\b", r"\bfinalmente\b", r"\bal d[íi]a siguiente\b",
    r"\blas cosas empeoraron\b", r"\btodo cambi[óo]\b", r"\ba partir de ah[íi]\b",
    r"\bsuddenly\b", r"\bwithout warning\b",
)

_CURIOSITY_PATTERNS = (
    r"\bno van a creer\b", r"\blo que pas[óo] despu[ée]s\b", r"\bno esperaba\b",
    r"\bhasta que vi\b", r"\bla raz[óo]n por la que\b", r"\blo peor fue\b",
    r"\bnadie sab[íi]a\b", r"\bsecreto\b", r"\bdescubr[íi]\b",
    r"\blo que encontr[ée]\b", r"\bwhat happened next\b", r"\bnever expected\b",
)

_TWIST_PATTERNS = (
    r"\bresult[óo] que\b", r"\bresulta que\b", r"\bla verdad era\b",
    r"\ben realidad\b", r"\bpara mi sorpresa\b", r"\bnunca me imagin[ée]\b",
    r"\bplot twist\b", r"\bresult[óo] ser\b", r"\bdescubrimos que\b",
    r"\bresult[óo] estar\b", r"\bit turned out\b", r"\bthe truth was\b",
    r"\bto my surprise\b", r"\bdescubr[íi] que\b", r"\btraici[óo]n\b",
    r"\benga[ñn]o\b", r"\bsecreto\b",
)

_IRONY_PATTERNS = (
    r"\bir[óo]nicamente\b", r"\bal contrario\b", r"\btodo lo contrario\b",
    r"\bno era quien dec[íi]a\b", r"\benga[ñn]ad[oa]\b", r"\bmentira\b",
    r"\bfals[oa]\b", r"\btrampa\b",
)

_HORROR_PATTERNS = (
    r"\bscp\b", r"\banomal[íi]a\b", r"\bcontenci[óo]n\b", r"\bentidad\b",
    r"\bobjeto\b", r"\bsujeto\b", r"\bclase\b", r"\beuclid\b", r"\bketer\b",
    r"\bmonstruo\b", r"\bcriatura\b", r"\bsombra\b", r"\bbosque\b",
    r"\bb[úu]nker\b", r"\bpesadilla\b", r"\bmiedo\b", r"\baterrador\b",
    r"\bsiniestr[oa]\b", r"\bcad[áa]ver\b", r"\bsangre\b", r"\bgrito\b",
    r"\bdemonio\b", r"\bfantasma\b", r"\bparanormal\b", r"\boscur[oa]\b",
    r"\bnoche\b", r"\bcreepypasta\b",
)

_DRAMA_PATTERNS = (
    r"\bfamilia\b", r"\bespos[oa]\b", r"\bnovi[oa]\b", r"\bherman[oa]\b",
    r"\bmadre\b", r"\bpadre\b", r"\bsuegr[oa]\b", r"\bboda\b",
    r"\bherencia\b", r"\bdinero\b", r"\bdivorcio\b", r"\binfidelidad\b",
    r"\benga[ñn]o\b", r"\bamig[oa]\b", r"\btrabajo\b", r"\bjefe\b",
    r"\bmoral\b", r"\bculpa\b", r"\bmal[oa]\b", r"\baita\b",
    r"\bopinan\b", r"\bconsejo\b", r"\bdiscusi[óo]n\b", r"\bexigi[óo]\b",
    r"\bdeuda\b", r"\btraici[óo]n\b",
)


def _calculate_semantic_subscores(
    normalized: str,
    full_text: str,
    clean_title: str,
    clean_content: str,
    channel_lane: str,
) -> tuple[float, float, float, float, list[str]]:
    """Calculate dramatic, retention, twist, and tone dimensions."""
    detected_hooks: list[str] = []

    # Dramatic Potential (1.0 - 10.0)
    conflict_matches = sum(1 for pat in _CONFLICT_PATTERNS if re.search(pat, normalized))
    d_score = 5.0 + min(4.0, 0.60 * conflict_matches)
    if conflict_matches >= 3:
        detected_hooks.append("high_conflict_stakes")

    escalation_matches = sum(1 for pat in _ESCALATION_PATTERNS if re.search(pat, normalized))
    d_score += min(2.0, 0.60 * escalation_matches)
    if escalation_matches >= 1:
        detected_hooks.append("escalating_narrative_pacing")

    if re.search(r'["«“—]', full_text):
        d_score += 0.5
        detected_hooks.append("active_dialogue")
    dramatic_potential = round(max(1.0, min(10.0, d_score)), 2)

    # Viewer Retention (1.0 - 10.0)
    curiosity_matches = sum(1 for pat in _CURIOSITY_PATTERNS if re.search(pat, normalized))
    r_score = 5.0 + min(2.5, 0.60 * curiosity_matches)
    if curiosity_matches >= 2:
        detected_hooks.append("curiosity_gap_retention")

    hook_val, _, _ = detect_opening_hook_strength(clean_title, clean_content)
    if hook_val >= 0.80:
        r_score += 1.5
        detected_hooks.append("strong_opening_hook")
    elif hook_val >= 0.50:
        r_score += 0.5
    elif hook_val < 0.20:
        r_score -= 1.5

    paragraphs = [p for p in clean_content.split("\n\n") if p.strip()]
    if len(paragraphs) >= 3:
        r_score += 0.5
    viewer_retention = round(max(1.0, min(10.0, r_score)), 2)

    # Surprise / Twist Factor (1.0 - 10.0)
    twist_matches = sum(1 for pat in _TWIST_PATTERNS if re.search(pat, normalized))
    t_score = 4.5 + min(3.5, 0.85 * twist_matches)
    if twist_matches >= 1:
        detected_hooks.append("twist_revelation")

    if any(re.search(pat, normalized) for pat in _IRONY_PATTERNS):
        t_score += 0.5
    surprise_factor = round(max(1.0, min(10.0, t_score)), 2)

    # Tone & Channel Alignment (1.0 - 10.0)
    lane_lower = channel_lane.lower()
    if any(k in lane_lower for k in ("horror", "scp", "terror")):
        horror_matches = sum(1 for pat in _HORROR_PATTERNS if re.search(pat, normalized))
        a_score = 5.5 + min(4.5, 0.55 * horror_matches)
        if horror_matches >= 2:
            detected_hooks.append("horror_atmospheric_alignment")
    elif any(k in lane_lower for k in ("aita", "drama", "moral", "relaciones")):
        drama_matches = sum(1 for pat in _DRAMA_PATTERNS if re.search(pat, normalized))
        a_score = 5.5 + min(4.5, 0.55 * drama_matches)
        if drama_matches >= 2:
            detected_hooks.append("moral_drama_alignment")
    else:
        a_score = 7.5
    tone_alignment = round(max(1.0, min(10.0, a_score)), 2)

    return dramatic_potential, viewer_retention, surprise_factor, tone_alignment, detected_hooks


def _evaluate_semantic_deterministically(
    title: str,
    content: str,
    channel_lane: str = "horror-horror-long",
    target_format: str = "longform",
    min_semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
) -> SemanticScoreReport:
    """Genuine, deterministic offline heuristic calculation of semantic viral dimensions."""
    clean_title = (title or "").strip()
    clean_content = (content or "").strip()
    full_text = f"{clean_title}\n\n{clean_content}"
    normalized = _strip_accents(full_text.lower())
    rejection_reasons: list[str] = []

    (
        dramatic_potential,
        viewer_retention,
        surprise_factor,
        tone_alignment,
        detected_hooks,
    ) = _calculate_semantic_subscores(
        normalized, full_text, clean_title, clean_content, channel_lane
    )


    raw_semantic = (
        0.30 * dramatic_potential
        + 0.35 * viewer_retention
        + 0.20 * surprise_factor
        + 0.15 * tone_alignment
    ) / 10.0
    overall_semantic_score = round(max(0.0, min(1.0, raw_semantic)), 4)
    verdict = "ACCEPTED" if overall_semantic_score >= min_semantic_threshold else "REJECTED"

    hook_quality = (
        "excellent" if overall_semantic_score >= 0.85
        else "strong" if overall_semantic_score >= 0.70
        else "acceptable" if overall_semantic_score >= 0.50
        else "poor"
    )

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
    first_brace, last_brace = cleaned.find("{"), cleaned.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            data = json.loads(cleaned[first_brace : last_brace + 1])
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return None


def _build_semantic_eval_prompt(channel_lane: str, target_format: str, title: str, content: str) -> str:
    """Standardized prompt template for LLM semantic scoring."""
    return (
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


def _build_semantic_report_from_llm(parsed: dict[str, Any], min_semantic_threshold: float) -> SemanticScoreReport:
    """Builds SemanticScoreReport from parsed LLM dictionary."""
    d = float(parsed.get("dramatic_potential", 5.0))
    r = float(parsed.get("viewer_retention", 5.0))
    t = float(parsed.get("surprise_factor", 5.0))
    a = float(parsed.get("tone_alignment", 5.0))
    raw_s = (0.30 * d + 0.35 * r + 0.20 * t + 0.15 * a) / 10.0
    overall = round(max(0.0, min(1.0, raw_s)), 4)
    verdict = "ACCEPTED" if overall >= min_semantic_threshold else "REJECTED"
    return SemanticScoreReport(
        dramatic_potential=round(d, 2),
        viewer_retention=round(r, 2),
        surprise_factor=round(t, 2),
        tone_alignment=round(a, 2),
        overall_semantic_score=overall,
        verdict=verdict,
        hook_quality=str(parsed.get("hook_quality", "acceptable")),
        rejection_reasons=tuple(str(x) for x in parsed.get("rejection_reasons", [])),
        detected_viral_hooks=tuple(str(x) for x in parsed.get("key_strengths", [])),
    )


def evaluate_semantic_viral_potential(
    title: str,
    content: str,
    channel_lane: str = "horror-horror-long",
    target_format: str = "longform",
    client: Optional[Any] = None,
    min_semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
) -> SemanticScoreReport:
    """Stage 2 Semantic & Viral Evaluation (LLM-as-judge with deterministic offline fallback)."""
    if client is not None:
        try:
            prompt = _build_semantic_eval_prompt(channel_lane, target_format, title, content)
            raw_result = None
            if hasattr(client, "generate_content"):
                res = client.generate_content(prompt)
                raw_result = getattr(res, "text", str(res))
            elif hasattr(client, "create"):
                res = client.create(messages=[{"role": "user", "content": prompt}])
                raw_result = str(res)
            elif callable(client):
                raw_result = str(client(prompt))

            if raw_result:
                parsed = _parse_llm_json_response(raw_result)
                if parsed and "dramatic_potential" in parsed:
                    return _build_semantic_report_from_llm(parsed, min_semantic_threshold)
        except Exception as e:
            logger.warning("LLM semantic evaluation failed (%s), falling back to deterministic analyzer.", e)

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
    channel_lane: str = "horror-horror-long",
    target_format: str = "longform",
    client: Optional[Any] = None,
    min_semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
) -> SemanticScoreReport:
    """Async wrapper for Stage 2 Semantic & Viral Evaluation."""
    if client is not None and asyncio.iscoroutinefunction(getattr(client, "generate_content", None)):
        try:
            prompt = _build_semantic_eval_prompt(channel_lane, target_format, title, content)
            res = await client.generate_content(prompt)
            raw_result = getattr(res, "text", str(res))
            if raw_result:
                parsed = _parse_llm_json_response(raw_result)
                if parsed and "dramatic_potential" in parsed:
                    return _build_semantic_report_from_llm(parsed, min_semantic_threshold)
        except Exception as e:
            logger.warning("Async LLM evaluation error (%s), falling back to deterministic analyzer.", e)

    return evaluate_semantic_viral_potential(
        title=title,
        content=content,
        channel_lane=channel_lane,
        target_format=target_format,
        client=client,
        min_semantic_threshold=min_semantic_threshold,
    )
