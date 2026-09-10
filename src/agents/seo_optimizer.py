"""
src/agents/seo_optimizer.py - Agent 6: SEO & Viral Metadata Optimizer.

Generates high-CTR titles for A/B testing, structured YouTube descriptions with timestamps,
optimized tag clouds, algorithm-boosting pinned comments, and thumbnail visual concepts.
Validates output against schemas/seo_metadata.schema.json.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import jsonschema

from src.agents.base_agent import CANONICAL_MODEL, ProgrammaticAgent, parse_json_reply
from src.log import get_logger

logger = get_logger("seo_optimizer")

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "seo_metadata.schema.json"

SYSTEM_INSTRUCTIONS = (
    "You are a world-class YouTube algorithm and SEO strategist. "
    "Given a topic and format, generate high-converting YouTube metadata in Spanish: "
    "1. 3 viral title options designed for high CTR and curiosity gap. "
    "2. Selected title. "
    "3. High-retention description with formatted timestamps, CTA, and tags. "
    "4. Relevant tags and valid hashtags. "
    "5. Pinned comment to maximize audience engagement. "
    "6. Thumbnail concepts using prompt-driven real-time intelligence: "
    "   Chiaroscuro high-CTR style, punchy 3-5 word viral hook headline, mysterious focal subject, "
    "   and high-contrast color palette. "
    "Always output strictly valid JSON conforming to the requested schema."
)


class SeoOptimizerAgent:
    """Agent 6: High-conversion YouTube SEO & Metadata Optimizer."""

    def __init__(
        self,
        schema_file: Optional[Path] = None,
        model: str = CANONICAL_MODEL,
        instance_id: str = "pipeline_seo",
        reasoning_effort: str = "high",
    ) -> None:
        self.schema_path = schema_file or SCHEMA_PATH
        self.model = model
        self.instance_id = instance_id
        self.reasoning_effort = reasoning_effort
        self._schema: Optional[Dict[str, Any]] = None
        if self.schema_path.is_file():
            with open(self.schema_path, "r", encoding="utf-8") as f:
                self._schema = json.load(f)

    def validate_metadata(self, metadata: Dict[str, Any]) -> None:
        """Validates output against schemas/seo_metadata.schema.json."""
        if self._schema:
            jsonschema.validate(instance=metadata, schema=self._schema)

    @staticmethod
    def build_synchronized_timestamps(acts: List[Dict[str, Any]], total_duration_sec: float) -> str:
        """Generates synchronized description timestamps that are strictly within the video length."""
        if not acts:
            return "00:00 - Introducción"
        lines = ["TIMESTAMPS:"]
        for act in acts:
            start = float(act.get("start_sec", 0))
            if start >= total_duration_sec:
                continue
            mm = int(start // 60)
            ss = int(start % 60)
            label = act.get("title") or act.get("label") or "Sección"
            # Clean editorial markers from label
            from src.sanitizer import RE_ACT_CHAPTER_LABELS
            label = RE_ACT_CHAPTER_LABELS.sub("", label).strip()
            lines.append(f"{mm:02d}:{ss:02d} - {label}")
        return "\n".join(lines)

    @staticmethod
    def validate_description_timestamps(description: str, total_duration_sec: float) -> Tuple[bool, List[str]]:
        """Validates that all timestamp markers in description are valid and within video duration."""
        errors: List[str] = []
        # Match mm:ss or hh:mm:ss timestamps
        ts_matches = re.findall(r"\b(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\b", description)
        for h, m, s in ts_matches:
            hrs = int(h) if h else 0
            mins = int(m)
            secs = int(s)
            ts_in_seconds = hrs * 3600 + mins * 60 + secs
            if ts_in_seconds > total_duration_sec + 0.5:
                errors.append(f"Timestamp {h+':' if h else ''}{mins:02d}:{secs:02d} ({ts_in_seconds}s) exceeds video duration ({total_duration_sec:.1f}s)")
        return len(errors) == 0, errors

    def optimize(
        self,
        topic: str,
        target_format: str = "short",
        niche: str = "General",
        use_agent: bool = False,
    ) -> Dict[str, Any]:
        """
        Generates optimized SEO metadata for a topic.
        Uses Antigravity harness if use_agent is True; otherwise uses deterministic viral formulas.
        """
        fmt = "short" if target_format in ("short", "shorts", "9:16", "vertical") else "longform"
        logger.info("Optimizing SEO for topic: '%s' (format=%s, use_agent=%s)", topic, fmt, use_agent)

        if use_agent and bool(os.environ.get("USE_AGENT_HARNESS", "0") in ("1", "true", "yes")):
            try:
                task_prompt = (
                    f"Generate YouTube SEO metadata for topic '{topic}' in format '{fmt}' and niche '{niche}'.\n"
                    "Include 3 viral titles, description with timestamps, tags, hashtags, pinned comment, and thumbnail concepts."
                )
                agent = ProgrammaticAgent(
                    system_instructions=SYSTEM_INSTRUCTIONS,
                    model=self.model,
                    role_name="seo-optimizer",
                    instance_id=self.instance_id,
                    reasoning_effort=self.reasoning_effort,
                    json_schema=self.schema_path if self.schema_path.is_file() else None,
                )
                result_path = agent.run(task_prompt)
                consumed = ProgrammaticAgent.consume(result_path)
                output_doc = consumed.get("output", {})
                structured = output_doc.get("structured_output")
                if isinstance(structured, dict) and "selected_title" in structured:
                    self.validate_metadata(structured)
                    return structured
                parsed = parse_json_reply(output_doc.get("reply", ""))
                if parsed and "selected_title" in parsed:
                    self.validate_metadata(parsed)
                    return parsed
            except Exception as exc:
                logger.warning("Antigravity SEO agent fallback to algorithmic engine: %s", exc)

        return self._deterministic_seo(topic, fmt, niche)

    def _deterministic_seo(self, topic: str, target_format: str, niche: str) -> Dict[str, Any]:
        """Algorithmic viral formulas with zero API dependencies, ported from Temp-."""
        clean_topic = topic.strip()
        slug = re.sub(r"[^A-Za-z0-9]", "", clean_topic)
        if not slug:
            slug = "Curiosidades"

        niche_l = (niche or "").lower()
        is_scp = "scp" in clean_topic.lower() or "scp" in niche_l
        is_moku_horror = any(k in niche_l or k in clean_topic.lower() for k in ("moku", "horror", "terror", "creepy", "nosleep"))
        if is_scp or is_moku_horror:
            if is_scp:
                viral_titles = [
                    f"El Secreto Prohibido de {clean_topic} (Clase Thaumiel)",
                    f"¿Qué Oculta Realmente {clean_topic}? La Verdad de la Fundación",
                    f"NUNCA Mires los Archivos de {clean_topic} a Solas",
                ]
            else:
                viral_titles = [
                    f"Lo que pasó en {clean_topic} (nadie volvió igual)",
                    f"NUNCA ignores esta advertencia sobre {clean_topic}",
                    f"Escuché esto sobre {clean_topic}… y no pude dormir",
                ]
            selected_title = viral_titles[0]
            description = (
                f"⚠️ ARCHIVO CLASIFICADO: Descubre los expedientes secretos sobre {clean_topic}.\n\n"
                "📌 Suscríbete y activa la campana para más accesos autorizados de la Fundación SCP.\n\n"
                "⏱️ Marcas de tiempo:\n"
                "0:00 Entrada y Hook de Contención\n"
                "0:15 Los Procedimientos Especiales\n"
                "0:45 Revelación Final y Conclusión\n\n"
                f"#{slug} #SCPFoundation #Misterio #Viral"
            )
            tags = [
                clean_topic.lower(),
                "scp",
                "scp foundation",
                "archivos secretos",
                "documental scp",
                "contencion",
                "misterio",
                target_format,
            ]
            hashtags = [f"#{slug}", "#SCPFoundation", "#Misterio", "#Viral"]
            pinned_comment = f"👇 ¿Crees que la Fundación tomó la decisión correcta con {clean_topic}? ¡Debatamos en los comentarios!"
            thumbnail_concepts = [
                {
                    "visual_layout": "Estilo Claroscuro de alto CTR: iluminación volumétrica lateral dramática, sombras profundas, sujeto focal misterioso en penumbra con silueta recortada",
                    "big_headline": "¡EXPEDIENTE SECRETO PROHIBIDO! ⚠️",
                    "color_palette": ["#FF0000", "#111827", "#F59E0B", "#FFFFFF"],
                    "facial_expression": "Silueta misteriosa en sombras con mirada fija",
                },
                {
                    "visual_layout": "Claroscuro de máximo contraste: luz de contorno verde cian sobre fondo negro abisal, sujeto focal misterioso emergiendo",
                    "big_headline": "NUNCA ENTRES A SOLAS 🧬",
                    "color_palette": ["#00FF66", "#040A08", "#D8FFE6"],
                    "facial_expression": "Sujeto en penumbra de espaldas al abismo",
                },
            ]
        else:
            viral_titles = [
                f"El Secreto Oculto de {clean_topic} que Nadie te Dice",
                f"NUNCA HAGAS ESTO con {clean_topic} (La Verdad Revelada)",
                f"Cómo Dominar {clean_topic} en Tiempo Récord [2026]",
            ]
            selected_title = viral_titles[0]
            description = (
                f"🔥 En este video revelamos todo lo que necesitas saber sobre {clean_topic}.\n\n"
                "📌 Suscríbete y activa la campanita para más contenido exclusivo.\n\n"
                "⏱️ Marcas de tiempo:\n"
                "0:00 Introducción y Hook\n"
                "0:15 El Gran Descubrimiento\n"
                "0:45 Conclusión y Llamado a la Acción\n\n"
                f"#{slug} #YouTubeAuto #Viral"
            )
            tags = [
                clean_topic.lower(),
                f"{clean_topic.lower()} explicacion",
                "curiosidades",
                "youtube automation",
                "datos fascinantes",
                niche.lower(),
                target_format,
            ]
            hashtags = [f"#{slug}", "#Curiosidades", "#YouTubeShorts" if target_format == "short" else "#YouTube", "#Viral"]
            pinned_comment = f"👇 ¿Cuál fue el dato que más te sorprendió sobre {clean_topic}? ¡Déjalo abajo!"
            thumbnail_concepts = [
                {
                    "visual_layout": "Estilo Claroscuro de alto CTR: iluminación de recorte volumétrica de alto impacto, sujeto focal misterioso en primer plano sobre fondo oscuro",
                    "big_headline": "¡NO COMETAS ESTE ERROR! 🚨",
                    "color_palette": ["#FF0000", "#FFFFFF", "#000000", "#FFD700"],
                    "facial_expression": "Expresión de impacto y mirada directa intrigante",
                },
                {
                    "visual_layout": "Composición Claroscuro de tensión: fondo oscuro minimalista con resplandor neón dorado y sujeto focal intrigante recortado",
                    "big_headline": "EL SECRETO MEJOR GUARDADO ❌",
                    "color_palette": ["#00FF88", "#111827", "#F59E0B"],
                    "facial_expression": "Sujeto focal en sombra señalando hacia el misterio",
                },
            ]

        metadata = {
            "version": "2.0",
            "topic": clean_topic,
            "target_format": target_format,
            "viral_title_options": viral_titles,
            "selected_title": selected_title,
            "description": description,
            "tags": tags,
            "hashtags": hashtags,
            "pinned_comment": pinned_comment,
            "thumbnail_concepts": thumbnail_concepts,
        }

        self.validate_metadata(metadata)
        return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="SEO & Viral Metadata Optimizer")
    parser.add_argument("--topic", type=str, required=True, help="Video topic")
    parser.add_argument("--format", type=str, default="short", choices=["short", "longform"], help="Target format")
    parser.add_argument("--niche", type=str, default="General", help="Content niche")
    parser.add_argument("--use-agent", action="store_true", default=False, help="Use Antigravity CLI harness")
    args = parser.parse_args()

    optimizer = SeoOptimizerAgent()
    data = optimizer.optimize(args.topic, target_format=args.format, niche=args.niche, use_agent=args.use_agent)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
