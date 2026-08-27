"""
scripts/test_render_and_send_telegram.py - Multi-Scene Dual-Engine Test Video Generator & Telegram Dispatcher.
"""
from __future__ import annotations

import json
import math
import os
import struct
import sys
import time
import wave
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
from src.log import get_logger

logger = get_logger("telegram_test_render")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def generate_ambient_speech_audio(wav_path: Path, duration_sec: float = 60.0) -> Path:
    """Generates an atmospheric multi-tone synth speech mockup for testing."""
    sample_rate = 44100
    total_samples = int(sample_rate * duration_sec)
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        
        for i in range(total_samples):
            t = i / sample_rate
            # Voice simulation formant frequencies (150Hz base, 800Hz / 1200Hz formants)
            f0 = 130.0 + 15.0 * math.sin(2.0 * math.pi * 0.3 * t)
            mod = 0.5 + 0.5 * math.sin(2.0 * math.pi * 2.5 * t)  # Speech cadence rhythm
            
            s1 = 0.3 * math.sin(2.0 * math.pi * f0 * t)
            s2 = 0.15 * math.sin(2.0 * math.pi * (f0 * 3.2) * t)
            s3 = 0.08 * math.sin(2.0 * math.pi * 850.0 * t)
            
            sample_val = (s1 + s2 + s3) * mod * 0.7
            int_val = int(max(-1.0, min(1.0, sample_val)) * 32767.0)
            wf.writeframes(struct.pack("<hh", int_val, int_val))
            
    return wav_path


def main():
    work_dir = ROOT_DIR / "work" / "telegram_multiscene_demo"
    work_dir.mkdir(parents=True, exist_ok=True)

    logger.info("🚀 Iniciando generación de video Multi-Escena Dual-Engine Prémium 1080p...")

    story_text = (
        "En la costa olvidada de Cabo Tormenta, el faro victoriano de piedra negra se alzaba contra un océano embravecido. "
        "Durante generaciones, los pescadores evitaron sus riscos cuando el agua adquiría un brillo esmeralda bioluminiscente. "
        "A las tres de la madrugada, un pulso electromagnético apagó los sistemas de la costa mientras un eclipse cósmico cubría el cielo. "
        "Colosales siluetas con tentáculos titánicos emergieron del vórtice estelar entre las olas turbulentas. "
        "La linterna del faro giraba a trescientos sesenta grados emitiendo haces volumétricos que atravesaban la densa niebla marina."
    )

    # 1. Agente 1: Curador de Guion Cinemático (4 Actos)
    curator = CinematicScriptCuratorAgent()
    script = curator.curate(
        raw_text=story_text,
        title="El Faro de Terror Cósmico: Pesadilla en el Vórtice Abisal",
        channel_lane="moku-horror-long",
        target_format="longform",
    )
    # Target 4 scenes with 15s each = 60s total demo master
    for act in script["acts"]:
        for sc in act["scenes"]:
            sc["estimated_duration_sec"] = 15.0

    (work_dir / "cinematic_script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")

    # 2. Agente 2: Director de Arte & Mood (Rec.709, Iluminación Volumétrica)
    art_agent = ArtDirectorMoodAgent()
    visual_plan = art_agent.plan_visuals(script, theme_lane="cosmic_horror")
    (work_dir / "visual_plan.json").write_text(json.dumps(visual_plan, indent=2, ensure_ascii=False), encoding="utf-8")

    # 3. Generar pista de audio
    audio_wav = work_dir / "narration.wav"
    generate_ambient_speech_audio(audio_wav, duration_sec=60.0)

    # 4. Agente 3: Scene Planner & Compositor (Manifiesto Canónico v2.0)
    planner = ScenePlannerCompositorAgent()
    manifest = planner.plan_manifest(
        script=script,
        visual_plan=visual_plan,
        story_id="cosmic_lighthouse_v2_demo",
        narration_path=str(audio_wav),
        lane_id="moku-horror-long",
        channel_name="moku",
        resolution=[1920, 1080],
        fps=30,
    )
    manifest_path = work_dir / "scene_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # 5. Renderizado con MultiSceneCompositor (Dual-Engine: Hybrid AI + Procedural WebGL)
    output_video = work_dir / "moku_cosmic_lighthouse_multiscene_1080p.mp4"
    compositor = MultiSceneCompositor()
    render_res = compositor.render(
        manifest_path=manifest_path,
        output_video_path=output_video,
        crf=18,
        preset="fast",
    )
    logger.info("Video renderizado con éxito: %s (%.2f MB)", output_video, output_video.stat().st_size / (1024 * 1024))

    # 6. Agente 4: Auditor QA Visual & Audio
    auditor = VisualAudioQAAuditorAgent()
    qa_report = auditor.audit_video(
        video_path=output_video,
        run_id="run_telegram_demo_001",
        target_resolution="1920x1080",
    )
    (work_dir / "qa_report.json").write_text(json.dumps(qa_report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Reporte QA: Pass=%s, Score=%d", qa_report["overall_pass"], qa_report["quality_score"])

    # 7. Despacho a Telegram
    logger.info("Enviando video master Full HD a Telegram...")
    caption = (
        f"🎬 *Video Prémium Multi-Escena 1080p Generado*\n\n"
        f"🔹 *Historia*: {script['metadata']['title']}\n"
        f"🔹 *Resolución*: 1920x1080 @ 30fps (Rec.709)\n"
        f"🔹 *Motores*: Híbrido Cinemático 2.5D + Procedural WebGL\n"
        f"🔹 *Escenas*: {len(manifest['scenes'])} escenas con ritmo dinámico (15s/escena)\n"
        f"🔹 *Posprocesamiento*: Lanczos 36-tap + De-band + EBU R128 (-14 LUFS)\n"
        f"🔹 *QA Score*: {qa_report['quality_score']}/100 ({'✅ Aprobado' if qa_report['overall_pass'] else '⚠️ Observaciones'})\n\n"
        f"⚡ _Generado con el nuevo pipeline de 4 agentes especializados_"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    with open(output_video, "rb") as video_file:
        files = {"video": video_file}
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": caption,
            "parse_mode": "Markdown",
            "supports_streaming": True,
        }
        resp = requests.post(url, data=data, files=files, timeout=300)
        logger.info("Respuesta Telegram: Status %d - %s", resp.status_code, resp.text[:200])

    if resp.status_code == 200:
        print("SUCCESS_TELEGRAM_DISPATCH")
    else:
        print(f"FAILED_TELEGRAM_DISPATCH: {resp.text}")


if __name__ == "__main__":
    main()
