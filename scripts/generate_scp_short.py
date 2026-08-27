"""
scripts/generate_scp_short.py - Production-Grade SCP-200 Vertical Short Generator & Telegram Dispatcher.

Generates a Full HD 1080x1920 (9:16) YouTube Short for SCP-200 ("Chrysalis") using:
- 4-Agent Specialized Pipeline (Curator, Art Director, Scene Planner, QA Auditor)
- Multi-Scene Dual-Engine Compositor (Hybrid Cinematic 2.5D + Pure Procedural WebGL)
- EdgeTTS voice synthesis with word-level timestamps
- Burned ASS karaoke subtitles formatted for vertical safe area (330px bottom margin)
- Lanczos 36-tap + De-band + EBU R128 audio mastering (-14 LUFS / -1.5 dBTP)
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import requests
from src.agents.script_curator import CinematicScriptCuratorAgent
from src.agents.art_director import ArtDirectorMoodAgent
from src.agents.scene_planner import ScenePlannerCompositorAgent
from src.agents.qa_auditor import VisualAudioQAAuditorAgent
from src.media.compositor import MultiSceneCompositor
from lib.tts import generate_audio
from lib.subtitles import create_ass_subtitles
from src.log import get_logger

logger = get_logger("scp_short_generator")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def generate_scp200_short():
    work_dir = ROOT_DIR / "work" / "scp_200_short_render"
    work_dir.mkdir(parents=True, exist_ok=True)

    logger.info("🧪 Iniciando generación de Short Vertical 1080x1920 para SCP-200...")

    scp_story_text = (
        "El sujeto SCP-200 parecía un niño completamente ordinario, hasta que comenzó a secretar seda biológica. "
        "En la celda de contención del Sector-19, el infante tejió una crisálida quitinosa impenetrable sellando su cámara. "
        "Los escáneres térmicos y de ultrasonido revelaron una aterradora metamorfosis: su estructura ósea se disolvía mientras nuevos apéndices crecían en su interior. "
        "A la cuarta semana de gestación, la crisálida emitió un pulso electromagnético masivo y la criatura que despertó ya no era humana."
    )

    # 1. Agente 1: Curador de Guion (Formato Short Vertical)
    curator = CinematicScriptCuratorAgent()
    script = curator.curate(
        raw_text=scp_story_text,
        title="SCP-200: La Crisálida Humana",
        channel_lane="moku-scp-shorts",
        target_format="short",
    )
    (work_dir / "cinematic_script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")

    # 2. Agente 2: Director de Arte & Mood (Temática SCP Foundation, Paleta Rec.709)
    art_agent = ArtDirectorMoodAgent()
    visual_plan = art_agent.plan_visuals(script, theme_lane="scp_foundation")
    (work_dir / "visual_plan.json").write_text(json.dumps(visual_plan, indent=2, ensure_ascii=False), encoding="utf-8")

    # 3. Síntesis de Audio con EdgeTTS (Voz oficial es-ES-AlvaroNeural)
    audio_path = work_dir / "narration.wav"
    logger.info("Sintetizando locución con EdgeTTS (es-ES-AlvaroNeural)...")
    
    clean_narration = " ".join([sc["narration_text"] for act in script["acts"] for sc in act["scenes"]])
    tts_result = generate_audio(
        script=clean_narration,
        audio_path=str(audio_path),
        channel="moku",
        lane_id="moku-scp-shorts",
        voice="es-ES-AlvaroNeural",
    )
    total_audio_dur = float(tts_result.get("duration_sec", 45.0))
    logger.info("Audio sintetizado: %.2f segundos (%d palabras con timestamps)", total_audio_dur, len(tts_result.get("word_timestamps", [])))

    from src.media.subtitles import THEME_PRESETS, CodeSubtitleDrawer
    from lib.tts import _word_timestamps_for

    word_timestamps = tts_result.get("word_timestamps", [])
    total_expected_words = len([w for w in clean_narration.split() if w.strip()])
    if not word_timestamps or len(word_timestamps) < max(6, total_expected_words // 2):
        word_timestamps = _word_timestamps_for(clean_narration, total_audio_dur)

    logger.info("Subtítulos por código: %d palabras sincronizadas para karaoke", len(word_timestamps))

    # 5. Agente 3: Scene Planner & Compositor (Manifiesto Canónico v2.0 Vertical)
    music_file = ROOT_DIR / "assets" / "music" / "horror_ambient.mp3"
    planner = ScenePlannerCompositorAgent()
    manifest = planner.plan_manifest(
        script=script,
        visual_plan=visual_plan,
        story_id="scp_200_chrysalis_short",
        narration_path=str(audio_path),
        music_path=str(music_file) if music_file.is_file() else "",
        lane_id="moku-scp-shorts",
        channel_name="moku",
        resolution=[1080, 1920],
        fps=30,
    )
    # Configure high-quality scenery assets and procedural CRT terminal
    bg_mapping = [
        str(ROOT_DIR / "assets/visual_bank/moku/scenery/scp_security_monitors.jpg"),
        str(ROOT_DIR / "assets/visual_bank/moku/scenery/scp_corridor.jpg"),
        str(ROOT_DIR / "assets/visual_bank/moku/scenery/scp_anomaly_cell.jpg"),
        str(ROOT_DIR / "assets/visual_bank/moku/scenery/scp_dark_stairs.jpg"),
    ]

    num_scenes = len(manifest["scenes"])
    per_scene_dur = round(total_audio_dur / max(1, num_scenes), 2)
    cum_t = 0.0
    pan_dirs = ["center_to_top", "left_to_right", "right_to_left", "center_to_bottom"]

    for idx, sc in enumerate(manifest["scenes"]):
        sc["start_sec"] = round(cum_t, 2)
        sc["duration_sec"] = per_scene_dur if idx < num_scenes - 1 else round(total_audio_dur - cum_t, 2)
        cum_t += sc["duration_sec"]

        if idx == 1:
            # Procedural CRT terminal wireframe
            sc["engine_type"] = "pure_procedural_webgl"
            sc["procedural_config"] = {
                "template_name": "scp_terminal_css.html",
                "seed": 200,
                "palette": {
                    "base_dark": "#020903",
                    "mid_tone": "#0a1f0f",
                    "accent": "#00ff66",
                },
                "uniforms": {
                    "u_noise_scale": 1.2,
                    "u_speed": 1.0,
                    "u_distortion": 0.4,
                    "u_glow_intensity": 0.85,
                },
            }
            sc.pop("hybrid_ai_config", None)
        else:
            sc["engine_type"] = "hybrid_cinematic_ai"
            bg_f = bg_mapping[idx % len(bg_mapping)]
            sc["hybrid_ai_config"] = {
                "background_image_path": bg_f,
                "camera_motion": {
                    "type": "ken_burns_3d",
                    "start_zoom": 1.0,
                    "end_zoom": round(1.06 + 0.02 * sc.get("tension_level", 3), 3),
                    "pan_direction": pan_dirs[idx % len(pan_dirs)],
                    "easing": "cubic_bezier",
                    "parallax_intensity": 0.2,
                },
                "lighting": {
                    "volumetric_rays": idx in (2, 3),
                    "light_source_pos": [0.5, 0.2],
                    "intensity": 0.35,
                    "flicker_frequency": 3.0 if idx == 3 else 0.0,
                    "color_tint": "#00ff66" if idx < 3 else "#ff3300",
                },
                "particles": {
                    "type": "ember_sparks" if idx == 3 else "dust_motes",
                    "density": 30,
                    "velocity": 1.2,
                    "color": "#00ff88",
                    "opacity": 0.4,
                },
            }
            sc.pop("procedural_config", None)

    manifest["total_duration_sec"] = round(total_audio_dur, 2)
    manifest["audio_tracks"]["music_volume"] = 0.14

    manifest_path = work_dir / "scene_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # 6. Renderizado Master con MultiSceneCompositor
    output_short = work_dir / "scp_200_chrysalis_short_1080x1920.mp4"
    compositor = MultiSceneCompositor()
    logger.info("Iniciando renderizado de alta fidelidad 1080x1920 con MultiSceneCompositor...")
    render_res = compositor.render(
        manifest_path=manifest_path,
        output_video_path=output_short,
        crf=18,
        preset="fast",
        word_timestamps=word_timestamps,
        subtitle_theme=THEME_PRESETS["scp_neon"],
    )
    logger.info("Short renderizado con éxito: %s (%.2f MB)", output_short, output_short.stat().st_size / (1024 * 1024))

    # 7. Agente 4: Auditor QA Visual & Audio
    auditor = VisualAudioQAAuditorAgent()
    qa_report = auditor.audit_video(
        video_path=output_short,
        run_id="run_scp_200_qa_001",
        target_resolution="1080x1920",
    )
    (work_dir / "qa_report.json").write_text(json.dumps(qa_report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Reporte QA: Pass=%s, Score=%d", qa_report["overall_pass"], qa_report["quality_score"])

    # 8. Despacho a Telegram
    logger.info("Enviando Short SCP-200 a Telegram...")
    caption = (
        f"📱 *Short Vertical 9:16 Generado — SCP-200: La Crisálida*\n\n"
        f"🔬 *Item*: SCP-200 (Clasificación: Seguro / Metamórfico)\n"
        f"📐 *Resolución*: 1080x1920 @ 30fps (Full HD Vertical)\n"
        f"🎨 *Estilo*: Terminal SCP Foundation (Rec.709, Iluminación de Alerta)\n"
        f"⏱️ *Duración*: {total_audio_dur:.1f}s en 4 escenas dinámicas\n"
        f"📝 *Subtítulos*: Quemados en área segura (330px margen inferior)\n"
        f"🔊 *Audio*: EBU R128 (-14.0 LUFS) + Sidechain Ducking (-18 dB)\n"
        f"🏆 *QA Score*: {qa_report['quality_score']}/100 ({'✅ Aprobado' if qa_report['overall_pass'] else '⚠️ Observaciones'})\n\n"
        f"🚀 _Pipeline Multi-Escena Dual-Engine Activo_"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    with open(output_short, "rb") as video_file:
        files = {"video": video_file}
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": caption,
            "parse_mode": "Markdown",
            "supports_streaming": True,
            "width": 1080,
            "height": 1920,
        }
        resp = requests.post(url, data=data, files=files, timeout=300)
        logger.info("Respuesta Telegram: Status %d - %s", resp.status_code, resp.text[:200])

    if resp.status_code == 200:
        print("SUCCESS_SCP_SHORT_DISPATCH")
    else:
        print(f"FAILED_SCP_SHORT_DISPATCH: {resp.text}")


if __name__ == "__main__":
    generate_scp200_short()
