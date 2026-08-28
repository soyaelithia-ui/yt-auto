#!/usr/bin/env python3
"""
dev/generate_two_videos.py - Generates two completely independent productions:
1. Short Vertical (1080x1920) via moku-scp-shorts
2. Longform Horizontal (1920x1080) via moku-horror-long
Using the Universal Adaptive Visual Archetypes and MultiSceneCompositor.
"""
import json
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure Playwright finds its browsers
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

from lib.tts import generate_audio
from src.agents.art_director import ArtDirectorMoodAgent
from src.agents.scene_planner import ScenePlannerCompositorAgent
from src.agents.script_curator import CinematicScriptCuratorAgent
from src.media.compositor import MultiSceneCompositor
from src.media.procedural_audio import ProceduralAudioEngine
from lib.ffmpeg import probe_media


def generate_short_video(output_dir: Path) -> Path:
    print("\n" + "=" * 80)
    print("🎬 INICIANDO PRODUCCIÓN 1: SHORT VERTICAL (1080x1920)")
    print("=" * 80)

    work_dir = output_dir / "work_short"
    work_dir.mkdir(parents=True, exist_ok=True)
    out_video = output_dir / "showcase_short_vertical.mp4"

    raw_script_text = (
        "03:42 AM. Sensor hidroacústico del Faro catorce activado en la Fosa Mariana. "
        "Anomalía no biológica detectada a ochocientos metros de profundidad. "
        "Los mamparos de contención registraron una variación de presión crítica del cuatrocientos por ciento. "
        "El análisis espectral confirma que una silueta colosal ha emergido del abismo."
    )

    # 1. Generate Voice Narration
    narration_wav = work_dir / "narration.wav"
    print(f"🎙️ Generando locución TTS con perfil solemne...")
    tts_res = generate_audio(
        script=raw_script_text,
        audio_path=str(narration_wav),
        voice="es-ES-AlvaroNeural",
        rate="+0%",
        pitch="-2Hz",
    )
    audio_dur = float(tts_res.get("duration_sec", 15.0))
    print(f"✅ Locución sintetizada: {audio_dur:.2f}s ({narration_wav.name})")

    # 2. Generate Procedural Background Soundscape
    ambient_wav = work_dir / "ambient.wav"
    audio_engine = ProceduralAudioEngine(sample_rate=48000)
    audio_engine.generate_ambient_track(
        output_path=ambient_wav,
        theme="scp",
        duration_sec=audio_dur + 2.0,
        volume=0.20,
        seed=101,
    )
    print(f"✅ Audio ambiental táctico/SCP generado ({ambient_wav.name})")

    # 3. Agents Pipeline
    curator = CinematicScriptCuratorAgent()
    art_director = ArtDirectorMoodAgent()
    planner = ScenePlannerCompositorAgent()

    script_payload = curator.curate(
        raw_text=raw_script_text,
        title="Incidente en el Faro de la Fosa 14",
        channel_lane="moku-scp-shorts",
        target_format="short",
    )
    (work_dir / "cinematic_script.json").write_text(json.dumps(script_payload, indent=2, ensure_ascii=False))
    print(f"✅ Guion cinemático curado: {len(script_payload.get('acts', []))} acto(s)")

    visual_plan = art_director.plan_visuals(
        cinematic_script=script_payload,
        theme_lane="scp_foundation",
    )
    (work_dir / "visual_plan.json").write_text(json.dumps(visual_plan, indent=2, ensure_ascii=False))
    print(f"✅ Plan visual prémium generado con paleta Rec.709")

    manifest = planner.plan_manifest(
        script=script_payload,
        visual_plan=visual_plan,
        story_id="showcase_short_001",
        narration_path=str(narration_wav),
        music_path=str(ambient_wav),
        music_volume=0.18,
        lane_id="moku-scp-shorts",
        channel_name="moku",
        resolution=[1080, 1920],
        fps=30,
        actual_audio_duration=audio_dur,
    )
    manifest_path = work_dir / "scene_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"✅ Scene Manifest V2 generado con {len(manifest['scenes'])} escenas:")
    for sc in manifest["scenes"]:
        tmpl = sc.get("procedural_config", {}).get("template_name", "none")
        print(f"   - {sc['scene_id']}: {tmpl} (dur={sc['duration_sec']}s)")

    # 4. Render Video via MultiSceneCompositor
    print(f"🎥 Renderizando Short Vertical a 1080x1920...")
    compositor = MultiSceneCompositor()
    compositor.render(
        manifest_path=manifest_path,
        output_video_path=out_video,
        crf=18,
        preset="fast",
    )
    print(f"🎉 Short Vertical completado con éxito: {out_video}")
    return out_video


def generate_longform_video(output_dir: Path) -> Path:
    print("\n" + "=" * 80)
    print("🎬 INICIANDO PRODUCCIÓN 2: VIDEO LARGO HORIZONTAL (1920x1080)")
    print("=" * 80)

    work_dir = output_dir / "work_long"
    work_dir.mkdir(parents=True, exist_ok=True)
    out_video = output_dir / "showcase_longform_horizontal.mp4"

    raw_script_text = (
        "Caminé durante tres días a través de la estepa de cenizas grises. "
        "En el horizonte infinito, los monolitos oscuros parecían absorber la poca luz que quedaba en el mundo. "
        "Alcanzar el búnker subterráneo de la estación cuarenta y nueve fue un alivio efímero; "
        "la pesada compuerta de acero blindado había sido sellada desde el interior con soldadura térmica. "
        "Dentro de la cámara principal, los monitores no registraban radiación sino pulsos de actividad sináptica consciente. "
        "La estructura completa latía como una mente colosal bajo tierra. "
        "Frente a la consola central, el espacio se fracturó en una singularidad gravitacional perfecta. "
        "Comprendí entonces que la estación nunca fue un refugio para protegernos, sino un portal hacia el vacío absoluto."
    )

    # 1. Generate Voice Narration
    narration_wav = work_dir / "narration.wav"
    print(f"🎙️ Generando locución TTS con cadencia pausada y grave...")
    tts_res = generate_audio(
        script=raw_script_text,
        audio_path=str(narration_wav),
        voice="es-ES-AlvaroNeural",
        rate="-2%",
        pitch="-3Hz",
    )
    audio_dur = float(tts_res.get("duration_sec", 42.0))
    print(f"✅ Locución sintetizada: {audio_dur:.2f}s ({narration_wav.name})")

    # 2. Generate Procedural Background Soundscape
    ambient_wav = work_dir / "ambient.wav"
    audio_engine = ProceduralAudioEngine(sample_rate=48000)
    audio_engine.generate_ambient_track(
        output_path=ambient_wav,
        theme="cosmic_horror",
        duration_sec=audio_dur + 2.0,
        volume=0.22,
        seed=202,
    )
    print(f"✅ Audio ambiental de Horror Cósmico generado ({ambient_wav.name})")

    # 3. Agents Pipeline
    curator = CinematicScriptCuratorAgent()
    art_director = ArtDirectorMoodAgent()
    planner = ScenePlannerCompositorAgent()

    script_payload = curator.curate(
        raw_text=raw_script_text,
        title="La Travesía por el Páramo de los Monolitos Silentes",
        channel_lane="moku-horror-long",
        target_format="longform",
    )
    (work_dir / "cinematic_script.json").write_text(json.dumps(script_payload, indent=2, ensure_ascii=False))
    print(f"✅ Guion cinemático curado: {len(script_payload.get('acts', []))} acto(s)")

    visual_plan = art_director.plan_visuals(
        cinematic_script=script_payload,
        theme_lane="cosmic_horror",
    )
    (work_dir / "visual_plan.json").write_text(json.dumps(visual_plan, indent=2, ensure_ascii=False))
    print(f"✅ Plan visual prémium generado con paleta Chiaroscuro")

    manifest = planner.plan_manifest(
        script=script_payload,
        visual_plan=visual_plan,
        story_id="showcase_longform_002",
        narration_path=str(narration_wav),
        music_path=str(ambient_wav),
        music_volume=0.18,
        lane_id="moku-horror-long",
        channel_name="moku",
        resolution=[1920, 1080],
        fps=30,
        actual_audio_duration=audio_dur,
    )
    manifest_path = work_dir / "scene_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"✅ Scene Manifest V2 generado con {len(manifest['scenes'])} escenas:")
    for sc in manifest["scenes"]:
        tmpl = sc.get("procedural_config", {}).get("template_name", "none")
        print(f"   - {sc['scene_id']}: {tmpl} (dur={sc['duration_sec']}s)")

    # 4. Render Video via MultiSceneCompositor
    print(f"🎥 Renderizando Video Largo Horizontal a 1920x1080...")
    compositor = MultiSceneCompositor()
    compositor.render(
        manifest_path=manifest_path,
        output_video_path=out_video,
        crf=18,
        preset="fast",
    )
    print(f"🎉 Video Largo Horizontal completado con éxito: {out_video}")
    return out_video


def main():
    out_base = PROJECT_ROOT / "output" / "showcase"
    out_base.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    v1 = generate_short_video(out_base)
    v2 = generate_longform_video(out_base)
    total_time = time.time() - t0

    print("\n" + "=" * 80)
    print("🏆 AMBAS PRODUCCIONES FINALIZADAS CON ÉXITO")
    print(f"⏱️ Tiempo total de renderizado y masterización: {total_time:.1f}s")
    print("=" * 80)

    for v in [v1, v2]:
        meta = probe_media(v)
        w = getattr(meta, "width", None) or (meta.get("width") if isinstance(meta, dict) else "?")
        h = getattr(meta, "height", None) or (meta.get("height") if isinstance(meta, dict) else "?")
        dur = getattr(meta, "duration_sec", None) or getattr(meta, "duration", None) or 0.0
        print(f"📁 Video: {v}")
        print(f"   - Tamaño: {v.stat().st_size / (1024 * 1024):.2f} MB")
        print(f"   - Resolución: {w}x{h}")
        print(f"   - Duración: {dur:.2f}s")
        print()


if __name__ == "__main__":
    main()
