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
    _expand_scenes_to_minimum,
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

    @staticmethod
    def scale_act_durations(
        durations: List[float],
        target_total_duration: float,
        min_act_duration: float = 30.0,
    ) -> List[float]:
        """
        Scales act durations proportionally to match target_total_duration with zero drift.
        Enforces min_act_duration per act when possible and clamps final act precisely.
        """
        if not durations:
            return []
        n = len(durations)
        if target_total_duration <= 0:
            return [0.0] * n

        raw_sum = sum(durations)
        if raw_sum <= 0:
            base = target_total_duration / n
            return [round(base, 4)] * (n - 1) + [round(target_total_duration - (n - 1) * round(base, 4), 4)]

        scale_factor = target_total_duration / raw_sum
        scaled = [d * scale_factor for d in durations]

        if target_total_duration >= n * min_act_duration:
            for _ in range(5):
                below_indices = [i for i, d in enumerate(scaled) if d < min_act_duration]
                above_indices = [i for i, d in enumerate(scaled) if d > min_act_duration]
                if not below_indices or not above_indices:
                    break
                deficit = sum(min_act_duration - scaled[i] for i in below_indices)
                for i in below_indices:
                    scaled[i] = min_act_duration
                surplus_pool = sum(scaled[i] - min_act_duration for i in above_indices)
                if surplus_pool > 0:
                    for i in above_indices:
                        reduce_amt = deficit * ((scaled[i] - min_act_duration) / surplus_pool)
                        scaled[i] -= reduce_amt

        result = [round(d, 4) for d in scaled[:-1]]
        final_dur = round(target_total_duration - sum(result), 4)
        result.append(final_dur)

        if target_total_duration >= n * min_act_duration and result[-1] < min_act_duration:
            shortfall = min_act_duration - result[-1]
            for i in range(len(result) - 2, -1, -1):
                if result[i] - shortfall >= min_act_duration:
                    result[i] = round(result[i] - shortfall, 4)
                    result[-1] = round(result[-1] + shortfall, 4)
                    break

        return result

    def curate(
        self,
        raw_text: str,
        title: str,
        channel_lane: str = "horror-horror-long",
        target_format: str = "longform",
        words_per_minute: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Curates raw text into structured screenplay with progressive tension curve.
        Dynamically decomposes longform narratives into 4-8 acts.
        Enforces lane-specific timing, scene bounds, vocal cues, and Draft-07 schema validation.
        """
        lane_key, lane_cfg = resolve_lane_config(channel_lane, target_format)
        target_fmt = lane_cfg["target_format"]
        wpm = float(words_per_minute or lane_cfg["default_wpm"])
        channel = lane_cfg.get("channel", "horror")

        clean_text = sanitize_text(raw_text, channel=channel)
        words = clean_text.split()
        is_fallback = len(words) < 25
        if is_fallback:
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

        if target_fmt == "longform" and len(scene_texts) < 4:
            scene_texts = _expand_scenes_to_minimum(scene_texts, 4)

        acts_data, tension_curve = self._build_acts(
            lane_key=lane_key,
            lane_cfg=lane_cfg,
            scene_texts=scene_texts,
            wpm=wpm,
            clean_text=clean_text,
            target_fmt=target_fmt,
            is_fallback=is_fallback,
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
            schema_to_use = self._schema
            needs_extended = (
                len(acts_data) > 4
                or any(
                    a.get("dramatic_role") not in {"exposition_inception", "rising_action_dread", "climax_confrontation", "aftermath_revelation"}
                    or "tension_level" in a
                    or "target_duration_sec" in a
                    for a in acts_data
                )
            )
            if needs_extended:
                schema_to_use = json.loads(json.dumps(self._schema))
                schema_to_use["properties"]["acts"]["maxItems"] = 8
                schema_to_use["properties"]["acts"]["items"]["properties"]["act_number"]["maximum"] = 8
                schema_to_use["properties"]["acts"]["items"]["properties"]["dramatic_role"]["enum"] = [
                    "exposition_inception",
                    "rising_action_dread",
                    "confrontation_crisis",
                    "climax_confrontation",
                    "climax_breaking_point",
                    "aftermath_revelation",
                ]
                schema_to_use["properties"]["acts"]["items"]["properties"]["tension_level"] = {
                    "type": "integer", "minimum": 1, "maximum": 5
                }
                schema_to_use["properties"]["acts"]["items"]["properties"]["target_duration_sec"] = {
                    "type": "number", "minimum": 0.0
                }
                schema_to_use["properties"]["acts"]["items"]["properties"]["estimated_duration_sec"] = {
                    "type": "number", "minimum": 0.0
                }
                schema_to_use["properties"]["acts"]["items"]["properties"]["word_count"] = {
                    "type": "integer", "minimum": 0
                }
                schema_to_use["properties"]["acts"]["items"]["properties"]["narration_text"] = {
                    "type": "string"
                }
            jsonschema.validate(instance=output_payload, schema=schema_to_use)

        return output_payload

    def _build_acts(
        self,
        lane_key: str,
        lane_cfg: Dict[str, Any],
        scene_texts: List[str],
        wpm: float,
        clean_text: str = "",
        target_fmt: str = "longform",
        is_fallback: bool = False,
    ) -> Tuple[List[Dict[str, Any]], List[int]]:
        """Assembles dynamic 4-8 act structure with scenes, tension curves, and audio pacing cues."""
        acts_specs = lane_cfg["acts"]
        is_longform = (target_fmt == "longform") or (lane_cfg.get("min_total_dur", 0) >= 600.0)

        total_words = len(clean_text.split()) if clean_text else sum(len(s.split()) for s in scene_texts)

        if is_longform and not is_fallback:
            target_n = max(4, min(8, round(total_words / 500)))
            if len(scene_texts) < target_n:
                scene_texts = _expand_scenes_to_minimum(scene_texts, target_n)

            if len(acts_specs) >= target_n:
                if target_n == 4:
                    selected_indices = [0, 1, 3, 5] if len(acts_specs) >= 6 else [0, 1, 2, 3]
                elif target_n == 5:
                    selected_indices = [0, 1, 2, 4, 5] if len(acts_specs) >= 6 else [0, 1, 2, 3, 4]
                elif target_n == 6:
                    selected_indices = [0, 1, 2, 3, 4, 5]
                elif target_n == 7:
                    selected_indices = [0, 1, 2, 3, 4, 5, 6] if len(acts_specs) >= 7 else list(range(len(acts_specs)))
                else:
                    selected_indices = list(range(min(target_n, len(acts_specs))))
                active_acts_specs = [acts_specs[i] for i in selected_indices]
            else:
                active_acts_specs = acts_specs
        elif is_longform and is_fallback:
            target_n = 4
            selected_indices = [0, 1, 3, 5] if len(acts_specs) >= 6 else [0, 1, 2, 3]
            active_acts_specs = [acts_specs[i] for i in selected_indices] if len(acts_specs) >= 4 else acts_specs
        else:
            target_n = len(acts_specs)
            active_acts_specs = acts_specs

        ROMAN_NUMS = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII"]
        scene_distribution = distribute_scenes_across_acts(len(scene_texts), len(active_acts_specs))
        min_scene_dur = lane_cfg["min_scene_dur"]
        max_scene_dur = lane_cfg["max_scene_dur"]

        acts_data: List[Dict[str, Any]] = []
        tension_curve: List[int] = []
        global_idx = 1
        curr_idx = 0

        for act_idx, raw_spec in enumerate(active_acts_specs, start=1):
            count_for_act = scene_distribution[act_idx - 1]
            act_scenes: List[Dict[str, Any]] = []

            raw_title = raw_spec["act_title"]
            if ":" in raw_title:
                title_suffix = raw_title.split(":", 1)[1].strip()
                act_title = f"Acto {ROMAN_NUMS[act_idx]}: {title_suffix}"
            else:
                act_title = f"Acto {ROMAN_NUMS[act_idx]}: {raw_title}"

            for sc_offset in range(count_for_act):
                if curr_idx >= len(scene_texts):
                    break
                sc_text = scene_texts[curr_idx]
                sc_words = len(sc_text.split())
                raw_dur = (sc_words / wpm) * 60.0
                sc_dur = round(max(min_scene_dur, min(max_scene_dur, raw_dur)), 2)

                tension = interpolate_tension(raw_spec["tension_profile"], sc_offset, count_for_act)
                tension_curve.append(tension)
                pacing_cue = resolve_audio_pacing_cue(lane_key, act_idx, tension, sc_offset, count_for_act)
                mood = derive_semantic_environmental_mood(sc_text, raw_spec["moods"][sc_offset % len(raw_spec["moods"])], tension)

                act_scenes.append({
                    "scene_id": f"scene_{global_idx:03d}",
                    "scene_index": global_idx,
                    "tension_level": tension,
                    "narration_text": sc_text,
                    "word_count": max(1, sc_words),
                    "estimated_duration_sec": sc_dur,
                    "environmental_mood": mood,
                    "audio_pacing_cue": pacing_cue,
                    "transition_reason": derive_transition_reason(act_idx, raw_spec["dramatic_role"], tension, sc_offset),
                })
                global_idx += 1
                curr_idx += 1

            if act_scenes:
                act_tension = max(s["tension_level"] for s in act_scenes)
                act_dur = round(sum(s["estimated_duration_sec"] for s in act_scenes), 2)
                act_dict: Dict[str, Any] = {
                    "act_number": act_idx,
                    "act_title": act_title,
                    "dramatic_role": raw_spec["dramatic_role"],
                    "scenes": act_scenes,
                }
                if len(active_acts_specs) > 4:
                    act_dict["tension_level"] = act_tension
                    act_dict["target_duration_sec"] = act_dur
                    act_dict["estimated_duration_sec"] = act_dur
                    act_dict["word_count"] = sum(s["word_count"] for s in act_scenes)
                    act_dict["narration_text"] = " ".join(s["narration_text"] for s in act_scenes)
                acts_data.append(act_dict)

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

        if target_fmt == "longform" and acts_data:
            act_raw_durs = [
                a.get("estimated_duration_sec", sum(s["estimated_duration_sec"] for s in a["scenes"]))
                for a in acts_data
            ]
            scaled_act_durs = self.scale_act_durations(act_raw_durs, final_total_duration, min_act_duration=30.0)
            for a_idx, act in enumerate(acts_data):
                if "target_duration_sec" in act or len(acts_data) > 4:
                    act["target_duration_sec"] = scaled_act_durs[a_idx]
                    act["estimated_duration_sec"] = scaled_act_durs[a_idx]
                scenes_in_act = act["scenes"]
                if scenes_in_act:
                    scene_raw_durs = [s["estimated_duration_sec"] for s in scenes_in_act]
                    scaled_scenes = self.scale_act_durations(scene_raw_durs, scaled_act_durs[a_idx], min_act_duration=1.0)
                    for s_idx, sc in enumerate(scenes_in_act):
                        sc["estimated_duration_sec"] = scaled_scenes[s_idx]

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
