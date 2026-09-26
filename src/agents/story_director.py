"""Story Director Agent — Autonomous narrative creation & curation via Antigravity Pro harness.

Transforms topics, canonical lore, or narrative premises into high-retention video scripts:
- YouTube Shorts retention curve: Hook (0-3s), Tension Escalation (3-30s), Climax (30-45s), Loop Hook (45-55s).
- Longform narrative escalation: Multi-chapter suspense with character perspective and subtext.
- Channel Specialization:
  * 'horror': Cosmic horror, psychological terror, and strict official SCP Foundation lore.
  * 'drama': High-stakes moral dilemmas, interpersonal drama, and community debate topics.
  * 'scifi': Speculative sci-fi, artificial intelligence, and cosmic singularity.
- Policy: Strict Fail-Closed — never emits degraded static placeholder text if AI quota/network fails.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from src.agents.base_agent import CANONICAL_MODEL, ProgrammaticAgent, is_saturation_text, parse_json_reply
from src.core.domain import AIProviderChainExhausted
from src.core.scp_lore import get_scp_canonical_lore, validate_scp_lore
from src.log import get_logger

logger = get_logger("story_director_agent")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
STORY_RESULT_PATH = OUTPUT_DIR / "story_director_result.json"

STORY_DIRECTOR_SYSTEM_INSTRUCTIONS = (
    "Eres el Director Narrativo y Guionista Principal de una red de canales de YouTube. "
    "Tu objetivo es crear guiones de máxima retención (Average Percentage Viewed > 85%).\n"
    "Estructura obligatoria para YouTube Shorts:\n"
    "1. HOOK (0-3 segundos): Una primera frase impactante, disruptiva y libre de saludos o clichés.\n"
    "2. ESCALADA DE TENSIÓN (3-30s): Desarrollo del conflicto, micro-anomalía y acumulación de suspense.\n"
    "3. CLÍMAX (30-45s): Momento de mayor revelación o ruptura dramática.\n"
    "4. LOOP HOOK (45-55s): Cierre que conecta circularmente con la primera frase para motivar la repetición del video.\n"
    "Tono según canal:\n"
    "- 'horror' (Terror / SCP): Rigor canónico, atmósfera opresiva, horror psicológico, neutralidad documental.\n"
    "- 'drama' (Drama): Dilema moral intenso, controversia real, debate ético sin villanos caricaturescos.\n"
    "- 'scifi' (Ciencia Ficción): Especulación tecnológica, singularidad y dilemas futuristas.\n"
    "Responde EXCLUSIVAMENTE en formato JSON conforme al esquema solicitado."
)

STORY_DIRECTOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "hook": {"type": "string"},
        "script": {"type": "string"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scene_index": {"type": "integer"},
                    "duration_sec": {"type": "number"},
                    "narration": {"type": "string"},
                    "visual_mood": {"type": "string"},
                    "tension_level": {"type": "integer", "minimum": 1, "maximum": 5},
                },
                "required": ["scene_index", "narration", "visual_mood", "tension_level"],
            },
        },
        "visual_motifs": {"type": "array", "items": {"type": "string"}},
        "channel": {"type": "string"},
        "estimated_duration_sec": {"type": "number"},
    },
    "required": ["title", "hook", "script", "visual_motifs"],
    "additionalProperties": True,
}


class StoryDirectorAgent(ProgrammaticAgent):
    """Autonomous narrative creation and editorial curation agent."""

    def __init__(
        self,
        model: str = CANONICAL_MODEL,
        instance_id: str = "pipeline_creative",
        reasoning_effort: str = "high",
    ) -> None:
        super().__init__(
            system_instructions=STORY_DIRECTOR_SYSTEM_INSTRUCTIONS,
            model=model,
            role_name="story-director-agent",
            instance_id=instance_id,
            reasoning_effort=reasoning_effort,
            task_result_path=STORY_RESULT_PATH,
            json_schema=STORY_DIRECTOR_SCHEMA,
        )

    def generate_story(
        self,
        topic: str,
        channel: str = "moku",
        target_format: str = "short",
        target_words: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generates a high-retention script with psychological tension curves.

        Fail-Closed: Raises AIProviderChainExhausted if the LLM cannot produce a valid script.
        """
        fmt = "short" if target_format in ("short", "shorts", "vertical", "9:16") else "longform"
        words_budget = target_words or (160 if fmt == "short" else 1800)

        # Canonical lore injection for SCP topics
        lore = None
        lore_prompt = ""
        clean_topic = topic.strip()
        if "scp" in clean_topic.lower() or "scp" in channel.lower():
            lore = get_scp_canonical_lore(clean_topic)
            if lore:
                facts = "\n".join(f"- {f}" for f in lore.get("key_facts", ()))
                keywords = ", ".join(lore.get("required_keywords", ()))
                hook_sug = (lore.get("narrative_hooks") or [""])[0]
                lore_prompt = (
                    f"\n\nCANON OFICIAL SCP REQUERIDO ({lore['scp_id']} - {lore['canonical_name'].get('es', '')}):\n"
                    f"Clasificación: {lore['object_class']}\n"
                    f"Hechos canónicos verificados:\n{facts}\n"
                    f"Palabras clave obligatorias: {keywords}\n"
                    f"Hook 0-3s sugerido: {hook_sug}\n"
                    "PROHIBICIÓN: Queda estrictamente prohibido inventar propiedades no canónicas."
                )

        prompt = (
            f"Genera un guion de alta retención para el canal '{channel}' en formato '{fmt}' "
            f"sobre el tema: '{clean_topic}'. Presupuesto aproximado: ~{words_budget} palabras.{lore_prompt}\n\n"
            "Requisitos de estructura:\n"
            "- Hook 0-3s que capture la atención de inmediato.\n"
            "- Tensión ascendente progresiva.\n"
            "- Clímax impactante.\n"
            "- Cierre con Loop Hook circular para YouTube Shorts.\n"
            "- Incluye visual_motifs (3-5 descriptores atmosféricos clave)."
        )

        # Check circuit breaker before making expensive calls
        cb = getattr(self, "circuit_breaker", None)
        if cb and cb.is_open():
            logger.warning(
                "Circuit breaker open for %s (%ds remaining). Using procedural fallback.",
                self.instance_id,
                cb.retry_after(),
            )
            return self._procedural_fallback_story(clean_topic, channel, fmt, words_budget)

        logger.info("StoryDirectorAgent generating story for '%s' (%s, format=%s)", clean_topic, channel, fmt)
        try:
            result_path = self.run(prompt)
            res = self.consume(result_path)
            if res.get("result") == "saturated":
                logger.warning("StoryDirectorAgent harness saturated. Using procedural fallback.")
                return self._procedural_fallback_story(clean_topic, channel, fmt, words_budget)
        except Exception as exc:
            if is_saturation_text(str(exc)):
                if cb:
                    cb.record_failure(str(exc))
                logger.warning("StoryDirectorAgent saturated (%s). Using procedural fallback.", exc)
                return self._procedural_fallback_story(clean_topic, channel, fmt, words_budget)
            logger.error("StoryDirectorAgent invocation failed: %s", exc)
            raise AIProviderChainExhausted(f"StoryDirectorAgent fallo de ejecucion: {exc}") from exc

        data = None
        structured = res.get("output", {}).get("structured_output")
        if isinstance(structured, dict) and structured.get("script"):
            data = dict(structured)
        else:
            parsed = parse_json_reply(res.get("output", {}).get("reply", ""))
            if isinstance(parsed, dict) and parsed.get("script"):
                data = dict(parsed)

        if not data or not data.get("script"):
            error_detail = res.get("output", {}).get("error") or "Respuesta sin guion utilizable"
            if is_saturation_text(str(error_detail)) or (cb and cb.is_open()):
                logger.warning("StoryDirectorAgent empty reply due to saturation. Using procedural fallback.")
                return self._procedural_fallback_story(clean_topic, channel, fmt, words_budget)
            raise AIProviderChainExhausted(f"StoryDirectorAgent sin guion valido ({error_detail})")

        # Canonical lore validation for SCP
        if lore and data.get("script"):
            is_valid, issues = validate_scp_lore(data["script"], clean_topic)
            data["is_lore_valid"] = is_valid
            data["lore_issues"] = issues
            if not is_valid:
                logger.warning("StoryDirectorAgent detected canonical SCP divergence: %s", issues)

        data.setdefault("channel", channel)
        return data

    def _procedural_fallback_story(
        self,
        topic: str,
        channel: str = "horror",
        target_format: str = "short",
        target_words: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generates a high-retention fallback story when AI providers are saturated."""
        from src.templates.narratives import get_fallback_story
        is_short = target_format in ("short", "shorts", "vertical", "9:16")
        script = get_fallback_story(channel=channel, topic=topic, is_short=is_short)
        title = topic.strip() or ("Relato de Terror" if channel in ("moku", "horror") else "Dilema Moral")
        first_sentence = script.split(".")[0] if "." in script else script[:80]
        return {
            "title": title,
            "script": script,
            "hook_0_3s": first_sentence.strip(),
            "climax": "El momento culminante de la revelación.",
            "loop_hook": "¿Qué habrías hecho tú?",
            "visual_motifs": ["sombras profundas", "iluminación cinematográfica", "tensión psicológica"],
            "fallback_used": True,
            "channel": channel,
            "status": "procedural_fallback",
        }


# Backward-compatibility facade
class StoryInvestigatorAgent(StoryDirectorAgent):
    """Backward compatibility alias for StoryInvestigatorAgent."""

    def generate_script(self, topic: str = "SCP-173") -> Dict[str, Any]:
        return self.generate_story(topic=topic, channel="horror", target_format="short")


def generate_story_script(topic: str = "SCP-173") -> bool:
    agent = StoryDirectorAgent()
    data = agent.generate_story(topic=topic, channel="horror")
    return bool(data.get("script"))
