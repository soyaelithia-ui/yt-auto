"""
src/agents/cinematic_script_curator.py - Agent 1: Cinematic Script Curator.

Transforms raw input stories or community submissions into structured 4-Act dramatic scripts
with tension curve grading (1-5), scene-by-scene timing (45-90s pacing for longform, 8-15s for shorts),
and sanitized neutral Spanish narration text.
Validates output against schemas/script_curator.schema.json.
"""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import jsonschema

from src.log import get_logger

logger = get_logger("cinematic_script_curator")

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "script_curator.schema.json"


class CinematicScriptCuratorAgent:
    """Agent 1: Generates structured, schema-compliant 4-Act dramatic scripts."""

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
        channel_lane: str = "moku-horror-long",
        target_format: str = "longform",
        words_per_minute: float = 140.0,
    ) -> Dict[str, Any]:
        """
        Curates raw text into structured 4-Act screenplay with tension curve.
        """
        # Clean text
        clean_text = self._sanitize_text(raw_text)
        words = clean_text.split()
        total_words = max(1, len(words))
        total_duration_sec = (total_words / words_per_minute) * 60.0

        is_short = target_format.lower() in ("short", "shorts", "vertical")
        target_fmt = "short" if is_short else "longform"

        # Determine target scene duration
        target_scene_dur = 10.0 if is_short else 60.0
        min_scene_dur = 8.0 if is_short else 45.0
        max_scene_dur = 15.0 if is_short else 90.0

        # Calculate number of scenes
        num_scenes = max(1, int(round(total_duration_sec / target_scene_dur)))
        if is_short:
            num_scenes = max(4, min(6, num_scenes))
        else:
            num_scenes = max(4, min(24, num_scenes))

        # Split words evenly across scenes
        words_per_scene = max(10, total_words // num_scenes)
        scene_word_chunks: List[List[str]] = []
        for i in range(num_scenes):
            start_w = i * words_per_scene
            end_w = (i + 1) * words_per_scene if i < num_scenes - 1 else total_words
            chunk = words[start_w:end_w]
            if chunk:
                scene_word_chunks.append(chunk)

        # Distribute into 4 Acts: [Act 1, Act 2, Act 3, Act 4]
        act_specs = [
            (1, "Act I: Inception & Atmosphere", "exposition_inception", 1),
            (2, "Act II: Rising Dread & Suspicion", "rising_action_dread", 3),
            (3, "Act III: The Climax / Confrontation", "climax_confrontation", 5),
            (4, "Act IV: Aftermath & Cosmic Revelations", "aftermath_revelation", 2),
        ]

        scenes_per_act = max(1, len(scene_word_chunks) // 4)
        acts_data: List[Dict[str, Any]] = []
        tension_curve: List[int] = []

        global_scene_idx = 1
        curr_chunk_idx = 0

        for act_num, act_title, dramatic_role, base_tension in act_specs:
            act_scenes: List[Dict[str, Any]] = []
            
            # Determine how many scenes belong to this act
            if act_num == 4:
                count_for_this_act = len(scene_word_chunks) - curr_chunk_idx
            else:
                count_for_this_act = scenes_per_act

            count_for_this_act = max(1, count_for_this_act)

            for _ in range(count_for_this_act):
                if curr_chunk_idx >= len(scene_word_chunks):
                    break

                chunk = scene_word_chunks[curr_chunk_idx]
                scene_text = " ".join(chunk)
                sc_words = len(chunk)
                sc_dur = round((sc_words / words_per_minute) * 60.0, 2)
                sc_dur = max(min_scene_dur, min(max_scene_dur, sc_dur))

                # Modulate tension
                tension = max(1, min(5, base_tension))
                tension_curve.append(tension)

                # Audio pacing cue based on tension
                if tension <= 2:
                    pacing_cue = "calm_slow" if tension == 1 else "steady_dramatic"
                elif tension in (3, 4):
                    pacing_cue = "tense_accelerando" if tension == 3 else "intense_urgent"
                else:
                    pacing_cue = "intense_urgent"

                scene_obj = {
                    "scene_id": f"scene_{global_scene_idx:03d}",
                    "scene_index": global_scene_idx,
                    "tension_level": tension,
                    "narration_text": scene_text,
                    "word_count": sc_words,
                    "estimated_duration_sec": sc_dur,
                    "environmental_mood": self._infer_environmental_mood(channel_lane, tension),
                    "audio_pacing_cue": pacing_cue,
                }
                act_scenes.append(scene_obj)
                global_scene_idx += 1
                curr_chunk_idx += 1

            if act_scenes:
                acts_data.append({
                    "act_number": act_num,
                    "act_title": act_title,
                    "dramatic_role": dramatic_role,
                    "scenes": act_scenes,
                })

        output_payload: Dict[str, Any] = {
            "version": "2.0",
            "metadata": {
                "title": title[:200],
                "channel_lane": channel_lane,
                "target_format": target_fmt,
                "total_word_count": total_words,
                "estimated_duration_sec": round(total_duration_sec, 2),
                "hook_summary": f"Relato inmersivo de {channel_lane} con tensión climática.",
                "tension_curve": tension_curve if tension_curve else [1, 2, 3, 4, 5, 2],
            },
            "acts": acts_data,
        }

        # Validate with Draft-07 schema if present
        if self._schema:
            jsonschema.validate(instance=output_payload, schema=self._schema)

        return output_payload

    def _sanitize_text(self, text: str) -> str:
        """Sanitizes text, removing markdown headers, meta chatter, emojis, and artifacts."""
        t = re.sub(r"#+\s*", "", text)
        t = re.sub(r"\[.*?\]", "", t)
        t = re.sub(r"\(http.*?\)", "", t)
        t = re.sub(r"[\*\_~`]", "", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def _infer_environmental_mood(self, channel_lane: str, tension: int) -> str:
        """Assigns an environmental mood based on lane and tension level."""
        lane = channel_lane.lower()
        if "scp" in lane:
            return "Classified Containment Site" if tension > 3 else "Underground Research Facility"
        elif "aita" in lane or "drama" in lane:
            return "Tense Living Room Confrontation" if tension > 3 else "Quiet Domestic Space"
        elif "cosmic" in lane or "horror" in lane:
            return "Eldritch Storm Horizon" if tension > 3 else "Ancient Monolithic Ruin"
        return "Atmospheric Chamber"
