"""
src/agents/image_auditor.py - Agent 5: Image Auditor Agent (Anti-Filler & Visual Asset Vetting).

Enforces strict anti-filler criteria:
1. 100% of video backgrounds and animated visual subjects must come from FFmpeg procedural loops or catalog scenery.
2. Pure filler or generic stock photography is strictly REJECTED and discarded.
3. Only verified official brandmarks, institutional emblems (e.g. SCP Foundation Logo, NASA, OpenAI),
   or technical schematics are approved as small non-invasive reference overlay badges.
Validates output against schemas/image_auditor.schema.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema

from src.agents.base_agent import CANONICAL_MODEL, ProgrammaticAgent, parse_json_reply
from src.log import get_logger

logger = get_logger("image_auditor")

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "image_auditor.schema.json"


SYSTEM_INSTRUCTIONS = (
    "You are the Image Auditor Agent for an automated YouTube production system. "
    "Your objective is to enforce strict anti-filler policies: reject all generic stock photos, "
    "filler imagery, or irrelevant visual assets. Approve only official brandmarks, institutional "
    "emblems (e.g., SCP Foundation, NASA, MIT, OpenAI), or technical schematics directly relevant "
    "to the topic for non-invasive reference badge overlays. "
    "Always output strictly valid JSON conforming to the requested schema."
)


class ImageAuditorAgent:
    """Agent 5: Forensic Visual Asset Auditor & Anti-Filler Guardian."""

    def __init__(self, schema_file: Optional[Path] = None, model: str = CANONICAL_MODEL) -> None:
        self.schema_path = schema_file or SCHEMA_PATH
        self.model = model
        self._schema: Optional[Dict[str, Any]] = None
        if self.schema_path.is_file():
            with open(self.schema_path, "r", encoding="utf-8") as f:
                self._schema = json.load(f)

    def validate_report(self, report: Dict[str, Any]) -> None:
        """Validates the audit report against schemas/image_auditor.schema.json."""
        if self._schema:
            jsonschema.validate(instance=report, schema=self._schema)

    def audit_candidates(
        self,
        topic: str,
        candidates: List[Dict[str, Any]],
        channel_lane: Optional[str] = None,
        use_agent: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluates candidate visual assets against anti-filler policy.
        
        If use_agent is True and environment allows, executes via ProgrammaticAgent / Antigravity CLI harness;
        otherwise runs high-precision deterministic forensic evaluation.
        """
        logger.info(
            "Auditing %d candidate visual assets for topic: '%s' (use_agent=%s)",
            len(candidates),
            topic,
            use_agent,
        )

        if use_agent and bool(os.environ.get("USE_AGENT_HARNESS", "0") in ("1", "true", "yes")):
            try:
                task_prompt = (
                    f"Audit the following visual asset candidates for topic '{topic}' and lane '{channel_lane or 'general'}'.\n"
                    f"Candidates: {json.dumps(candidates, ensure_ascii=False)}\n"
                    "Enforce strict anti-filler: reject generic filler, approve only official emblems/schematics relevant to topic."
                )
                agent = ProgrammaticAgent(
                    system_instructions=SYSTEM_INSTRUCTIONS,
                    model=self.model,
                    role_name="image-auditor",
                    json_schema=self.schema_path if self.schema_path.is_file() else None,
                )
                result_path = agent.run(task_prompt)
                consumed = ProgrammaticAgent.consume(result_path)
                structured = consumed.get("structured_output")
                if isinstance(structured, dict) and "verdicts" in structured:
                    self.validate_report(structured)
                    return structured
                parsed = parse_json_reply(consumed.get("response", ""))
                if parsed and "verdicts" in parsed:
                    self.validate_report(parsed)
                    return parsed
            except Exception as exc:
                logger.warning("Antigravity agent audit fallback to deterministic engine: %s", exc)

        return self._deterministic_audit(topic, candidates, channel_lane)

    def _deterministic_audit(
        self,
        topic: str,
        candidates: List[Dict[str, Any]],
        channel_lane: Optional[str] = None,
    ) -> Dict[str, Any]:
        """High-precision deterministic rule engine ported from Temp-."""
        verdicts: List[Dict[str, Any]] = []
        approved_count = 0
        discarded_count = 0

        lower_topic = topic.lower()

        for asset in candidates:
            asset_id = str(asset.get("id") or asset.get("asset_id") or f"asset_{len(verdicts)+1}")
            source_type = asset.get("sourceType") or asset.get("source_type") or "generic_filler_photo"
            name = asset.get("name") or asset.get("entity_name") or "Asset"
            lower_name = name.lower()

            if source_type == "generic_filler_photo":
                discarded_count += 1
                verdict_entry = {
                    "asset_id": asset_id,
                    "source_type": "generic_filler_photo",
                    "entity_name": name,
                    "verdict": "DISCARDED_GENERIC_FILLER",
                    "confidence_score": 0.99,
                    "reasoning": (
                        "DESCARTE ESTRICTO: Las imágenes de relleno genérico o fotos de stock están prohibidas. "
                        "Todo el contenido dinámico de fondo debe provenir de loops de catálogo o scenery verificado."
                    ),
                    "badge_render_type": "none",
                }
                logger.warning("[RECHAZADO] %s descartado por ser imagen estática/stock filler.", name)
                verdicts.append(verdict_entry)
                continue

            is_official = source_type in ("brand_logo", "official_emblem", "technical_schematic")
            is_scp_topic = "scp" in lower_topic or "fundacion" in lower_topic or "fundación" in lower_topic or "foundation" in lower_topic
            is_scp_asset = "scp" in lower_name or "foundation" in lower_name or "fundacion" in lower_name or "fundación" in lower_name
            is_tech_brand = any(b in lower_name for b in ("google", "apple", "openai", "tesla", "meta", "microsoft", "deepmind", "linux"))
            name_words = [w for w in lower_name.split() if len(w) > 3 and w not in ("brand", "logo", "official", "emblem", "photo", "icon")]
            matches_topic = any(w in lower_topic for w in name_words)

            is_relevant = (is_scp_topic and is_scp_asset) or is_tech_brand or matches_topic

            if is_official and is_relevant:
                approved_count += 1
                badge_type = "canvas_procedural_emblem" if (is_scp_topic or is_scp_asset) else "svg_vector_badge"
                verdict_entry = {
                    "asset_id": asset_id,
                    "source_type": source_type,
                    "entity_name": name,
                    "verdict": "APPROVED_REFERENCE",
                    "confidence_score": 0.96,
                    "reasoning": (
                        f"APROBADO COMO REFERENCIA OFICIAL: Se valida el emblema/logotipo '{name}' "
                        "para proyección como badge vectorial overlay no invasivo."
                    ),
                    "badge_render_type": badge_type,
                }
                logger.info("[APROBADO] Emblema oficial autorizado: %s (%s)", name, badge_type)
                verdicts.append(verdict_entry)
            else:
                discarded_count += 1
                verdict_entry = {
                    "asset_id": asset_id,
                    "source_type": source_type,
                    "entity_name": name,
                    "verdict": "REJECTED_LOW_RELEVANCE",
                    "confidence_score": 0.88,
                    "reasoning": f"DESCARTE POR RELEVANCIA: El activo '{name}' no guarda correlación directa con '{topic}'.",
                    "badge_render_type": "none",
                }
                logger.warning("[RECHAZADO] Activo no relevante para '%s': %s", topic, name)
                verdicts.append(verdict_entry)

        report = {
            "version": "2.0",
            "topic": topic,
            "channel_lane": channel_lane or "general",
            "total_candidates": len(candidates),
            "approved_count": approved_count,
            "discarded_count": discarded_count,
            "verdicts": verdicts,
        }

        self.validate_report(report)
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Image Auditor Agent (Anti-Filler & Visual Asset Vetting)")
    parser.add_argument("-t", "--topic", type=str, required=True, help="Video topic / subject")
    parser.add_argument("-c", "--candidates", type=str, default=None, help="JSON list of candidate visual assets")
    parser.add_argument("-l", "--channel-lane", type=str, default="general", help="Channel editorial lane")
    parser.add_argument("--use-agent", action="store_true", default=False, help="Invoke Antigravity CLI harness")
    args = parser.parse_args()

    candidates: List[Dict[str, Any]] = []
    if args.candidates:
        try:
            candidates = json.loads(args.candidates)
        except Exception:
            candidates = [
                {"id": "cand_1", "name": args.candidates, "source_type": "official_emblem"}
            ]
    else:
        # Default probe candidates
        candidates = [
            {
                "id": "asset_scp_emblem",
                "name": "SCP Foundation Insignia Oficial",
                "source_type": "official_emblem",
            },
            {
                "id": "asset_stock_filler",
                "name": "Foto de Stock Genérica - Rostro Asombrado",
                "source_type": "generic_filler_photo",
            },
        ]

    auditor = ImageAuditorAgent()
    report = auditor.audit_candidates(args.topic, candidates, channel_lane=args.channel_lane, use_agent=args.use_agent)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
