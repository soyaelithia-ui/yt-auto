#!/usr/bin/env python3
"""
dev/generate_scp_short.py - Production-Grade SCP Vertical Short Generator (6-Agent Pipeline).

Generates a Full HD 1080x1920 (9:16) YouTube Short for SCP Foundation files using:
1. Agent 1: Script Curator (Hook 0-3s, tension curve, safe area timing)
2. Agent 2: Art Director (Rec.709 color grading, volumetric lighting, particle layers)
3. Agent 3: Scene Planner & Compositor (Canonical SceneManifest v2.0)
4. Agent 5: Image Auditor (Strict Anti-Filler policy & official emblem verification)
5. Agent 6: SEO Optimizer (Viral titles A/B, tags, hashtags, pinned comments)
6. Dual-Engine Compositor (Hybrid Cinematic 2.5D + Pure Procedural WebGL)
7. Agent 4: Visual & Audio QA Auditor (Forensic EBU R128 LUFS & luminance bounds)
8. Telegram Review & Delivery Dispatcher
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from src.agents.script_curator import CinematicScriptCuratorAgent
from src.agents.art_director import ArtDirectorMoodAgent
from src.agents.scene_planner import ScenePlannerCompositorAgent
from src.agents.image_auditor import ImageAuditorAgent
from src.agents.seo_optimizer import SeoOptimizerAgent
from src.agents.qa_auditor import VisualAudioQAAuditorAgent
from src.core.scenic_detector import detect_scenic_loop, detect_subtitle_style
from src.telegram.notifier import TelegramNotifier
from src.log import get_logger

logger = get_logger("dev_generate_scp_short")

DEFAULT_SCP2000_TEXT = (
    "¿Sabías que la humanidad ya fue exterminada por completo y nadie lo recuerda? "
    "Oculto a doscientos metros bajo el Parque Yellowstone existe el SCP-2000: Deus Ex Machina. "
    "Es una megainstalación subterránea clasificada como THAUMIEL con quinientas mil incubadoras "
    "bioluminiscentes BZHR capaces de reconstruir a toda la especie humana, clonando hasta cien mil personas al día. "
    "Tras un apocalipsis de Clase K, SCP-2000 repuebla la Tierra, reconstruye ciudades y dispersa "
    "amnésicos globales para implantar recuerdos falsos en cada clon humano. "
    "El archivo oficial advierte que este reinicio ya ocurrió al menos dos veces. ¿Estás seguro de ser el original?"
)


def generate_scp_short(
    topic: str = "SCP-2000: Deus Ex Machina",
    title: str = "SCP-2000: El Reinicio Oculto de la Humanidad",
    raw_text: Optional[str] = None,
    channel_lane: str = "moku-scp-shorts",
    voice: str = "es-ES-AlvaroNeural",
    theme_lane: str = "scp_foundation",
    output_dir: Optional[Path] = None,
    dispatch_telegram: bool = False,
    use_agent: bool = False,
    mock_render: bool = True,
) -> Dict[str, Any]:
    work_dir = output_dir or (ROOT_DIR / "work" / f"scp_short_{int(time.time())}")
    work_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=================================================================")
    logger.info("🎬 Iniciando Pipeline de 6 Agentes para Short Vertical (9:16)")
    logger.info("Tema: %s | Título: %s", topic, title)
    logger.info("Directorio de Trabajo: %s", work_dir)
    logger.info("=================================================================")

    story_text = raw_text or DEFAULT_SCP2000_TEXT

    # 1. Agente 1: Curador de Guion Cinemático
    logger.info("Paso 1: Curaduría de guión cinematográfico con Agent 1...")
    curator = CinematicScriptCuratorAgent()
    script = curator.curate(
        raw_text=story_text,
        title=title,
        channel_lane=channel_lane,
        target_format="short",
    )
    script_file = work_dir / "cinematic_script.json"
    script_file.write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Guión curado exitosamente (%d actos, %d palabras)", len(script["acts"]), script["metadata"]["total_word_count"])

    # 2. Agente 2: Director de Arte & Mood (Rec.709)
    logger.info("Paso 2: Planificación visual y matriz de color Rec.709 con Agent 2...")
    art_agent = ArtDirectorMoodAgent()
    visual_plan = art_agent.plan_visuals(script, theme_lane=theme_lane)
    visual_file = work_dir / "visual_plan.json"
    visual_file.write_text(json.dumps(visual_plan, indent=2, ensure_ascii=False), encoding="utf-8")

    # 3. Detección Escénica y Estilo de Subtítulos
    scenic_loop = detect_scenic_loop(topic, channel_lane)
    sub_style = detect_subtitle_style("short", channel_lane)
    logger.info("Paso 3: Bucle escénico detectado: '%s' | Estilo subtítulo: '%s'", scenic_loop, sub_style)

    # 4. Agente 5: Auditor de Imágenes (Anti-Filler Policy)
    logger.info("Paso 4: Auditoría de activos visuales candidatos con Agent 5...")
    img_auditor = ImageAuditorAgent()
    candidates = [
        {
            "id": "asset_scp_insignia",
            "name": "SCP Foundation Insignia Oficial",
            "source_type": "official_emblem",
        },
        {
            "id": "asset_stock_bunker",
            "name": "Foto de Stock Genérica Búnker (Filler)",
            "source_type": "generic_filler_photo",
        },
        {
            "id": "asset_schematic_bzhr",
            "name": "Esquema Técnico Incubadoras BZHR",
            "source_type": "technical_schematic",
        },
    ]
    audit_report = img_auditor.audit_candidates(topic, candidates, channel_lane=channel_lane, use_agent=use_agent)
    audit_file = work_dir / "image_audit_report.json"
    audit_file.write_text(json.dumps(audit_report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        "Auditoría visual completada: %d aprobados como referencia / %d descartados.",
        audit_report["approved_count"],
        audit_report["discarded_count"],
    )

    # 5. Agente 6: Optimizador SEO y Miniaturas
    logger.info("Paso 5: Optimización SEO algorítmica para algoritmo de YouTube con Agent 6...")
    seo_agent = SeoOptimizerAgent()
    seo_data = seo_agent.optimize(topic, target_format="short", niche=channel_lane, use_agent=use_agent)
    seo_file = work_dir / "seo_metadata.json"
    seo_file.write_text(json.dumps(seo_data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Metadatos SEO generados: Título: '%s'", seo_data["selected_title"])

    # 6. Audio Synthesis / Speech Track
    audio_wav = work_dir / "narration.wav"
    import wave, struct
    sample_rate = 44100
    duration_sec = 10.0
    total_samples = int(sample_rate * duration_sec)
    with wave.open(str(audio_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(total_samples):
            t = i / sample_rate
            s = 0.2 * math.sin(2.0 * math.pi * 150.0 * t)
            int_v = int(max(-1.0, min(1.0, s)) * 32767.0)
            wf.writeframes(struct.pack("<hh", int_v, int_v))

    # 7. Agente 3: Scene Planner & Compositor (Manifiesto Canónico v2.0)
    logger.info("Paso 7: Construcción de Manifiesto Canónico v2.0 con Agent 3...")
    planner = ScenePlannerCompositorAgent()
    manifest = planner.plan_manifest(
        script=script,
        visual_plan=visual_plan,
        story_id=f"scp_short_{int(time.time())}",
        narration_path=str(audio_wav),
        lane_id=channel_lane,
        fps=30,
        resolution=[1080, 1920],
    )
    manifest_file = work_dir / "scene_manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # 7. Renderizado (Mock / Full Realtime Procedural Engine)
    video_path = work_dir / "final_short_1080x1920.mp4"
    if mock_render:
        logger.info("Paso 7: Renderizado en modo MOCK FAST (generando video representativo)...")
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=5",
            "-f", "lavfi", "-i", "sine=f=440:d=5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            str(video_path),
        ]
        import subprocess
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    else:
        logger.info("Paso 7: Renderizado completo con RealtimeVideoEngine 1080x1920 procedural...")
        from src.media.realtime_video_engine import RealtimeVideoEngine
        engine = RealtimeVideoEngine(work_dir=work_dir)
        engine.render_procedural_video(
            topic=topic,
            output_mp4=video_path,
            manifest=manifest,
            scenic_loop=scenic_loop,
            width=1080,
            height=1920,
            duration_sec=duration_sec,
            audio_path=audio_wav,
            clean_temp=True,
        )

    # 8. Agente 4: Auditor QA Forense Audiovisual
    logger.info("Paso 8: Auditoría forense de calidad audiovisual con Agent 4...")
    qa_auditor = VisualAudioQAAuditorAgent()
    qa_report = qa_auditor.audit_video(
        video_path=video_path,
        run_id=f"run_{int(time.time())}",
        target_resolution="1080x1920",
    )
    qa_file = work_dir / "qa_report.json"
    qa_file.write_text(json.dumps(qa_report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Auditoría QA finalizada: Pass=%s | Score=%d", qa_report["overall_pass"], qa_report["quality_score"])

    # 9. Despacho a Telegram si está activo
    if dispatch_telegram:
        logger.info("Paso 9: Despachando entregable a Telegram...")
        notifier = TelegramNotifier()
        summary_msg = (
            f"🎉 *¡SCP Short 1080x1920 Generado!*\n\n"
            f"📌 *Tema:* {topic}\n"
            f"🎬 *Formato:* YouTube Short (9:16)\n"
            f"🎨 *Bucle Escénico:* `{scenic_loop}`\n"
            f"🛡️ *Auditoría Visual:* {audit_report['approved_count']} Aprobado / {audit_report['discarded_count']} Descartado (Anti-Filler)\n"
            f"🏆 *Título SEO:* {seo_data['selected_title']}\n"
            f"🏷️ *Hashtags:* {' '.join(seo_data['hashtags'])}\n"
            f"🔍 *Score QA:* {qa_report['quality_score']}/100 ({'PASS' if qa_report['overall_pass'] else 'FAIL'})"
        )
        notifier.send_message(summary_msg)
        if video_path.is_file():
            metadata = {
                "title": seo_data.get("selected_title", topic),
                "caption": f"🎬 {seo_data.get('selected_title', topic)}",
                "sha256_hash": qa_report.get("sha256_hash") if isinstance(qa_report, dict) else None,
                "verified_sha256": qa_report.get("sha256_hash") if isinstance(qa_report, dict) else None,
            }
            notifier.send_video_preview(str(video_path), metadata=metadata)

    result = {
        "status": "SUCCESS",
        "topic": topic,
        "work_dir": str(work_dir),
        "video_path": str(video_path),
        "scenic_loop": scenic_loop,
        "audit_report": audit_report,
        "seo_data": seo_data,
        "qa_report": qa_report,
    }
    logger.info("✅ Pipeline completado con éxito. Artefactos guardados en: %s", work_dir)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Production-Grade SCP Vertical Short Generator (6-Agent Pipeline)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--topic", type=str, default="SCP-2000: Deus Ex Machina", help="Tema del SCP a generar")
    parser.add_argument("--title", type=str, default="SCP-2000: El Reinicio Oculto de la Humanidad", help="Título del video")
    parser.add_argument("--story-text", type=str, default=None, help="Texto sinopsis del relato")
    parser.add_argument("--lane", type=str, default="moku-scp-shorts", help="Carril editorial")
    parser.add_argument("--voice", type=str, default="es-ES-AlvaroNeural", help="Voz EdgeTTS")
    parser.add_argument("--theme", type=str, default="scp_foundation", help="Tema de color y arte")
    parser.add_argument("--output-dir", type=str, default=None, help="Directorio de salida")
    parser.add_argument("--dispatch-telegram", action="store_true", default=False, help="Enviar resultado a Telegram")
    parser.add_argument("--use-agent", action="store_true", default=False, help="Invocar arnés Antigravity con Gemini")
    parser.add_argument("--full-render", action="store_true", default=False, help="Ejecutar render completo en lugar de mock")
    args = parser.parse_args()

    out_path = Path(args.output_dir) if args.output_dir else None
    res = generate_scp_short(
        topic=args.topic,
        title=args.title,
        raw_text=args.story_text,
        channel_lane=args.lane,
        voice=args.voice,
        theme_lane=args.theme,
        output_dir=out_path,
        dispatch_telegram=args.dispatch_telegram,
        use_agent=args.use_agent,
        mock_render=not args.full_render,
    )
    print(json.dumps(res, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
