"""Story Investigator & Script Writer Agent — Antigravity CLI harness (Pro quota)."""

import json
from pathlib import Path
from typing import Any, Dict

from src.agents.base_agent import CANONICAL_MODEL, ProgrammaticAgent, parse_json_reply
from src.core.scp_lore import get_scp_canonical_lore, validate_scp_lore

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
SCRIPT_RESULT_PATH = OUTPUT_DIR / "generated_script.json"

STORY_SYSTEM_INSTRUCTION = (
    "Eres un investigador de historias y escritor de guiones profesional para YouTube. "
    "Redacta un guion usando la fórmula: Hook 0-3s, Tensión 3-20s, Cliffhanger 20-28s. "
    "Responde ÚNICAMENTE en formato JSON plano con las claves: 'title', 'script', y 'visual_metadata' (lista de descriptores)."
)

STORY_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "script": {"type": "string"},
        "visual_metadata": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "script", "visual_metadata"],
    "additionalProperties": False,
}


class StoryInvestigatorAgent(ProgrammaticAgent):
    """Researches story anomalies and generates video scripts via the Pro harness."""

    def __init__(self, model: str = CANONICAL_MODEL) -> None:
        super().__init__(
            system_instructions=STORY_SYSTEM_INSTRUCTION,
            model=model,
            role_name="story-investigator-agent",
            task_result_path=SCRIPT_RESULT_PATH,
            json_schema=STORY_JSON_SCHEMA,
        )

    def generate_script(self, topic: str = "SCP-173") -> Dict[str, Any]:
        """Generate a story script using the Pro harness grounded in canonical lore."""
        lore = get_scp_canonical_lore(topic)
        lore_prompt = ""
        if lore:
            facts = "\n".join(f"- {f}" for f in lore.get("key_facts", ()))
            keywords = ", ".join(lore.get("required_keywords", ()))
            hook = lore.get("narrative_hooks", [""])[0]
            lore_prompt = (
                f"\n\nCANON OFICIAL SCP REQUERIDO ({lore['scp_id']} - {lore['canonical_name'].get('es', '')}):\n"
                f"Clasificación: {lore['object_class']}\n"
                f"Hechos canónicos verificados:\n{facts}\n"
                f"Palabras clave obligatorias: {keywords}\n"
                f"Hook 0-3s sugerido: {hook}\n"
                "PROHIBICIÓN: Queda estrictamente prohibido inventar propiedades no canónicas o mezclar temas domésticos/romance."
            )

        prompt = (
            f"Genera un guion fascinante para YouTube sobre: {topic}. {lore_prompt}\n"
            "Incluye title, script (hook/tensión/cliffhanger) y visual_metadata."
        )
        result_path = self.run(prompt)
        res = self.consume(result_path)

        fallback_visuals = (
            list(lore["visual_descriptors"]) if lore and lore.get("visual_descriptors")
            else ["anomalia", "misterio", "oscuridad"]
        )

        data: Dict[str, Any]
        structured = res.get("output", {}).get("structured_output")
        if isinstance(structured, dict) and structured.get("script"):
            data = dict(structured)
        else:
            parsed = parse_json_reply(res.get("output", {}).get("reply", ""))
            if isinstance(parsed, dict) and parsed.get("script"):
                data = dict(parsed)
            else:
                # AUD-02 (WP2): fail-closed — never emit a degraded non-AI
                # script when the harness returned no usable reply.
                error_detail = res.get("output", {}).get("error") or "sin respuesta"
                from src.core.domain import AIProviderChainExhausted

                raise AIProviderChainExhausted(
                    f"StoryInvestigator sin guion IA utilizable ({error_detail})"
                )

        # Post-synthesis canonical lore validation
        if lore and data.get("script"):
            is_valid, issues = validate_scp_lore(data["script"], topic)
            data["is_lore_valid"] = is_valid
            if not is_valid:
                data["lore_warnings"] = issues

        return data

    def write_script_result(self, data: Dict[str, Any]) -> Path:
        """Persist the script dict to output/generated_script.json."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        SCRIPT_RESULT_PATH.write_text(
            json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8"
        )
        return SCRIPT_RESULT_PATH


def generate_story_script(topic: str = "SCP-173") -> bool:
    """CLI / Backward compatibility helper."""
    print(f"Iniciando Agente Guionista/Investigador (Modelo: {CANONICAL_MODEL})...")
    agent = StoryInvestigatorAgent()
    data = agent.generate_script(topic)
    path = agent.write_script_result(data)
    print(f"Script guardado en {path}")
    return True


if __name__ == "__main__":
    generate_story_script()
