"""
src/agents/seo_optimizer.py - Agent 6: SEO & Viral Metadata Optimizer.

Generates high-CTR titles for A/B testing, structured YouTube descriptions with timestamps,
optimized tag clouds, algorithm-boosting pinned comments, and thumbnail visual concepts.
Validates output against schemas/seo_metadata.schema.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import jsonschema

from src.agents.base_agent import CANONICAL_MODEL, ProgrammaticAgent, parse_json_reply
from src.core.domain import AIProviderChainExhausted
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

    @staticmethod
    def _clamp_titles(metadata: Dict[str, Any]) -> None:
        """Ensure all titles strictly observe YouTube's 100-character ceiling at word boundary."""
        from src.branding import truncate_at_word_boundary
        if "selected_title" in metadata and isinstance(metadata["selected_title"], str):
            metadata["selected_title"] = truncate_at_word_boundary(metadata["selected_title"].strip(), 100)
        if "viral_title_options" in metadata and isinstance(metadata["viral_title_options"], list):
            metadata["viral_title_options"] = [
                truncate_at_word_boundary(str(t).strip(), 100) for t in metadata["viral_title_options"]
            ]

    def validate_metadata(self, metadata: Dict[str, Any]) -> None:
        """Validates output against schemas/seo_metadata.schema.json."""
        self._clamp_titles(metadata)
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
        use_agent: bool = True,
        fail_closed: bool = False,
    ) -> Dict[str, Any]:
        """
        Generates optimized SEO metadata for a topic.
        Uses Antigravity harness if use_agent is True; otherwise uses deterministic viral formulas.
        If fail_closed is True and the agent fails, raises AIProviderChainExhausted.
        """
        fmt = "short" if target_format in ("short", "shorts", "9:16", "vertical") else "longform"
        logger.info("Optimizing SEO for topic: '%s' (format=%s, use_agent=%s)", topic, fmt, use_agent)

        from src.pipeline.utils import is_pipeline_test_environment as is_test_environment

        run_harness = use_agent and (
            bool(os.environ.get("USE_AGENT_HARNESS", "0") in ("1", "true", "yes"))
            or not is_test_environment()
        )

        if run_harness:
            try:
                recent_titles_prompt = ""
                try:
                    from src.core.inventory import get_inventory_ai_digest
                    channel_scope = niche if niche in ("moku", "aelithia", "horror", "drama") else None
                    digest = get_inventory_ai_digest(channel=channel_scope, limit=12)
                    titles = [p["title"] for p in digest.get("recent_publications", []) if p.get("title")]
                    if titles:
                        recent_titles_prompt = (
                            "\n\nIMPORTANT - PREVIOUSLY PUBLISHED TITLES IN INVENTORY:\n"
                            + "\n".join(f"- {t}" for t in titles[:10])
                            + "\nYou MUST generate NOVEL, unique hooks that do NOT duplicate or closely mimic any of the above titles."
                        )
                except Exception:
                    recent_titles_prompt = ""

                task_prompt = (
                    f"Generate YouTube SEO metadata for topic '{topic}' in format '{fmt}' and niche '{niche}'.\n"
                    "Include 3 viral titles, description with timestamps, tags, hashtags, pinned comment, and thumbnail concepts."
                    f"{recent_titles_prompt}"
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
                if fail_closed:
                    raise AIProviderChainExhausted("SeoOptimizerAgent respuesta sin titulo estructurado")
            except Exception as exc:
                if fail_closed and not is_test_environment():
                    raise AIProviderChainExhausted(f"SeoOptimizerAgent fallo en optimizacion: {exc}") from exc
                logger.warning("Antigravity SEO agent fallback to algorithmic engine: %s", exc)

        return self._deterministic_seo(topic, fmt, niche)

    def _deterministic_seo(self, topic: str, target_format: str, niche: str) -> Dict[str, Any]:
        """Algorithmic viral formulas with zero API dependencies, ported from Temp-."""
        from src.branding import truncate_at_word_boundary

        clean_topic = topic.strip()
        slug = re.sub(r"[^A-Za-z0-9]", "", clean_topic)
        if not slug:
            slug = "Curiosidades"

        niche_l = (niche or "").lower()
        is_scp = "scp" in clean_topic.lower() or "scp" in niche_l
        is_moku_horror = any(k in niche_l or k in clean_topic.lower() for k in ("moku", "horror", "terror", "creepy", "nosleep"))
        is_drama = any(k in niche_l or k in clean_topic.lower() for k in ("drama", "aita", "aelithia", "relato", "confesion", "infidelidad", "boda", "familia")) or clean_topic.startswith("¿")

        if is_scp or is_moku_horror:
            if is_scp:
                if len(clean_topic) > 40:
                    viral_titles = [
                        f"[CLASIFICADO] {clean_topic}",
                        f"Expediente SCP: {clean_topic}",
                        f"NUNCA abras este archivo: {clean_topic}",
                    ]
                else:
                    viral_titles = [
                        f"El Secreto Prohibido de {clean_topic} (Clase Thaumiel)",
                        f"¿Qué Oculta Realmente {clean_topic}? La Verdad de la Fundación",
                        f"NUNCA Mires los Archivos de {clean_topic} a Solas",
                    ]
            else:
                if len(clean_topic) > 40:
                    viral_titles = [
                        clean_topic,
                        f"Lo que pasó: {clean_topic}",
                        f"NUNCA ignores esto: {clean_topic}",
                    ]
                else:
                    viral_titles = [
                        f"Lo que pasó en {clean_topic} (nadie volvió igual)",
                        f"NUNCA ignores esta advertencia sobre {clean_topic}",
                        f"Escuché esto sobre {clean_topic}… y no pude dormir",
                    ]
            viral_titles = [truncate_at_word_boundary(t, 100) for t in viral_titles]
            selected_title = viral_titles[0]
            description = (
                f"⚠️ ARCHIVO CLASIFICADO: Descubre los expedientes secretos sobre {truncate_at_word_boundary(clean_topic, 60)}.\n\n"
                "📌 Suscríbete y activa la campana para más accesos autorizados de la Fundación SCP.\n\n"
                "⏱️ Marcas de tiempo:\n"
                "0:00 Entrada y Hook de Contención\n"
                "0:15 Los Procedimientos Especiales\n"
                "0:45 Revelación Final y Conclusión\n\n"
                f"#{slug[:15]} #SCPFoundation #Misterio #Viral"
            )
            tags = [
                truncate_at_word_boundary(clean_topic.lower(), 40),
                "scp",
                "scp foundation",
                "archivos secretos",
                "documental scp",
                "contencion",
                "misterio",
                target_format,
            ]
            hashtags = [f"#{slug[:15]}", "#SCPFoundation", "#Misterio", "#Viral"]
            pinned_comment = f"👇 ¿Crees que la Fundación tomó la decisión correcta con {truncate_at_word_boundary(clean_topic, 40)}? ¡Debatamos en los comentarios!"
            seed_hash = int(hashlib.md5(clean_topic.encode("utf-8")).hexdigest()[:6], 16)
            horror_headlines = [
                "¡EXPEDIENTE SECRETO PROHIBIDO! ⚠️",
                "NUNCA ENTRES A SOLAS 🧬",
                "EL ARCHIVO CONFIDENCIAL ❌",
                "NO DEBIERON ABRIRLO 🚨",
                "LA PESADILLA OCULTA 👁️",
                "EXPEDIENTE CLASIFICADO ⚠️",
            ]
            thumbnail_concepts = [
                {
                    "visual_layout": "Estilo Claroscuro de alto CTR: iluminación volumétrica lateral dramática, sombras profundas, sujeto focal misterioso en penumbra con silueta recortada",
                    "big_headline": horror_headlines[seed_hash % len(horror_headlines)],
                    "color_palette": ["#FF0000", "#111827", "#F59E0B", "#FFFFFF"],
                    "facial_expression": "Silueta misteriosa en sombras con mirada fija",
                },
                {
                    "visual_layout": "Claroscuro de máximo contraste: luz de contorno verde cian sobre fondo negro abisal, sujeto focal misterioso emergiendo",
                    "big_headline": horror_headlines[(seed_hash + 1) % len(horror_headlines)],
                    "color_palette": ["#00FF66", "#040A08", "#D8FFE6"],
                    "facial_expression": "Sujeto en penumbra de espaldas al abismo",
                },
            ]
        elif is_drama:
            if clean_topic.startswith("¿") or len(clean_topic) > 35:
                viral_titles = [
                    clean_topic,
                    f"{clean_topic} (La verdad oculta)",
                    f"{clean_topic} ¿Hice lo correcto?",
                ]
            else:
                viral_titles = [
                    f"¿Soy la mala por lo que pasó con {clean_topic}?",
                    f"NUNCA imaginé la traición tras {clean_topic}",
                    f"La verdad sobre {clean_topic} que nadie sospechaba",
                ]
            viral_titles = [truncate_at_word_boundary(t, 100) for t in viral_titles]
            selected_title = viral_titles[0]
            description = (
                f"💭 En este relato revelamos todos los detalles sobre {truncate_at_word_boundary(clean_topic, 60)}.\n\n"
                "📌 Suscríbete y activa la campanita para más historias y confesiones.\n\n"
                "⏱️ Marcas de tiempo:\n"
                "0:00 Introducción y Dilema\n"
                "0:15 El Conflicto Principal\n"
                "0:45 Desenlace y Juicio Moral\n\n"
                f"#{slug[:15]} #HistoriasReales #Confesiones #Viral"
            )
            tags = [
                truncate_at_word_boundary(clean_topic.lower(), 40),
                "historias de reddit",
                "aita",
                "relatos",
                "confesiones",
                "drama",
                "dilemas morales",
                target_format,
            ]
            hashtags = [f"#{slug[:15]}", "#HistoriasReales", "#Confesiones", "#Viral"]
            pinned_comment = f"👇 ¿Tú qué habrías hecho en esta situación? ¡Déjame tu opinión en los comentarios!"
            seed_hash = int(hashlib.md5(clean_topic.encode("utf-8")).hexdigest()[:6], 16)
            drama_headlines = [
                "¡NO COMETAS ESTE ERROR! 🚨",
                "EL SECRETO MEJOR GUARDADO ❌",
                "TRAICIÓN AL DESCUBIERTO ⚡",
                "LA VERDAD QUE OCULTABAN 💥",
                "DESENMASCARADO ANTE TODOS ⚖️",
                "TODO FUE UNA MENTIRA 💔",
            ]
            thumbnail_concepts = [
                {
                    "visual_layout": "Estilo Claroscuro de alto CTR: iluminación de recorte volumétrica de alto impacto, sujeto focal misterioso en primer plano sobre fondo oscuro",
                    "big_headline": drama_headlines[seed_hash % len(drama_headlines)],
                    "color_palette": ["#FF0000", "#FFFFFF", "#000000", "#FFD700"],
                    "facial_expression": "Expresión de impacto y mirada directa intrigante",
                },
                {
                    "visual_layout": "Composición Claroscuro de tensión: fondo oscuro minimalista con resplandor neón dorado y sujeto focal intrigante recortado",
                    "big_headline": drama_headlines[(seed_hash + 1) % len(drama_headlines)],
                    "color_palette": ["#00FF88", "#111827", "#F59E0B"],
                    "facial_expression": "Sujeto focal en sombra señalando hacia el misterio",
                },
            ]
        else:
            if len(clean_topic) > 40:
                viral_titles = [
                    clean_topic,
                    f"La verdad sobre {clean_topic}",
                    f"Lo que ocultan de {clean_topic}",
                ]
            else:
                viral_titles = [
                    f"El Secreto Oculto de {clean_topic} que Nadie te Dice",
                    f"NUNCA HAGAS ESTO con {clean_topic} (La Verdad Revelada)",
                    f"Cómo Dominar {clean_topic} en Tiempo Récord [2026]",
                ]
            viral_titles = [truncate_at_word_boundary(t, 100) for t in viral_titles]
            selected_title = viral_titles[0]
            description = (
                f"🔥 En este video revelamos todo lo que necesitas saber sobre {truncate_at_word_boundary(clean_topic, 60)}.\n\n"
                "📌 Suscríbete y activa la campanita para más contenido exclusivo.\n\n"
                "⏱️ Marcas de tiempo:\n"
                "0:00 Introducción y Hook\n"
                "0:15 El Gran Descubrimiento\n"
                "0:45 Conclusión y Llamado a la Acción\n\n"
                f"#{slug[:15]} #Historias #Relatos #Viral"
            )
            tags = [
                truncate_at_word_boundary(clean_topic.lower(), 40),
                f"{truncate_at_word_boundary(clean_topic.lower(), 30)} explicacion",
                "curiosidades",
                "historias",
                "datos fascinantes",
                niche.lower(),
                target_format,
            ]
            hashtags = [f"#{slug[:15]}", "#Curiosidades", "#YouTubeShorts" if target_format == "short" else "#YouTube", "#Viral"]
            pinned_comment = f"👇 ¿Cuál fue el dato que más te sorprendió sobre {truncate_at_word_boundary(clean_topic, 40)}? ¡Déjalo abajo!"
            seed_hash = int(hashlib.md5(clean_topic.encode("utf-8")).hexdigest()[:6], 16)
            drama_headlines = [
                "¡NO COMETAS ESTE ERROR! 🚨",
                "EL SECRETO MEJOR GUARDADO ❌",
                "TRAICIÓN AL DESCUBIERTO ⚡",
                "LA VERDAD QUE OCULTABAN 💥",
                "DESENMASCARADO ANTE TODOS ⚖️",
                "TODO FUE UNA MENTIRA 💔",
            ]
            thumbnail_concepts = [
                {
                    "visual_layout": "Estilo Claroscuro de alto CTR: iluminación de recorte volumétrica de alto impacto, sujeto focal misterioso en primer plano sobre fondo oscuro",
                    "big_headline": drama_headlines[seed_hash % len(drama_headlines)],
                    "color_palette": ["#FF0000", "#FFFFFF", "#000000", "#FFD700"],
                    "facial_expression": "Expresión de impacto y mirada directa intrigante",
                },
                {
                    "visual_layout": "Composición Claroscuro de tensión: fondo oscuro minimalista con resplandor neón dorado y sujeto focal intrigante recortado",
                    "big_headline": drama_headlines[(seed_hash + 1) % len(drama_headlines)],
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
    parser.add_argument("-t", "--topic", type=str, required=True, help="Video topic")
    parser.add_argument("-f", "--format", type=str, default="short", choices=["short", "longform"], help="Target format")
    parser.add_argument("-n", "--niche", type=str, default="General", help="Content niche")
    parser.add_argument("--use-agent", action="store_true", default=False, help="Use Antigravity CLI harness")
    args = parser.parse_args()

    optimizer = SeoOptimizerAgent()
    data = optimizer.optimize(args.topic, target_format=args.format, niche=args.niche, use_agent=args.use_agent)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


# Primary alias for new AI-First architecture
ViralPackagingAgent = SeoOptimizerAgent


if __name__ == "__main__":
    sys.exit(main())
