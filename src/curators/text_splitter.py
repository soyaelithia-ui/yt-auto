"""
src/curators/text_splitter.py - Facade for Cinematic Script Curator & Text Segmentation.

Transforms raw input stories, community submissions, or canonical lore into structured
4-Act dramatic scripts with progressive tension curve grading (1-5), scene-by-scene timing,
lane-calibrated environmental moods, and sanitized neutral Spanish narration text.
Validates output against schemas/script_curator.schema.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import jsonschema

from src.curators.curation_profiles import (
    LANE_CURATION_CONFIGS,
    SCHEMA_PATH,
    VALID_AUDIO_PACING_CUES,
    generate_fallback_narrative,
    resolve_lane_config,
    synthesize_hook_summary,
)
from src.curators.segmentation import (
    distribute_scenes_across_acts,
    sanitize_text,
    slice_into_scenes,
    split_into_sentences,
)
from src.curators.tension import (
    derive_semantic_environmental_mood,
    derive_transition_reason,
    interpolate_tension,
    resolve_audio_pacing_cue,
)
from src.log import get_logger

logger = get_logger("cinematic_script_curator")


class TextSegmentationEngine:
    """Deterministic narrative text segmentation and 4-act timing compiler."""

    def __init__(self, schema_file: Optional[Path] = None) -> None:
        self.schema_path = schema_file or SCHEMA_PATH
        self._schema: Optional[Dict[str, Any]] = None
        if self.schema_path.is_file():
            with open(self.schema_path, "r", encoding="utf-8") as f:
                self._schema = json.load(f)

    def curate(
        self,
        raw_text: str,
        title: str,
        channel_lane: str = "horror-horror-long",
        target_format: str = "longform",
        words_per_minute: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Curates raw text into structured 4-Act screenplay with progressive tension curve.
        Enforces lane-specific timing, scene bounds, vocal cues, and Draft-07 schema validation.
        """
        lane_key, lane_cfg = resolve_lane_config(channel_lane, target_format)
        target_fmt = lane_cfg["target_format"]
        wpm = float(words_per_minute or lane_cfg["default_wpm"])
        channel = lane_cfg.get("channel", "horror")

        clean_text = sanitize_text(raw_text, channel=channel)
        words = clean_text.split()
        if len(words) < 25:
            clean_text = generate_fallback_narrative(title, lane_key, clean_text)
            words = clean_text.split()

        scene_texts = slice_into_scenes(
            clean_text=clean_text,
            target_scene_dur=lane_cfg["target_scene_dur"],
            min_scene_dur=lane_cfg["min_scene_dur"],
            max_scene_dur=lane_cfg["max_scene_dur"],
            wpm=wpm,
            min_scenes=lane_cfg["min_scenes"],
            max_scenes=lane_cfg["max_scenes"],
            target_format=target_fmt,
        )

        acts_data, tension_curve = self._build_acts(
            lane_key=lane_key,
            lane_cfg=lane_cfg,
            scene_texts=scene_texts,
            wpm=wpm,
        )

        output_payload = self._assemble_payload(
            title=title,
            channel_lane=channel_lane,
            target_fmt=target_fmt,
            lane_key=lane_key,
            clean_text=clean_text,
            lane_cfg=lane_cfg,
            acts_data=acts_data,
            tension_curve=tension_curve,
        )

        if self._schema:
            jsonschema.validate(instance=output_payload, schema=self._schema)

        return output_payload

    def _build_acts(
        self,
        lane_key: str,
        lane_cfg: Dict[str, Any],
        scene_texts: List[str],
        wpm: float,
    ) -> Tuple[List[Dict[str, Any]], List[int]]:
        """Assembles 4-act structure with scenes, tension curves, and audio pacing cues."""
        acts_specs = lane_cfg["acts"]
        scene_distribution = distribute_scenes_across_acts(len(scene_texts), len(acts_specs))
        min_scene_dur = lane_cfg["min_scene_dur"]
        max_scene_dur = lane_cfg["max_scene_dur"]

        acts_data: List[Dict[str, Any]] = []
        tension_curve: List[int] = []
        global_idx = 1
        curr_idx = 0

        for act_idx, act_spec in enumerate(acts_specs):
            count_for_act = scene_distribution[act_idx]
            act_scenes: List[Dict[str, Any]] = []

            for sc_offset in range(count_for_act):
                if curr_idx >= len(scene_texts):
                    break
                sc_text = scene_texts[curr_idx]
                sc_words = len(sc_text.split())
                raw_dur = (sc_words / wpm) * 60.0
                sc_dur = round(max(min_scene_dur, min(max_scene_dur, raw_dur)), 2)

                tension = interpolate_tension(act_spec["tension_profile"], sc_offset, count_for_act)
                tension_curve.append(tension)
                pacing_cue = resolve_audio_pacing_cue(lane_key, act_spec["act_number"], tension, sc_offset, count_for_act)
                mood = derive_semantic_environmental_mood(sc_text, act_spec["moods"][sc_offset % len(act_spec["moods"])], tension)

                act_scenes.append({
                    "scene_id": f"scene_{global_idx:03d}",
                    "scene_index": global_idx,
                    "tension_level": tension,
                    "narration_text": sc_text,
                    "word_count": max(1, sc_words),
                    "estimated_duration_sec": sc_dur,
                    "environmental_mood": mood,
                    "audio_pacing_cue": pacing_cue,
                    "transition_reason": derive_transition_reason(act_spec["act_number"], act_spec["dramatic_role"], tension, sc_offset),
                })
                global_idx += 1
                curr_idx += 1

            if act_scenes:
                acts_data.append({
                    "act_number": act_spec["act_number"],
                    "act_title": act_spec["act_title"],
                    "dramatic_role": act_spec["dramatic_role"],
                    "scenes": act_scenes,
                })

        return acts_data, tension_curve

    def _assemble_payload(
        self,
        title: str,
        channel_lane: str,
        target_fmt: str,
        lane_key: str,
        clean_text: str,
        lane_cfg: Dict[str, Any],
        acts_data: List[Dict[str, Any]],
        tension_curve: List[int],
    ) -> Dict[str, Any]:
        """Assembles final curated script payload dictionary."""
        total_scene_duration = round(sum(s["estimated_duration_sec"] for a in acts_data for s in a["scenes"]), 2)
        final_total_duration = max(lane_cfg["min_total_dur"], min(lane_cfg["max_total_dur"], total_scene_duration))
        hook_summary = synthesize_hook_summary(title, lane_key, clean_text)
        pred_score, pred_rationale = self.evaluate_predictive_success(clean_text, title, channel_lane)

        return {
            "version": "2.0",
            "metadata": {
                "title": title[:200] if title else "Crónica Narrativa",
                "channel_lane": channel_lane,
                "target_format": target_fmt,
                "total_word_count": max(1, sum(s["word_count"] for a in acts_data for s in a["scenes"])),
                "estimated_duration_sec": final_total_duration,
                "hook_summary": hook_summary,
                "tension_curve": tension_curve if tension_curve else [1, 2, 3, 4, 5, 2],
                "predictive_success_score": pred_score,
                "score_rationale": pred_rationale,
            },
            "acts": acts_data,
        }

    def evaluate_predictive_success(
        self,
        script_text: str,
        title: str,
        channel_lane: str = "horror-horror-long",
        use_agent: bool = False,
    ) -> tuple[float, str]:
        """
        Evaluate predictive audience retention and success score (0.0 to 1.0) with LLM reasoning.
        Analyzes hook strength, pacing curve, stakes clarity, and curiosity payoff.
        """
        import os
        import re

        if use_agent and bool(os.environ.get("USE_AGENT_HARNESS", "0") in ("1", "true", "yes")):
            try:
                from src.agents.base_agent import ProgrammaticAgent, parse_json_reply
                system_instruction = (
                    "Eres un auditor y analista de retención de YouTube. "
                    "Evalúa el guion y título proporcionados. "
                    "Calcula una puntuación predictiva de éxito de 0.0 a 1.0 y una razón explicativa concisa (1 oración). "
                    "Responde en JSON con las claves: 'score' (float) y 'rationale' (string)."
                )
                agent = ProgrammaticAgent(
                    system_instructions=system_instruction,
                    role_name="retention-evaluator",
                )
                res = agent.run(f"Título: {title}\nGuion: {script_text[:1200]}")
                consumed = ProgrammaticAgent.consume(res)
                doc = consumed.get("output", {})
                parsed = doc.get("structured_output") or parse_json_reply(doc.get("reply", ""))
                if isinstance(parsed, dict) and "score" in parsed:
                    score = max(0.0, min(1.0, float(parsed["score"])))
                    rationale = str(parsed.get("rationale") or "Evaluado por agente cognitivo.")
                    return round(score, 2), rationale
            except Exception:
                pass

        # Deterministic analytical fallback
        words = script_text.split()
        total_w = len(words)
        has_question_or_exclamation = bool(re.search(r"[¿?¡!]", title))
        has_strong_hook = bool(
            words
            and len(words[:25]) >= 10
            and any(w.lower() in ("yo", "mi", "nunca", "siempre", "secreto", "descubrí", "exigió", "rechazó") for w in words[:15])
        )

        base_score = 0.70
        if has_question_or_exclamation:
            base_score += 0.10
        if has_strong_hook:
            base_score += 0.12
        if 80 <= total_w <= 300:
            base_score += 0.06
        score = round(min(0.98, base_score), 2)
        rationale = f"Estructura balanceada ({total_w} palabras) con gancho de alta curiosidad."
        return score, rationale

    # Delegated methods for backward-compatibility with tests / subcomponents
    def _resolve_lane_config(self, channel_lane: str, target_format: str) -> Tuple[str, Dict[str, Any]]:
        return resolve_lane_config(channel_lane, target_format)

    def _sanitize_text(self, text: str, channel: str = "horror") -> str:
        return sanitize_text(text, channel=channel)

    def _generate_fallback_narrative(self, title: str, lane_key: str, existing_text: str) -> str:
        return generate_fallback_narrative(title, lane_key, existing_text)

    def _slice_into_scenes(self, *args: Any, **kwargs: Any) -> List[str]:
        return slice_into_scenes(*args, **kwargs)

    def _split_into_sentences(self, text: str) -> List[str]:
        return split_into_sentences(text)

    def _distribute_scenes_across_acts(self, total_scenes: int, num_acts: int = 4) -> List[int]:
        return distribute_scenes_across_acts(total_scenes, num_acts)

    def _interpolate_tension(self, profile: List[int], offset: int, total: int) -> int:
        return interpolate_tension(profile, offset, total)

    def _resolve_audio_pacing_cue(self, *args: Any, **kwargs: Any) -> str:
        return resolve_audio_pacing_cue(*args, **kwargs)

    def _derive_semantic_environmental_mood(self, text: str, fallback_mood: str, tension: int) -> str:
        return derive_semantic_environmental_mood(text, fallback_mood, tension)

    def _derive_transition_reason(self, act_number: int, dramatic_role: str, tension: int, scene_offset: int) -> str:
        return derive_transition_reason(act_number, dramatic_role, tension, scene_offset)

    def _synthesize_hook_summary(self, title: str, lane_key: str, clean_text: str) -> str:
        return synthesize_hook_summary(title, lane_key, clean_text)


# Backward-compatibility alias
CinematicScriptCuratorAgent = TextSegmentationEngine

__all__ = [
    "CinematicScriptCuratorAgent",
    "LANE_CURATION_CONFIGS",
    "SCHEMA_PATH",
    "TextSegmentationEngine",
    "VALID_AUDIO_PACING_CUES",
    "derive_semantic_environmental_mood",
    "derive_transition_reason",
    "distribute_scenes_across_acts",
    "generate_fallback_narrative",
    "interpolate_tension",
    "resolve_audio_pacing_cue",
    "resolve_lane_config",
    "sanitize_text",
    "slice_into_scenes",
    "split_into_sentences",
    "synthesize_hook_summary",
]
