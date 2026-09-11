"""Translator & Title Curator Agent — Antigravity CLI harness (Pro quota), structured JSON."""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from src.agents.base_agent import CANONICAL_MODEL, ProgrammaticAgent, parse_json_reply

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
TRANSLATION_RESULT_PATH = OUTPUT_DIR / "translation_result.json"

TRANSLATOR_SYSTEM_INSTRUCTION = (
    "Eres un traductor y curador de títulos profesional para YouTube Shorts. "
    "Traduces texto con máxima fidelidad de tono, adaptando expresiones culturales "
    "y generando títulos virales y optimizados para SEO. "
    "Traduce al idioma solicitado y genera exactamente 3 títulos virales. "
    "El sistema ya no genera prompts de imagen: el video se compone con motor de loop atmosférico."
)

TRANSLATOR_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "translated_text": {"type": "string"},
        "viral_titles": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["translated_text", "viral_titles"],
    "additionalProperties": False,
}


class TranslatorAgent(ProgrammaticAgent):
    """Translates scripts and curates viral titles via the Pro harness.

    Image-prompt generation has been removed: the active pipeline composes
    a continuous atmospheric loop with ``LoopVideoEngine`` and no longer
    synthesizes per-scene images.
    """

    def __init__(
        self,
        model: str = CANONICAL_MODEL,
        instance_id: str = "pipeline_translator",
        reasoning_effort: str = "high",
    ) -> None:
        super().__init__(
            system_instructions=TRANSLATOR_SYSTEM_INSTRUCTION,
            model=model,
            role_name="translator-agent",
            instance_id=instance_id,
            reasoning_effort=reasoning_effort,
            task_result_path=TRANSLATION_RESULT_PATH,
            json_schema=TRANSLATOR_JSON_SCHEMA,
        )

    def translate_and_curate(
        self, text_to_translate: str, target_lang: str = "es"
    ) -> Dict[str, Any]:
        """Translate text and curate viral titles using the Pro harness."""
        prompt = (
            f"Traduce el siguiente texto al idioma '{target_lang}' y genera 3 "
            f"títulos virales cortos:\n\n{text_to_translate}"
        )
        parsed: Optional[dict[str, Any]] = None
        try:
            result_path = self.run(prompt)
            res = self.consume(result_path)
            structured = res.get("output", {}).get("structured_output")
            if isinstance(structured, dict) and structured.get("translated_text"):
                parsed = structured
            else:
                parsed = parse_json_reply(res.get("output", {}).get("reply", ""))
        except Exception:
            parsed = None

        if not parsed or not parsed.get("translated_text"):
            clean_trans = self._basic_fallback_clean(text_to_translate)
            from src.branding import truncate_at_word_boundary
            parsed = {
                "translated_text": clean_trans,
                "viral_titles": [truncate_at_word_boundary(clean_trans, 50)],
            }

        parsed["translated_text"] = self._clean_residual_english(parsed["translated_text"])
        # Back-compat: external callers may still expect the key.
        parsed.setdefault("scene_prompts", [])

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        TRANSLATION_RESULT_PATH.write_text(
            json.dumps(parsed, indent=4, ensure_ascii=False), encoding="utf-8"
        )
        return parsed

    def _basic_fallback_clean(self, text: str) -> str:
        """Robust fallback translation via GoogleTranslator when the LLM is unavailable."""
        if not text or not text.strip():
            return text
        try:
            from deep_translator import GoogleTranslator
            translator = GoogleTranslator(source="auto", target="es")

            paragraphs = text.split("\n\n")
            chunks = []
            curr_chunk = []
            curr_len = 0
            for p in paragraphs:
                if curr_len + len(p) > 3000 and curr_chunk:
                    chunks.append("\n\n".join(curr_chunk))
                    curr_chunk = [p]
                    curr_len = len(p)
                else:
                    curr_chunk.append(p)
                    curr_len += len(p)
            if curr_chunk:
                chunks.append("\n\n".join(curr_chunk))

            translated_chunks = []
            for chunk in chunks:
                if chunk.strip():
                    trans = translator.translate(chunk)
                    translated_chunks.append(trans if trans else chunk)
            res = "\n\n".join(translated_chunks)
            if res and len(res.strip()) > 0:
                return res
        except Exception:
            pass
        cleaned = text.replace("reinforced", "reforzada").replace("bunker", "búnker")
        return cleaned

    def _clean_residual_english(self, text: str) -> str:
        """Replace common residual English tokens that slip through translation."""
        replacements = {
            " reinforced ": " reforzada ",
            "Reinforced ": "Reforzada ",
            " bunker ": " búnker ",
            "Bunker ": "Búnker ",
            " basement ": " sótano ",
            "Basement ": "Sótano ",
        }
        res = text
        for eng, esp in replacements.items():
            res = res.replace(eng, esp)
        return res


if __name__ == "__main__":
    agent = TranslatorAgent()
    res = agent.translate_and_curate("The creature lurked in the dark basement, waiting for someone to blink.")
    print("Resultado de traducción guardado en output/translation_result.json")
    print(json.dumps(res, ensure_ascii=False, indent=2)[:500])
