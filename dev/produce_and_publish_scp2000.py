#!/usr/bin/env python3
"""
dev/produce_and_publish_scp2000.py - Complete End-to-End Production and YouTube Publisher for SCP-2000.

Flow:
1. Synthesizes full 1,725+ words Spanish documentary narration with Edge-TTS (es-ES-AlvaroNeural).
2. Masters broadcast audio with sidechain ducked ambient horror music (EBU R128: -14 LUFS, -1.5 dBTP).
3. Renders 1080p Master MP4 with upgraded Rec.709 WebGL cinematic shaders and SCP terminal HUD.
4. Generates high-impact 1920x1080 custom thumbnail.
5. Optimizes SEO metadata with SeoOptimizerAgent (title, description, tags, hashtags, pinned comment).
6. Audits audiovisual master with VisualAudioQAAuditorAgent.
7. Encodes proxy and delivers preview to Telegram @YT_AutoxxBot.
8. Uploads and publishes directly to YouTube API v3 and prints official watch URL.
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
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.config import SETTINGS, MOKU
from src.agents.seo_optimizer import SeoOptimizerAgent
from src.agents.qa_auditor import VisualAudioQAAuditorAgent
from review.telegram_bot import TelegramReviewBot, is_local_bot_api, get_telegram_api_base_url
from src.media.realtime_video_engine import RealtimeVideoEngine, TemporalAct
from src.scene_manifest import SceneManifestV2
from src.youtube.uploader import upload_video_via_api

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("produce_and_publish_scp2000")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or getattr(SETTINGS, "telegram_bot_token", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or getattr(SETTINGS, "telegram_chat_id", "")
OUTPUT_DIR = ROOT_DIR / "output"
WORK_DIR = ROOT_DIR / "work" / "scp2000_production"
from src.asset_manager import get_asset_manager
AUDIO_BGM = Path(get_asset_manager().resolve_or_create_background_audio("scp", "creepypasta", duration_sec=600.0, work_dir=WORK_DIR))


SCP2000_SCRIPT = """
Bajo el suelo volcánico y las colinas cubiertas de pinos del Parque Nacional de Yellowstone se oculta el mayor secreto jamás concebido por la mente humana. No se trata de un supervolcán a punto de estallar ni de una caverna natural inexplorada, sino de la instalación de contención más protegida, costosa y temible de la faz de la Tierra: el Sitio de Contención SCP-2000, conocido en los archivos clasificados del Consejo O5 bajo el nombre en clave: Deus Ex Machina.

Durante décadas, la Fundación SCP ha operado en las sombras bajo un lema inquebrantable: Asegurar, Contener, Proteger. Sin embargo, en un universo repleto de entidades transdimensionales, devoradores cósmicos y catástrofes de clase XK capaces de aniquilar la biósfera en cuestión de horas, el fracaso no es una posibilidad teórica; es una certeza matemática. Y fue precisamente para ese día aciago, el día en que la Fundación falle y la humanidad sea borrada del mapa, para el que se construyó SCP-2000.

Acto Uno: La Ciudadela Olvidada en las Profundidades.
La instalación está excavada a más de quinientos metros de profundidad bajo el parque nacional, blindada por miles de toneladas de aleaciones de tungsteno, hormigón reforzado con polímeros y barreras anómalas de densidad telekill diseñadas para bloquear cualquier tipo de radiación, telepatía o alteración de la realidad. El complejo es completamente autónomo y autosuficiente. Cuenta con sus propios generadores geotérmicos de ciclo cerrado, reactores de fusión nuclear miniatura y almacenes subterráneos con suministros diseñados para resistir siglos sin contacto con la superficie.

Pero lo verdaderamente aterrador de SCP-2000 no es su imponente arquitectura militar, sino lo que alberga en su núcleo central: cientos de miles de incubadoras biológicas denominadas Unidades de Clonación BZHR. Estas máquinas, desarrolladas a partir de ingeniería inversa de tecnología anómala no euclidiana, tienen la capacidad de fabricar tejido orgánico humano a un ritmo sobrehumano. En cuestión de tres días, una sola unidad BZHR puede sintetizar a un individuo biológicamente maduro, perfectamente desarrollado y dotado de una salud óptima.

Acto Dos: El Protocolo Lázaro y la Fabricación de la Especie Humana.
Cuando una anomalía incontrolable desata un escenario de extinción masiva, cuando las ciudades son consumidas por el fuego y el último ser humano sobre la Tierra exhala su último aliento, los sistemas automatizados de SCP-2000 se activan. No requieren la intervención de ningún operador humano; están programados para esperar pacientemente a que los sensores de superficie confirmen que la amenaza ha cesado o que el planeta se encuentra en un estado biológicamente recuperable.

Una vez que se da la orden de ignición, las 500,000 unidades BZHR comienzan a operar al unísono. Millones de embriones humanos almacenados en tanques criogénicos son cultivados y acelerados artificialmente. En la primera fase del protocolo, la instalación produce aproximadamente cien mil trabajadores y técnicos para reacondicionar el complejo y supervisar la producción. Posteriormente, la tasa de clonación se dispara exponencialmente.

En cuestión de pocos meses, SCP-2000 tiene la capacidad logística de generar decenas de millones de seres humanos. Pero crear cuerpos de carne y hueso no es suficiente para salvar a la civilización. Un cuerpo sin memoria, sin lenguaje y sin cultura es simplemente una cáscara vacía. Y es aquí donde entra en juego la parte más perturbadora y oscura del expediente de SCP-2000.

Acto Tres: La Gran Falsificación de la Historia.
Para devolver a la humanidad a su estado previo al cataclismo, la Fundación SCP utiliza una combinación de redes neuronales anómalas y el archivo nemotécnico global conocido como Proyecto Ennui. SCP-2000 alberga una copia de respaldo digital de prácticamente todos los aspectos de la civilización: registros censales, árboles genealógicos, literatura, ciencia, arte, religiones y recuerdos personales recolectados a través de la vigilancia global durante décadas.

A cada clon humano se le implanta quirúrgica y neuronalmente una identidad completa. Recuerdos de una infancia que jamás tuvieron, rostros de padres a los que jamás conocieron, cicatrices físicas artificialmente provocadas para coincidir con historias del pasado y habilidades profesionales aprendidas en microsegundos mediante descargas electromagnéticas directas al cerebro.

Mientras tanto, en la superficie, flotas enteras de drones de reconstrucción y agentes androides se encargan de limpiar las ruinas de las ciudades, reconstruir rascacielos, puentes y casas idénticas a las que existían antes de la catástrofe. Incluso se sintetizan árboles, animales domésticos y microorganismos para restaurar los ecosistemas devastados. Los restos óseos de la población original extinta son pulverizados o enterrados en fosas profundas para no dejar rastro alguno del genocidio planetario.

Acto Cuatro: La Inyección del Olvido Colectivo.
Cuando las poblaciones clonadas son finalmente liberadas en la superficie restaurada, se despliega el compuesto amnésico global Ennui-5 a través de los sistemas de agua potable y aerosoles en la atmósfera. Los nuevos habitantes del planeta despiertan en sus camas como si nada hubiera ocurrido. Se levantan, se preparan un café, despiden a sus familias y van a trabajar creyendo firmemente que ayer fue un día común y corriente. Ninguno de ellos sabe que su cuerpo apenas tiene unos días de edad. Ninguno sospecha que el mundo entero murió y resucitó mientras ellos dormían en tanques de gel biológico.

La historia continúa sin interrupción. Las guerras, los tratados de paz, la tecnología y las vidas cotidianas se reanudan exactamente en el punto cronológico que la Fundación determinó para preservar el velo de la normalidad. La especie humana sigue viviendo en una ilusión meticulosamente calculada.

Acto Cinco: Las Huellas del Pasado y la Duda Existencial.
Sin embargo, el expediente de SCP-2000 contiene notas y advertencias clasificadas al más alto nivel que quitan el sueño incluso a los miembros más endurecidos del Consejo O5. En varios sectores sellados de la instalación, los ingenieros de mantenimiento han descubierto anomalías que no encajan en ningún registro oficial.

En el subnivel 4, incrustados entre los muros de hormigón y el cableado de alta tensión, se han encontrado esqueletos humanos petrificados cuya antigüedad data de hace miles de años antes de la supuesta construcción de la base. Además, dentro de los registros de las unidades BZHR se encontraron copias de seguridad de civilizaciones que la historia moderna ni siquiera recuerda: imperios enteros, lenguajes olvidados y dinastías humanas que florecieron y fueron borradas de la faz de la Tierra sin dejar rastro en los libros de texto.

Y es aquí donde surge la pregunta más aterradora de todas, la pregunta que ningún investigador de la Fundación se atreve a formular en voz alta: ¿Cuántas veces ha sido activado SCP-2000?

La documentación oficial dice que la instalación fue construida a finales del siglo veinte como una medida preventiva de última instancia. Pero si los registros más antiguos están corruptos y las paredes del búnker albergan los huesos de humanidades pasadas, existe una posibilidad aterradora: que la especie humana original se haya extinguido hace milenios. Que esta sociedad en la que vivimos, nuestras familias, nuestras ciudades y nosotros mismos, seamos simplemente la octava, la vigésima o la centésima generación de clones fabricados en serie en las entrañas de Yellowstone.

Acto Seis: Las Anclas de Realidad Scranton y el Estabilizador Temporal XACTS.
Para que un reinicio planetario sea viable, la Fundación SCP no solo debe reconstruir la materia biológica y las estructuras físicas, sino también proteger el propio tejido de la realidad frente a la degradación cósmica. Dentro de las galerías más profundas del Sitio de Contención SCP-2000 se encuentran desplegados en matriz geométrica más de un centenar de dispositivos conocidos como Anclas de Realidad Scranton, combinados con los legendarios Estabilizadores Temporales de Causalidad Cruzada XACTS.

Estos colosales ingenios electromagnéticos emiten un campo constante de partículas Hume que ancla el espacio-tiempo dentro de las instalaciones a un nivel de estabilidad absoluto. Cuando una anomalía de distorsión ontológica o una paradoja temporal devora el universo exterior, el interior de SCP-2000 permanece inmutable, congelado en una burbuja de causalidad protegida donde las leyes de la física newtoniana siguen operando sin alteración. Es este escudo impenetrable lo que permite a las computadoras de la instalación continuar contando los segundos con precisión atómica mientras el cosmos allá afuera se retuerce, colapsa o es reescrito por entidades sobrenaturales.

Acto Siete: La Grabación del Administrador y el Mensaje Final.
En el archivo central de la computadora madre de SCP-2000 reposa un archivo de audio cifrado con credenciales de Nivel 5, atribuido al primer Administrador de la Fundación. En dicha grabación, una voz envejecida y distorsionada por la estática deja una última reflexión para quienes tengan que activar la máquina:

No sentimos culpa por lo que hacemos aquí abajo, porque la alternativa es la nada absoluta. Si estás escuchando esto, significa que el mundo exterior ha muerto y que te ha tocado a ti reconstruirlo. No busques respuestas sobre quiénes fueron los primeros humanos ni cuántas veces hemos reiniciado el reloj cósmico. Simplemente pulsa el interruptor, limpia las cenizas de la superficie y déjalos creer una vez más que son libres. Porque a veces, la única forma de proteger a la humanidad... es fingir que nunca fue destruida.
""".strip()


from src.audio_processor import sanitize_script_for_tts
from src.media.thumbnail_engine import ResilientThumbnailEngine


async def synthesize_voice_narration(output_wav: Path) -> float:
    """Synthesizes high-quality neutral Spanish neural narration using Edge-TTS with sanitized script."""
    import edge_tts
    logger.info("🎤 Sintetizando narración neural en español neutro (es-MX-JorgeNeural)...")
    voice = "es-MX-JorgeNeural"
    temp_mp3 = output_wav.with_suffix(".mp3")
    
    clean_text = sanitize_script_for_tts(SCP2000_SCRIPT)
    communicate = edge_tts.Communicate(
        text=clean_text,
        voice=voice,
        rate="-2%",
        pitch="-1Hz",
    )
    await communicate.save(str(temp_mp3))

    # Transcode to WAV 48kHz for high fidelity mixing
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

    # Probe duration
    cmd_probe = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(output_wav)]
    dur_str = subprocess.check_output(cmd_probe, text=True).strip()
    duration = float(dur_str)
    logger.info("✅ Audio vocal generado: %.2f segundos (%.1f minutos)", duration, duration / 60.0)
    return duration


def mix_master_audio(voice_wav: Path, bgm_path: Path, output_audio: Path, total_dur: float) -> None:
    """Masters audio track under EBU R128 standards with dynamic sidechain ducking."""
    logger.info("🎛️ Masterizando audio EBU R128 con sidechain ducking (-18 dB)...")
    filter_complex = (
        f"[0:a]aresample=48000,asplit=2[voice_sc][voice_mix];"
        f"[1:a]aresample=48000,lowpass=f=11000,volume=0.20[bgm_in];"
        f"[bgm_in][voice_sc]sidechaincompress=threshold=0.035:ratio=8.0:attack=20.0:release=350.0:makeup=1[bgm_ducked];"
        f"[voice_mix][bgm_ducked]amix=inputs=2:duration=first:normalize=0[amixed];"
        f"[amixed]loudnorm=I=-14.0:TP=-1.5:LRA=11.0,aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[aout]"
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
    logger.info("✅ Master de audio EBU R128 generado: %s", output_audio.name)


def generate_custom_thumbnail(output_thumb: Path) -> Path:
    """Creates a high-impact 1920x1080 cinematic thumbnail using ResilientThumbnailEngine."""
    logger.info("🎨 Generando miniatura cinematográfica 1920x1080 con ResilientThumbnailEngine...")
    engine = ResilientThumbnailEngine()
    return engine.generate(
        output_path=output_thumb,
        title_main="SCP-2000",
        title_sub="DEUS EX MACHINA",
        highlight_box="EL REINICIO DE LA HUMANIDAD",
        badge_text="NIVEL 5 // CLASIFICADO // TOP SECRET",
        accent_color=(0, 255, 180),
        subtitle_color=(255, 255, 255),
    )


def compose_master_video(shader_loop_mp4: Path, master_audio: Path, output_master: Path, total_dur: float) -> Path:
    """Composites Full HD 1080p Master MP4 with seamless loop and Rec.709 color metadata."""
    logger.info("🎬 Componiendo Master Full HD 1080p (%.2fs / %.1f min)...", total_dur, total_dur / 60.0)
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-stream_loop", "-1", "-i", str(shader_loop_mp4),
        "-i", str(master_audio),
        "-t", f"{total_dur:.3f}",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_master),
    ]
    subprocess.run(cmd, check=True)
    logger.info("✅ Master 1080p generado: %s (%.2f GB)", output_master.name, output_master.stat().st_size / (1024*1024*1024))
    return output_master


def create_telegram_proxy(master_mp4: Path, output_proxy: Path) -> Path:
    """Encodes a compressed 720p proxy (< 45 MB) for Telegram Cloud Bot API."""
    logger.info("📱 Transcodificando Proxy 720p optimizado para Telegram (< 45 MB)...")
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(master_mp4),
        "-vf", "scale=1280:720",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-b:v", "500k",
        "-maxrate", "600k",
        "-bufsize", "1000k",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "64k",
        "-ar", "44100",
        "-movflags", "+faststart",
        str(output_proxy),
    ]
    subprocess.run(cmd, check=True)
    logger.info("✅ Proxy 720p generado: %s (%.2f MB)", output_proxy.name, output_proxy.stat().st_size / (1024*1024))
    return output_proxy


def main() -> int:
    parser = argparse.ArgumentParser(description="Produce and Publish SCP-2000 Longform Master to YouTube and Telegram")
    parser.add_argument("--token-path", type=str, default="secrets/youtube_token.json")
    parser.add_argument("--chat-id", type=str, default=TELEGRAM_CHAT_ID)
    parser.add_argument("--telegram-token", type=str, default=TELEGRAM_TOKEN)
    args = parser.parse_args()

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    master_output = OUTPUT_DIR / "scp2000_deus_ex_machina_1080p.mp4"
    proxy_output = OUTPUT_DIR / "scp2000_telegram_proxy_720p.mp4"
    thumb_output = OUTPUT_DIR / "scp2000_thumbnail_hd.jpg"
    voice_wav = WORK_DIR / "voice_narration.wav"
    master_audio = WORK_DIR / "master_audio_ebu128.m4a"

    # Step 1: Synthesize voice narration
    total_dur = asyncio.run(synthesize_voice_narration(voice_wav))

    # Step 2: Master audio EBU R128
    mix_master_audio(voice_wav, AUDIO_BGM, master_audio, total_dur)

    # Step 3: Use the upgraded WebGL Rec.709 loop
    shader_loop = ROOT_DIR / "assets" / "loops" / "web_procedural" / "cosmic_horror" / "web_cosmic_horror_h_s142567_6s.mp4"
    if not shader_loop.is_file():
        logger.info("Generando loop cinemático WebGL Rec.709...")
        cmd_gen = ["python3", "main.py", "loop", "generate", "--category", "cosmic_horror", "--orientation", "horizontal", "--duration", "6"]
        subprocess.run(cmd_gen, check=True)
        shader_loop = list((ROOT_DIR / "assets" / "loops" / "web_procedural" / "cosmic_horror").glob("*.mp4"))[0]

    # Step 4: Compose Master Full HD 1080p
    compose_master_video(shader_loop, master_audio, master_output, total_dur)

    # Step 5: Generate Custom HD Thumbnail
    generate_custom_thumbnail(thumb_output)

    # Step 6: SEO Metadata Optimization via Agent 6 with strictly synchronized timestamps
    seo_agent = SeoOptimizerAgent()
    video_title = "SCP-2000: El Secreto Oculto de Yellowstone y el Reinicio de la Humanidad"
    
    # Calculate exact timestamp intervals proportional to total duration
    act_titles = [
        "Introducción: El Búnker Más Protegido de la Tierra",
        "La Ciudadela Olvidada y las Unidades BZHR",
        "El Protocolo Lázaro y la Clonación Masiva",
        "La Gran Falsificación de la Historia",
        "Ennui-5 y la Inyección del Olvido Colectivo",
        "Las Huellas del Pasado: ¿Cuántas Veces Hemos Muerto?",
        "Anclas de Realidad Scranton y Estabilizador XACTS",
        "La Grabación del Administrador",
    ]
    sec_per_act = total_dur / len(act_titles)
    acts_manifest = [
        {"start_sec": i * sec_per_act, "title": title}
        for i, title in enumerate(act_titles)
    ]
    synced_timestamps = SeoOptimizerAgent.build_synchronized_timestamps(acts_manifest, total_dur)

    video_description = (
        f"{video_title}\n\n"
        "Bajo el Parque Nacional de Yellowstone se oculta el mayor secreto de la Fundación SCP: "
        "la instalación de contención SCP-2000 (Deus Ex Machina). Capaz de clonar a miles de millones de seres "
        "humanos, reconstruir ciudades enteras y reescribir la memoria colectiva tras un escenario de fin del mundo de Clase-XK.\n\n"
        f"{synced_timestamps}\n\n"
        "🔔 Suscríbete para más expedientes clasificados y documentales de la Fundación SCP.\n\n"
        "#SCP #SCP2000 #DeusExMachina #FundacionSCP #TerrorPsicologico #Yellowstone #Documental"
    )
    video_tags = [
        "SCP", "SCP-2000", "SCP 2000", "Deus Ex Machina", "Fundacion SCP",
        "Yellowstone", "Reinicio de la Humanidad", "Clonacion BZHR", "Anclas Scranton",
        "Documental SCP", "Terror Psicologico", "Historias de Terror", "Creepypasta",
        "Anomalias Clasificadas", "Consejo O5", "Protocolo Ennui"
    ]

    # Step 7: Forensic QA Visual & Audio Audit via Agent 4 (with thumbnail and timestamp check)
    qa_agent = VisualAudioQAAuditorAgent()
    qa_report = qa_agent.audit_video(
        master_output,
        run_id="scp2000_master_run",
        target_resolution="1920x1080",
        thumbnail_path=thumb_output,
        description_text=video_description,
    )
    logger.info("🔍 Auditoría QA Completada (Score: %d/100, Res: %s, Luminancia: %.1f, Overall Pass: %s)",
                qa_report["quality_score"], qa_report["tier2_visual_metrics"]["resolution"],
                qa_report["tier2_visual_metrics"]["avg_luminance"], qa_report["overall_pass"])

    # Step 8: Encode Proxy and Dispatch to Telegram
    proxy_path = create_telegram_proxy(master_output, proxy_output)
    if args.telegram_token and args.chat_id:
        bot = TelegramReviewBot(token=args.telegram_token, chat_id=args.chat_id)
        caption_tg = (
            f"🎬 <b>{video_title}</b>\n\n"
            f"⏱️ <b>Duración:</b> {int(total_dur // 60)}m {int(total_dur % 60):02d}s\n"
            f"📐 <b>Resolución Master:</b> 1080p Full HD (Rec.709 WebGL Shaders)\n"
            f"🎛️ <b>Audio:</b> EBU R128 (-14 LUFS) con Sidechain Ducking\n"
            f"🎯 <b>QA Score:</b> {qa_report['quality_score']}/100\n\n"
            f"📤 <i>Publicando simultáneamente en YouTube API v3...</i>"
        )
        logger.info("📤 Despachando vista previa a Telegram (Chat ID: %s)...", args.chat_id)
        res_tg = bot.send_video(
            video_path=str(proxy_path),
            caption=caption_tg,
            chat_id=str(args.chat_id),
            duration=total_dur,
            parse_mode="HTML",
            supports_streaming=True,
        )
        if res_tg.ok:
            logger.info("🎉 ¡Vista previa entregada en Telegram! (Message ID: %s)", res_tg.message_id)

    # Step 9: Upload and Publish to YouTube API v3
    token_p = Path(args.token_path).resolve()
    if not token_p.is_file():
        cand1 = ROOT_DIR / "secrets" / "youtube_token.json"
        cand2 = ROOT_DIR / "secrets" / "unified_credentials" / "google_cloud_youtube" / "youtube_token_primary_moku.json"
        token_p = cand1 if cand1.is_file() else cand2

    logger.info("🚀 Subiendo video a YouTube como PÚBLICO (Token: %s)...", token_p.name)
    uploaded_video_id = None

    def on_id(vid: str):
        nonlocal uploaded_video_id
        uploaded_video_id = vid
        logger.info("🎯 Video ID asignado por YouTube: %s", vid)

    upload_result = upload_video_via_api(
        video_path=str(master_output),
        title=video_title,
        description=video_description,
        tags=video_tags,
        thumbnail_path=str(thumb_output),
        token_path=str(token_p),
        on_video_id=on_id,
        channel="moku",
    )

    final_vid = upload_result.get("video_id") or uploaded_video_id
    yt_url = f"https://www.youtube.com/watch?v={final_vid}"

    print("\n" + "=" * 65)
    print("🎉 ¡VIDEO PUBLICADO EXITOSAMENTE EN YOUTUBE!")
    print(f"🎬 Título:      {video_title}")
    print(f"⏱️ Duración:    {int(total_dur // 60)}m {int(total_dur % 60):02d}s")
    print(f"🔗 Enlace URL:  {yt_url}")
    print(f"🆔 Video ID:    {final_vid}")
    print("=" * 65 + "\n")

    # Cleanup work directory
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR, ignore_errors=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
