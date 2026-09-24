"""Stage 11: Thumbnail generation (with climax frame extraction) and metadata persistence."""

from __future__ import annotations

import json
import os

import lib.video
from src.agents.seo_optimizer import SeoOptimizerAgent
from src.core.profiling import CanonicalStage
from src.core.scenic_detector import extract_story_motifs
import src.llm
from src.log import get_logger
from src.pipeline.context import PipelineContext
from src.pipeline.utils import is_pipeline_test_environment as is_test_environment

logger = get_logger("pipeline.stages.stage_11_metadata")


def stage_11_thumbnail_metadata(ctx: PipelineContext) -> None:
    """Stage 11: Thumbnail generation (with climax frame extraction) and metadata persistence."""
    with ctx.profiler.phase(CanonicalStage.THUMBNAIL_METADATA):
        ctx.spanish_title = (
            src.llm.clean_title(ctx.title)
            if is_test_environment()
            else src.llm.clean_title(src.llm.translate_title(ctx.title, provider="A"))
        )
        from src.branding import truncate_at_word_boundary
        from src.core.inventory import extract_hook_and_synopsis

        story_hook, story_synopsis = extract_hook_and_synopsis(
            ctx.spanish_title or ctx.title or "",
            ctx.script or "",
        )

        motifs_for_thumb = extract_story_motifs(ctx.spanish_title or ctx.title or "")
        thumb_hook = getattr(ctx.lane, "hook_text", None) or (
            ctx.story.get("hook_text") if isinstance(ctx.story, dict) else None
        )
        if not thumb_hook and motifs_for_thumb:
            motif_hooks = {
                "carnival": ["¿QUÉ HABÍA EN LA FERIA?", "FERIA MALDITA ⚠️", "EL CIRCO PROHIBIDO"],
                "morgue": ["¿QUÉ HABÍA EN LA CAMILLA?", "LA AUTOPSIA OCULTA 🚨", "NO ESTABA MUERTO"],
                "asylum": ["¿QUÉ HABÍA EN EL PASILLO?", "PABELLÓN CLAUSURADO 👁️", "EL GRITO EN LA CELDA"],
                "cabin": ["¿QUÉ HABÍA EN LA CABAÑA?", "NUNCA ENTRES AL BOSQUE 🌲", "EL REFUGIO PERDIDO"],
                "cemetery": ["¿QUÉ HABÍA EN LA TUMBA?", "LA CRIPTA ABIERTA ⚠️", "NO DEBÍ ABRIRLA"],
                "diner": ["¿QUÉ PASÓ A LAS 3 AM?", "TURNO DE NOCHE FATAL ❌", "EL CLIENTE EN SOMBRAS"],
                "bakery": ["¿QUÉ HABÍA EN EL HORNO?", "TURNO DE MADRUGADA ⚠️", "EL SECRETO DEL OBRADOR"],
                "mar": ["¿QUÉ HABÍA EN EL FARO?", "ABISMO SUBMARINO 🌊", "EL ECO DE LA FOSA"],
                "boda": ["¿ARRUINÉ SU BODA? 💥", "EXIGENCIAS IMPOSIBLES ⚖️", "NO PAGARÉ SU BODA 🚫", "TRAICIÓN EN EL ALTAR 💔"],
                "hermano": ["¿TRAICIÓN FAMILIAR? ⚡", "MI HERMANO ME ENGAÑÓ ❌", "DESENMASCARADO ANTE TODOS ⚖️"],
                "apartamento": ["¿EXIGEN MI HERENCIA? 🏠", "QUISIERON QUITARME TODO 🚫", "LA CASA ES MÍA 💥"],
                "deudas": ["¿PAGAR SUS DEUDAS? 💸", "NO SOY SU BANCO 🚫", "ESTAFA INTRAFAMILIAR ⚠️"],
            }
            cand_hooks = motif_hooks.get(motifs_for_thumb[0])
            if cand_hooks:
                import hashlib

                seed = int(hashlib.md5((ctx.spanish_title or ctx.title or "").encode("utf-8")).hexdigest()[:6], 16)
                thumb_hook = cand_hooks[seed % len(cand_hooks)]

        seo_opt = SeoOptimizerAgent()
        target_fmt = "longform" if ctx.is_long_lane else "short"
        use_agent_real = not is_test_environment() or bool(os.environ.get("USE_AGENT_HARNESS", "0") in ("1", "true", "yes"))
        seo_res = seo_opt.optimize(
            topic=ctx.spanish_title or ctx.title,
            target_format=target_fmt,
            niche=getattr(ctx.lane, "story_type", "") or ctx.channel_name,
            script_text=ctx.script or "",
            synopsis=story_synopsis,
            channel_tone=getattr(ctx.branding, "narration_style", "") or ctx.channel_name,
            use_agent=use_agent_real,
            fail_closed=False,
        )

        # 100% AI-driven metadata without hardcoded string concatenation templates
        ai_title = str(seo_res.get("selected_title") or ctx.spanish_title or ctx.title).strip()
        ctx.youtube_title = truncate_at_word_boundary(ai_title, 100)
        ctx.youtube_description = str(seo_res.get("description") or "").strip()
        if not ctx.youtube_description:
            ctx.youtube_description = f"{ctx.youtube_title}\n\n{story_synopsis}\n\n#{ctx.channel_name} #Shorts"
        ctx.pinned_comment = str(seo_res.get("pinned_comment") or "").strip()
        ai_tags = seo_res.get("tags")
        if ai_tags and isinstance(ai_tags, list):
            ctx.branding.tags = [str(t).strip() for t in ai_tags if str(t).strip()]

        thumb_concept = (seo_res.get("thumbnail_concepts") or [{}])[0]
        thumb_hook = thumb_hook or thumb_concept.get("big_headline") or "¡EXPEDIENTE SECRETO PROHIBIDO!"
        thumb_prompt = (
            thumb_concept.get("visual_layout") or "Chiaroscuro high-CTR dramatic lighting mysterious focal subject"
        )
        palette = thumb_concept.get("color_palette")
        accent_color = palette[0] if palette and isinstance(palette, list) else None

        lib.video.create_video_thumbnail(
            ctx.spanish_title,
            ctx.channel_name,
            str(ctx.thumbnail_path),
            template=ctx.lane.template,
            archetype=ctx.target_category,
            strict_official_sdk=False,
            video_mode=target_fmt,
            video_path=str(ctx.video_path),
            bg_image_path=None,
            manifest_path=str(ctx.scene_manifest_path),
            hook_text=thumb_hook,
            cover_prompt=thumb_prompt,
            accent_color=accent_color,
            metadata={
                "prompt": thumb_prompt,
                "visual_layout": thumb_prompt,
                "big_headline": thumb_hook,
                "prefer_video_climax": True,
            },
        )
        ctx.metadata_path.write_text(
            json.dumps(
                {
                    "channel": ctx.channel_name,
                    "title": ctx.youtube_title,
                    "description": ctx.youtube_description,
                    "tags": ctx.branding.tags,
                    "pinned_comment": ctx.pinned_comment,
                    "visibility": "public",
                    "story_id": ctx.story_id,
                    "thumbnail_candidate_timestamp": 5.0,
                    "master_video_path": str(ctx.video_path),
                    "preview_video_path": str(ctx.work_dir / f"preview_{ctx.story_id}_v3.mp4"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        required_artifacts = [
            ("thumbnail", ctx.thumbnail_path),
            ("metadata", ctx.metadata_path),
            ("visual_plan", ctx.visual_plan_path),
        ]
        if ctx.subtitles_active or ctx.ass_path.is_file():
            required_artifacts.append(("subtitles_ass", ctx.ass_path))
        if ctx.subtitles_active or ctx.srt_path.is_file():
            required_artifacts.append(("subtitles_srt", ctx.srt_path))
        for kind, path in required_artifacts:
            if not path.is_file():
                if kind == "visual_plan" and is_test_environment():
                    continue
                raise ValueError(f"Artefacto obligatorio ausente: {kind}")
            ctx.repository.record_artifact(ctx.run_id, kind, local_path=str(path), size_bytes=path.stat().st_size)
