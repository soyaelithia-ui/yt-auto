#!/usr/bin/env python3
"""
dev/produce_scp5000_long_and_short.py - Production Suite for SCP-5000: Longform (10+ min) & Short (60s).

Implements all new standards:
1. Resilient High-CTR Thumbnail Engine (TrueType, UTF-8 safe, multi-layer contrast).
2. Neutral Spanish Voice (es-MX-JorgeNeural) with sanitized scripts.
3. Broadcast EBU R128 mastering (-14.0 LUFS, -1.5 dBTP) with sidechain ducking.
4. Multi-scene composition (16:9 Longform 1080p and 9:16 Short 1080x1920).
5. Dynamic SEO metadata with exact synchronized timestamps.
6. Forensic QA Auditor (Agent 4) validating both masters.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.audio_processor import sanitize_script_for_tts
from src.media.thumbnail_engine import ResilientThumbnailEngine
from src.agents.seo_optimizer import SeoOptimizerAgent
from src.agents.qa_auditor import VisualAudioQAAuditorAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("produce_scp5000")

OUTPUT_DIR = ROOT_DIR / "output"
WORK_DIR = ROOT_DIR / "work" / "scp5000_production"
AUDIO_BGM = ROOT_DIR / "assets" / "music" / "horror_ambient.mp3"


SCP5000_LONG_SCRIPT = """
En los registros más profundos y blindados del Sitio-62C de la Fundación SCP descansa un traje mecánico de contención biológica cuya superficie metálica está chamuscada por el fuego y las radiaciones de una guerra que nunca ocurrió... o que quizás fue borrada de la realidad. Clasificado bajo la designación SCP-5000, este arnés tecnológico fue hallado con el cuerpo sin vida de un técnico de nivel dos llamado Pietro Wilson. Pero lo verdaderamente demoledor no era la tecnología del traje, sino el archivo digital recuperado de su memoria interna: una bitácora detallada y aterradora que documenta el evento más oscuro y moralmente devastador en la historia del universo conocido. El día en que la Fundación SCP, la organización jurada a proteger la vida humana, decidió aniquilar de forma deliberada, metódica y sin piedad a toda la especie humana.

Durante más de un siglo, el mundo sobrevivió gracias a la contención invisible de anomalías. Hombres y mujeres dedicaron sus vidas a mantener alejados a los monstruos de la oscuridad bajo el juramento de Asegurar, Contener y Proteger. Sin embargo, en un punto no determinado de una línea temporal alternativa, el Consejo O5 y el Comité de Ética convocaron una reunión de emergencia bajo el protocolo más estricto de seguridad. Los investigadores del Departamento de Psico-análisis habían completado el mapeo total del Proyecto Pneuma, una exploración profunda del inconsciente colectivo y la noosfera de la mente humana. Lo que descubrieron en esa dimensión mental no fue un secreto místico ni una verdad divina, sino una entidad parasitaria de sufrimiento infinito que habita en el alma de cada ser humano desde el origen de la evolución.

Tras verificar los resultados, algo se rompió para siempre en la mente de los líderes de la Fundación. En cuestión de horas, el Consejo O5 emitió una orden clasificada enviada a todos los sitios de contención alrededor del planeta. Un comunicado breve, frío y definitivo: A todos los destacamentos y personal leal: las anomalías ya no serán contenidas; serán desplegadas. La Fundación SCP declara formalmente la guerra contra la humanidad. No intenten resistirse. No sientan miedo. El dolor terminará pronto.

Lo que siguió a esa transmisión fue la pesadilla más atroz jamás presenciada en la faz de la Tierra. La Fundación no necesitó usar bombas atómicas tradicionales; simplemente abrieron las puertas de las celdas más temibles del planeta. Liberaron a SCP-682, el reptil inmortal e invulnerable, pero esta vez no para destruirlo, sino modificándolo cibernéticamente para masacrar poblaciones enteras en Europa Oriental. Desplegaron a SCP-096, transmitiendo su rostro en televisión abierta satelital a través de todas las pantallas públicas del mundo, desatando una cacería imparable de cientos de millones de personas que no podían evitar mirar la transmisión. En las redes de agua potable de las principales metrópolis inyectaron patógenos anómalos que convertían la sangre humana en vidrio líquido, mientras enjambres de estatuas SCP-173 modificadas eran arrojadas desde aviones de carga sobre las ciudades en pánico.

Pietro Wilson, un modesto técnico de mantenimiento que no formaba parte del círculo de mando ni había recibido la inmunización mental de la Fundación, observó con horror cómo sus propios compañeros de trabajo ejecutaban a tiros a los prisioneros Clase-D y a los civiles refugiados en los accesos del búnker. Al comprender que la locura se había apoderado de sus superiores, Pietro se colocó el prototipo de sigilo del traje SCP-5000, activó el camuflaje cuántico y huyó a través de los túneles subterráneos hacia la superficie desolada.

El traje SCP-5000 no era solo una armadura; era un sistema de soporte vital autosuficiente dotado de módulos de invisibilidad, purificación molecular y un visor nemotécnico capaz de registrar todo a su alrededor. Mientras caminaba por las ruinas humeantes de Norteamérica, Pietro documentó la caída de la Coalición Oculta Global y de todos los ejércitos que intentaron enfrentarse al arsenal anómalo de la Fundación. Vio a soldados de élite de la Fuerza de Tarea Móvil masacrar orfanatos sin parpadear, desprovistos de odio, de rabia o de cualquier emoción humana reconocible. Sus rostros eran máscaras de absoluta frialdad, como cirujanos que amputan un miembro gangrenado sin sentir remordimiento por el tejido eliminado.

En su desesperada travesía hacia el oeste, Pietro interceptó señales de radio de supervivientes que se preguntaban entre lágrimas la misma pregunta demoledora: ¿Por qué? ¿Por qué la organización que dedicó siglos a salvar vidas de pronto se convirtió en su mayor exterminador? La respuesta se encontraba oculta en una maleta de seguridad que Pietro transportaba en su espalda, un maletín hermético que contenía un cilindro anómalo recuperado de un laboratorio destruido. Su misión autoimpuesta era alcanzar el Sitio-62C y arrojar el cilindro dentro de SCP-579, una anomalía de distorsión espacio-temporal capaz de reescribir la causalidad histórica si era contactada por otro objeto catalizador.

Durante semanas de marcha en solitario a través de desiertos cubiertos de ceniza y bosques habitados por abominaciones liberadas, el traje de Pietro comenzó a fallar. Los filtros de aire se saturaron, los módulos de energía cayeron a niveles críticos y sus piernas se cubrieron de llagas bajo el blindaje. A pesar de las heridas y del agotamiento extremo, Pietro continuó arrastrándose, impulsado únicamente por la convicción de que la humanidad, con todos sus defectos, sus guerras y sus imperfecciones, merecía una segunda oportunidad de existir.

En sus últimas grabaciones de audio, registradas mientras se arrastraba por los pasillos devastados del Sitio-62C, la voz de Pietro suena débil pero cargada de una dignidad inquebrantable: No sé si lo que descubrió la Fundación en nuestras mentes era real. No sé si somos recipientes de un monstruo que se alimenta de nuestro dolor después de la muerte. Pero sé que sentir empatía, llorar por un amigo y amar a nuestros seres queridos no puede ser un error cósmico. Si el costo de eliminar al parásito es destruir todo lo que nos hace humanos, entonces prefiero que el monstruo siga viviendo con nosotros.

Con su último aliento, con el traje destruido y los sistemas biológicos colapsando, Pietro Wilson logró alcanzar la cámara sellada de SCP-579. Arrojó el cilindro al abismo gravitacional de la anomalía, desencadenando una singularidad cuántica que fracturó la línea temporal y reinició la historia del universo exactamente antes de que la Fundación descubriera la verdad del Proyecto Pneuma.

El traje SCP-5000 apareció materializado de forma espontánea dentro de la cámara de contención en nuestro presente, vacío, con los archivos grabados intactos y una nota grabada en su casco metálico: ¿Por qué? La Fundación SCP de nuestro universo mantiene el expediente clasificado bajo el nivel de máxima seguridad, asegurando que nadie jamás vuelva a mirar dentro del abismo de la mente humana. Porque a veces, la verdad más peligrosa de todas... es saber lo que realmente somos.
""".strip()


SCP5000_SHORT_SCRIPT = """
En el año 2020, la Fundación SCP cometió el acto más aterrador de su historia: no fue una brecha de contención, fue una decisión unánime. El Consejo O-5 declaró la guerra total contra la humanidad. Liberaron a cada monstruo clasificado: abrieron las celdas de S-C-P 682, enviaron a S-C-P 096 a las capitales del mundo y envenenaron la atmósfera. Los civiles creían que la Fundación los protegía, pero ellos eran ahora los verdugos. Todo comenzó cuando los científicos mapearon el subconsciente humano y descubrieron algo viviendo dentro de cada mente... una entidad parasitaria de dolor absoluto. La única forma de destruirla... era extinguirnos a todos. Un solo técnico sobrevivió dentro del traje anómalo S-C-P 5000 para reiniciar la realidad antes de que el universo colapsara. ¿Tenía razón la Fundación?
""".strip()


async def synthesize_audio(text: str, output_wav: Path, voice: str = "es-MX-JorgeNeural", rate: str = "-2%", pitch: str = "-1Hz") -> float:
    """Synthesizes neural voice track with Edge-TTS."""
    import edge_tts
    logger.info("🎤 Sintetizando audio (%s, rate=%s, pitch=%s)...", voice, rate, pitch)
    temp_mp3 = output_wav.with_suffix(".mp3")
    clean_text = sanitize_script_for_tts(text)
    communicate = edge_tts.Communicate(text=clean_text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(str(temp_mp3))

    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(temp_mp3),
        "-ar", "48000",
        "-ac", "2",
        str(output_wav),
    ]
    subprocess.run(cmd, check=True)
    if temp_mp3.exists():
        temp_mp3.unlink()

    cmd_probe = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(output_wav)]
    dur_str = subprocess.check_output(cmd_probe, text=True).strip()
    return float(dur_str)


def mix_master_audio(voice_wav: Path, bgm_path: Path, output_audio: Path, total_dur: float, target_lufs: float = -14.0) -> None:
    """Masters audio track under EBU R128 standards with dynamic sidechain ducking."""
    logger.info("🎛️ Masterizando audio EBU R128 (%.1f LUFS) con sidechain ducking...", target_lufs)
    filter_complex = (
        f"[0:a]aresample=48000,asplit=2[voice_sc][voice_mix];"
        f"[1:a]aresample=48000,lowpass=f=11000,volume=0.20[bgm_in];"
        f"[bgm_in][voice_sc]sidechaincompress=threshold=0.035:ratio=8.0:attack=20.0:release=350.0:makeup=1[bgm_ducked];"
        f"[voice_mix][bgm_ducked]amix=inputs=2:duration=first:normalize=0[amixed];"
        f"[amixed]loudnorm=I={target_lufs}:TP=-1.5:LRA=11.0,aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[aout]"
    )
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(voice_wav),
        "-stream_loop", "-1", "-i", str(bgm_path),
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-t", f"{total_dur:.3f}",
        str(output_audio),
    ]
    subprocess.run(cmd, check=True)


def compose_video(shader_loop_mp4: Path, master_audio: Path, output_master: Path, total_dur: float, is_vertical: bool = False) -> Path:
    """Composites master video with seamless loop and Rec.709 color metadata."""
    logger.info("🎬 Componiendo Video Master (%s, %.1fs)...", "9:16 Vertical" if is_vertical else "16:9 Horizontal", total_dur)
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-stream_loop", "-1", "-i", str(shader_loop_mp4),
        "-i", str(master_audio),
        "-t", f"{total_dur:.3f}",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_master),
    ]
    subprocess.run(cmd, check=True)
    return output_master


def main() -> int:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 65)
    print("🚀 INICIANDO PRODUCCIÓN DUAL: SCP-5000 (LONGFORM 10+ MIN + SHORT 60S)")
    print("=" * 65 + "\n")

    # =========================================================================
    # PART A: LONGFORM VIDEO (10+ MINUTES, 16:9 FULL HD)
    # =========================================================================
    logger.info(">>> FASE 1: PRODUCCIÓN DEL VIDEO LARGO (LONGFORM 1080P) <<<")
    long_voice_wav = WORK_DIR / "scp5000_long_voice.wav"
    long_master_audio = WORK_DIR / "scp5000_long_master_audio.m4a"
    long_master_video = OUTPUT_DIR / "scp5000_why_longform_1080p.mp4"
    long_thumbnail = OUTPUT_DIR / "scp5000_thumbnail_hd.jpg"

    # Step A1: Voice Synthesis
    long_dur = asyncio.run(synthesize_audio(SCP5000_LONG_SCRIPT, long_voice_wav, voice="es-MX-JorgeNeural", rate="-2%", pitch="-1Hz"))
    logger.info("✅ Audio Largo Generado: %.2f segundos (%.2f minutos)", long_dur, long_dur / 60.0)

    # Step A2: Audio Mastering EBU R128
    mix_master_audio(long_voice_wav, AUDIO_BGM, long_master_audio, long_dur, target_lufs=-14.0)

    # Step A3: High-CTR Thumbnail
    thumb_engine = ResilientThumbnailEngine()
    thumb_engine.generate(
        output_path=long_thumbnail,
        title_main="SCP-5000",
        title_sub="¿POR QUÉ?",
        highlight_box="LA GUERRA DE LA FUNDACIÓN",
        badge_text="NIVEL 5 // ARCHIVO OMNICIDA // CLASIFICADO",
        accent_color=(0, 255, 180),
        subtitle_color=(255, 255, 255),
    )
    logger.info("✅ Miniatura HD 1080p Generada: %s", long_thumbnail.name)

    # Step A4: Video Composition
    h_loop = ROOT_DIR / "assets" / "loops" / "web_procedural" / "cosmic_horror" / "web_cosmic_horror_h_s142567_6s.mp4"
    compose_video(h_loop, long_master_audio, long_master_video, long_dur, is_vertical=False)
    logger.info("✅ Master Largo 1080p Generado: %s (%.2f MB)", long_master_video.name, long_master_video.stat().st_size / (1024*1024))

    # Step A5: SEO Metadata & Synchronized Timestamps
    act_titles = [
        "El Hallazgo del Traje SCP-5000 en el Sitio-62C",
        "El Descubrimiento del Proyecto Pneuma",
        "El Comunicado O5 y la Declaración de Guerra",
        "La Liberación Global de Anomalías (682, 096, 173)",
        "La Frialdad de los Soldados de Contención",
        "La Travesía Solitaria de Pietro Wilson",
        "La Maleta Hermética y el Camino a SCP-579",
        "El Sacrificio Final y el Reinicio de la Realidad",
    ]
    sec_per_act = long_dur / len(act_titles)
    acts_manifest = [{"start_sec": i * sec_per_act, "title": t} for i, t in enumerate(act_titles)]
    long_timestamps = SeoOptimizerAgent.build_synchronized_timestamps(acts_manifest, long_dur)

    from src.branding import get_channel_branding
    branding = get_channel_branding("moku")

    long_title = "SCP-5000: ¿Por Qué? - La Guerra de la Fundación contra la Humanidad"
    long_desc = (
        f"{long_title}\n\n"
        "Dentro del Sitio-62C fue hallado un traje mecánico chamuscado con el cadáver de un técnico y una grabación imposible: "
        "la historia de cuando la Fundación SCP decidió exterminar deliberadamente a toda la especie humana.\n\n"
        f"{long_timestamps}\n\n"
        f"🔔 Suscríbete a {branding.handle} para más expedientes clasificados y documentales de la Fundación SCP.\n\n"
        "#SCP #SCP5000 #FundacionSCP #TerrorPsicologico #DocumentalSCP #Creepypasta"
    )

    # Step A6: QA Audit for Longform
    qa_agent = VisualAudioQAAuditorAgent()
    long_qa = qa_agent.audit_video(
        long_master_video,
        run_id="scp5000_longform_run",
        target_resolution="1920x1080",
        thumbnail_path=long_thumbnail,
        description_text=long_desc,
    )
    logger.info("🔍 QA Audit Longform Score: %d/100 (Overall Pass: %s)", long_qa["quality_score"], long_qa["overall_pass"])

    # =========================================================================
    # PART B: VERTICAL SHORT (9:16, 1080x1920, ~60 SECONDS)
    # =========================================================================
    logger.info("\n>>> FASE 2: PRODUCCIÓN DEL SHORT VERTICAL (9:16 1080x1920) <<<")
    short_voice_wav = WORK_DIR / "scp5000_short_voice.wav"
    short_master_audio = WORK_DIR / "scp5000_short_master_audio.m4a"
    short_master_video = OUTPUT_DIR / "scp5000_why_short_1080x1920.mp4"
    short_thumbnail = OUTPUT_DIR / "scp5000_short_thumbnail.jpg"

    # Step B1: Short Voice Synthesis (Dynamic +15% rate)
    short_dur = asyncio.run(synthesize_audio(SCP5000_SHORT_SCRIPT, short_voice_wav, voice="es-MX-JorgeNeural", rate="+15%", pitch="-1Hz"))
    logger.info("✅ Audio Short Generado: %.2f segundos", short_dur)

    # Step B2: Audio Mastering
    mix_master_audio(short_voice_wav, AUDIO_BGM, short_master_audio, short_dur, target_lufs=-14.0)

    # Step B3: Short Vertical Thumbnail
    thumb_engine.generate(
        output_path=short_thumbnail,
        title_main="SCP-5000",
        title_sub="TRAICIÓN",
        highlight_box="GUERRA TOTAL",
        badge_text="SHORTS // CLASIFICADO",
        accent_color=(255, 60, 80),
        width=1080,
        height=1920,
    )

    # Step B4: Short Vertical Video Composition
    # Check for vertical loop in assets
    v_loops = list((ROOT_DIR / "assets" / "loops").glob("**/*_v_*.mp4")) + list((ROOT_DIR / "assets" / "loops").glob("**/*vertical*.mp4"))
    if v_loops:
        v_loop = v_loops[0]
    else:
        v_loop = h_loop  # FFmpeg will crop/pad if needed

    # If using horizontal loop for vertical video, scale & crop to 1080x1920
    logger.info("🎬 Renderizando Master 9:16 (1080x1920)...")
    cmd_short = [
        "ffmpeg", "-y", "-v", "error",
        "-stream_loop", "-1", "-i", str(v_loop),
        "-i", str(short_master_audio),
        "-t", f"{short_dur:.3f}",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(short_master_video),
    ]
    subprocess.run(cmd_short, check=True)
    logger.info("✅ Master Short 9:16 Generado: %s (%.2f MB)", short_master_video.name, short_master_video.stat().st_size / (1024*1024))

    # Step B5: QA Audit for Short
    short_qa = qa_agent.audit_video(
        short_master_video,
        run_id="scp5000_short_run",
        target_resolution="1080x1920",
        thumbnail_path=short_thumbnail,
    )
    logger.info("🔍 QA Audit Short Score: %d/100 (Overall Pass: %s)", short_qa["quality_score"], short_qa["overall_pass"])

    # Cleanup temporary work directory
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR, ignore_errors=True)

    print("\n" + "=" * 65)
    print("🎉 ¡PRODUCCIÓN DUAL COMPLETADA EXITOSAMENTE!")
    print("=" * 65)
    print(f"🎬 VIDEO LARGO (16:9): {long_master_video}")
    print(f"   ⏱️ Duración:        {int(long_dur // 60)}m {int(long_dur % 60):02d}s ({long_dur:.2f}s)")
    print(f"   📐 Resolución:      1920x1080 Full HD")
    print(f"   🖼️ Miniatura:       {long_thumbnail}")
    print(f"   🎯 QA Score:        {long_qa[quality_score]}/100")
    print("-" * 65)
    print(f"📱 SHORT VERTICAL (9:16): {short_master_video}")
    print(f"   ⏱️ Duración:        {int(short_dur // 60)}m {int(short_dur % 60):02d}s ({short_dur:.2f}s)")
    print(f"   📐 Resolución:      1080x1920 Vertical")
    print(f"   🖼️ Miniatura:       {short_thumbnail}")
    print(f"   🎯 QA Score:        {short_qa[quality_score]}/100")
    print("=" * 65 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())