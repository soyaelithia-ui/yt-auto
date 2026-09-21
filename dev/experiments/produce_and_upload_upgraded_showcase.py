"""
dev/produce_and_upload_upgraded_showcase.py - Master Production and YouTube Upload with High-CTR Thumbnails.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import edge_tts
from googleapiclient.http import MediaFileUpload
from PIL import Image

from lib.ffmpeg import probe_media
from lib.subtitles import create_ass_subtitles
from src.agents.art_director import ArtDirectorMoodAgent
from src.agents.scene_planner import ScenePlannerCompositorAgent
from src.agents.script_curator import CinematicScriptCuratorAgent
from src.core.channel_profile import ChannelProfileRegistry
from src.media.loop_engine import LoopVideoEngine
from src.media.thumbnails.engine import ThumbnailConfig, ThumbnailEngine
from src.youtube.uploader import _youtube_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("upgraded_showcase")

OUTPUT_DIR = REPO_ROOT / "output" / "showcase_v3"
FONTS_DIR = REPO_ROOT / "assets" / "fonts"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def synthesize_speech_sync(text: str, output_path: Path, voice: str = "es-ES-AlvaroNeural") -> Path:
    """Runs isolated asyncio loop for TTS synthesis and terminates loop before rendering."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    async def _runner():
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))
    asyncio.run(_runner())
    logger.info("Synthesized TTS speech: %s", output_path)
    return output_path


def generate_karaoke_ass(text: str, total_duration: float, output_path: Path, is_vertical: bool = True) -> Path:
    words = text.split()
    if not words:
        return output_path
    step = total_duration / max(1, len(words))
    word_timestamps = [
        {"word": w, "start": round(i * step, 2), "end": round((i + 1) * step, 2)}
        for i, w in enumerate(words)
    ]
    create_ass_subtitles(
        word_timestamps=word_timestamps,
        output_path=str(output_path),
        template="scp_classified" if is_vertical else "default",
        video_res=(1080, 1920) if is_vertical else (1920, 1080),
        font_name="Montserrat-Black.ttf",
    )
    return output_path


def assemble_master_video(
    raw_video_path: Path,
    audio_path: Path,
    subtitles_path: Optional[Path],
    output_path: Path,
    width: int,
    height: int,
    fps: int = 30,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(raw_video_path.resolve()),
        "-i", str(audio_path.resolve()),
    ]

    filter_complex = f"[0:v]scale={width}:{height},fps={fps},format=yuv420p"
    if subtitles_path and subtitles_path.is_file():
        from src.media.subtitles_ass import libass_filter_clause
        filter_complex += f",{libass_filter_clause(subtitles_path)}"
    filter_complex += "[v]"

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "1:a",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "19",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(output_path.resolve()),
    ])

    logger.info("Assembling master video with FFmpeg: %s", output_path)
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return output_path


def produce_short_production() -> Dict[str, Any]:
    logger.info("=== PRODUCING SHORT PRODUCTION (9:16) ===")
    short_dir = OUTPUT_DIR / "short"
    short_dir.mkdir(parents=True, exist_ok=True)

    title = "INCIDENTE EN EL FARO DE LA FOSA 14"
    raw_story = (
        "Bitácora del Faro 14. A las tres de la madrugada, las aguas de la fosa oceánica comenzaron a retroceder de forma imposible. "
        "En la sala de máquinas del sótano, los generadores vibraban mientras la baliza estroboscópica parpadeaba en rojo de emergencia. "
        "Entonces emergió de la niebla abisal: una silueta titánica con ojos incandescentes que eclipsó la línea del horizonte. "
        "El radar militar registró una anomalía electromagnética total segundos antes de que la señal se cortara para siempre."
    )

    audio_path = short_dir / "narration.mp3"
    synthesize_speech_sync(raw_story, audio_path, voice="es-ES-AlvaroNeural")
    probe = probe_media(str(audio_path))
    audio_dur = float(probe.duration) if probe else 22.0

    # 1. Script Curator
    curator = CinematicScriptCuratorAgent()
    script = curator.curate(
        raw_text=raw_story,
        title=title,
        channel_lane="moku-scp-shorts",
        target_format="short",
        words_per_minute=150.0,
    )

    # 2. Art Director
    art_director = ArtDirectorMoodAgent()
    visual_plan = art_director.plan_visuals(
        cinematic_script=script,
        theme_lane="scp_foundation",
    )

    # 3. Scene Planner (enforces non-repetition)
    planner = ScenePlannerCompositorAgent()
    manifest = planner.plan_manifest(
        script=script,
        visual_plan=visual_plan,
        story_id="short_faro_14",
        narration_path=str(audio_path),
        channel_name="moku",
        resolution=[1080, 1920],
        fps=30,
        actual_audio_duration=audio_dur,
    )

    manifest_path = short_dir / "scene_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # 4. Render Catalog Loop Scenes
    raw_video = short_dir / "raw_procedural_scenes.mp4"
    proc_engine = LoopVideoEngine()
    proc_engine.render(manifest_path=manifest_path, output_video_path=raw_video)

    # 5. Subtitles
    subs_path = short_dir / "subtitles.ass"
    generate_karaoke_ass(raw_story, audio_dur, subs_path, is_vertical=True)

    # 6. Composite Master Video
    master_video = short_dir / "short_master_1080x1920.mp4"
    assemble_master_video(
        raw_video_path=raw_video,
        audio_path=audio_path,
        subtitles_path=subs_path,
        output_path=master_video,
        width=1080,
        height=1920,
        fps=30,
    )

    # 7. Generate High-CTR Thumbnail
    thumb_engine = ThumbnailEngine()
    thumb_path = short_dir / "short_thumbnail.jpg"
    thumb_cfg = ThumbnailConfig(
        title="LO QUE VIO EL FARERO",
        hook_text="APAGÓN EN EL FARO",
        channel_id="moku",
        output_path=thumb_path,
        width=1080,
        height=1920,
        accent_color="#00FF66",
        primary_color="#FFE600",
    )
    thumb_res = thumb_engine.generate(
        config=thumb_cfg,
        video_path=master_video,
        manifest_path=manifest_path,
    )

    return {
        "format": "short",
        "title": f"{title} #Shorts #Terror #Moku",
        "description": "Una impactante narración en Moku sobre el incidente inexplicable en el Faro 14.\n\n#Shorts #Terror #Misterio #SCP #Horror",
        "video_path": master_video,
        "thumbnail_path": thumb_res,
        "duration": audio_dur,
        "manifest": manifest,
    }


def produce_longform_production() -> Dict[str, Any]:
    logger.info("=== PRODUCING LONGFORM PRODUCTION (16:9) ===")
    long_dir = OUTPUT_DIR / "longform"
    long_dir.mkdir(parents=True, exist_ok=True)

    title = "LA TRAVESÍA POR EL PÁRAMO DE LOS MONOLITOS SILENTES"
    raw_story = (
        "Acto uno: La expedición comenzó en el límite septentrional, donde el páramo de cenizas grises se extiende bajo un horizonte de monolitos ciclópeos y niebla perpetua. "
        "Acto dos: Nos refugiamos en el búnker subterráneo de hormigón sellado, mientras las alarmas estroboscópicas anunciaban la ruptura inminente de los mamparos de contención. "
        "Acto tres: Al descender a la cámara profunda, la red sináptica bioluminiscente comenzó a emitir pulsos eléctricos que se sincronizaban con los pensamientos de la tripulación. "
        "Acto cuatro: Entonces la tormenta se abrió. Una silueta titánica emergió entre las cenizas con ojos incandescentes, desafiando toda comprensión física. "
        "Acto cinco: Sobre el vórtice cósmico, la singularidad gravitacional distorsionó la luz estelar en un anillo relativista enceguecedor. "
        "Acto seis: Los terminales de radar del búnker parpadearon con telemetría clasificable en nivel cinco antes del colapso de las comunicaciones. "
        "Acto siete: En el punto culminante de la confrontación, la entidad colosal liberó una onda de choque electromagnética que selló el destino de la instalación. "
        "Acto ocho: Solo quedó el silencio sobre el páramo desolado. Los monolitos permanecen inmóviles, como guardianes eternos de lo que jamás debió ser despertado."
    )

    audio_path = long_dir / "narration.mp3"
    synthesize_speech_sync(raw_story, audio_path, voice="es-ES-AlvaroNeural")
    probe = probe_media(str(audio_path))
    audio_dur = float(probe.duration) if probe else 48.0

    # 1. Script Curator
    curator = CinematicScriptCuratorAgent()
    script = curator.curate(
        raw_text=raw_story,
        title=title,
        channel_lane="moku-horror-long",
        target_format="longform",
        words_per_minute=145.0,
    )

    # 2. Art Director
    art_director = ArtDirectorMoodAgent()
    visual_plan = art_director.plan_visuals(
        cinematic_script=script,
        theme_lane="cosmic_horror",
    )

    # 3. Scene Planner
    planner = ScenePlannerCompositorAgent()
    manifest = planner.plan_manifest(
        script=script,
        visual_plan=visual_plan,
        story_id="long_paramo_monolitos",
        narration_path=str(audio_path),
        channel_name="moku",
        resolution=[1920, 1080],
        fps=30,
        actual_audio_duration=audio_dur,
    )

    manifest_path = long_dir / "scene_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # 4. Render Catalog Loop Scenes
    raw_video = long_dir / "raw_procedural_scenes.mp4"
    proc_engine = LoopVideoEngine()
    proc_engine.render(manifest_path=manifest_path, output_video_path=raw_video)

    # 5. Subtitles
    subs_path = long_dir / "subtitles.ass"
    generate_karaoke_ass(raw_story, audio_dur, subs_path, is_vertical=False)

    # 6. Composite Master Video
    master_video = long_dir / "longform_master_1920x1080.mp4"
    assemble_master_video(
        raw_video_path=raw_video,
        audio_path=audio_path,
        subtitles_path=subs_path,
        output_path=master_video,
        width=1920,
        height=1080,
        fps=30,
    )

    # 7. Generate High-CTR Thumbnail
    thumb_engine = ThumbnailEngine()
    thumb_path = long_dir / "longform_thumbnail.jpg"
    thumb_cfg = ThumbnailConfig(
        title="EL PÁRAMO DE LOS MONOLITOS",
        hook_text="MONOLITOS DEL VACÍO",
        channel_id="moku",
        output_path=thumb_path,
        width=1920,
        height=1080,
        accent_color="#00FF66",
        primary_color="#FFE600",
    )
    thumb_res = thumb_engine.generate(
        config=thumb_cfg,
        video_path=master_video,
        manifest_path=manifest_path,
    )

    return {
        "format": "longform",
        "title": f"[REGISTRO CLASIFICADO] {title} | Moku",
        "description": "Una expedición al límite septentrional revela la verdad oculta tras los monolitos ciclópeos y la niebla del vacío.\n\n#Terror #Misterio #SCP #Horror #Moku",
        "video_path": master_video,
        "thumbnail_path": thumb_res,
        "duration": audio_dur,
        "manifest": manifest,
    }


def upload_production(prod_data: Dict[str, Any]) -> str:
    v_path = Path(prod_data["video_path"])
    t_path = Path(prod_data["thumbnail_path"])
    title = prod_data["title"]
    desc = prod_data["description"]
    is_short = prod_data["format"] == "short"

    token_path = str(REPO_ROOT / "secrets" / "youtube_token.json")
    youtube = _youtube_service(token_path)

    logger.info("Uploading %s to YouTube: '%s'...", prod_data["format"], title)
    body = {
        "snippet": {
            "title": title,
            "description": desc,
            "tags": ["terror", "misterio", "scp", "moku", "relatos", "horror"],
            "categoryId": "24",
            "defaultLanguage": "es",
            "defaultAudioLanguage": "es",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(v_path.resolve()), chunksize=-1, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            logger.info("Upload progress: %d%%", int(status.progress() * 100))

    video_id = response.get("id")
    logger.info("Video uploaded successfully. Video ID: %s", video_id)

    # Set Custom High-CTR Thumbnail
    if t_path.is_file():
        try:
            logger.info("Setting custom thumbnail: %s", t_path)
            thumb_media = MediaFileUpload(str(t_path.resolve()), mimetype="image/jpeg")
            youtube.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()
            logger.info("Thumbnail applied successfully to video %s", video_id)
        except Exception as e:
            logger.warning("Could not set custom thumbnail for %s: %s", video_id, e)

    url = f"https://youtube.com/shorts/{video_id}" if is_short else f"https://youtu.be/{video_id}"
    return url


def main():
    logger.info("Starting Master Upgraded Showcase Production Pipeline (Synchronous Pure WebGL)...")
    
    # 1. Produce Short & Longform
    short_data = produce_short_production()
    long_data = produce_longform_production()

    # 2. Upload both to YouTube
    short_url = upload_production(short_data)
    long_url = upload_production(long_data)

    print("\n" + "=" * 80)
    print("🚀 PRODUCTIONS UPLOADED SUCCESSFULLY TO YOUTUBE!")
    print(f"🎬 SHORT VERTICAL (9:16):  {short_url}")
    print(f"🎬 LONGFORM VIDEO (16:9):   {long_url}")
    print("=" * 80 + "\n")

    # Write deployment summary
    summary_path = OUTPUT_DIR / "upload_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "short": {
                "title": short_data["title"],
                "url": short_url,
                "video_path": str(short_data["video_path"]),
                "thumbnail_path": str(short_data["thumbnail_path"]),
                "scenes": [s["procedural_config"]["template_name"] for s in short_data["manifest"]["scenes"]],
            },
            "longform": {
                "title": long_data["title"],
                "url": long_url,
                "video_path": str(long_data["video_path"]),
                "thumbnail_path": str(long_data["thumbnail_path"]),
                "scenes": [s["procedural_config"]["template_name"] for s in long_data["manifest"]["scenes"]],
            }
        }, f, indent=2)

if __name__ == "__main__":
    main()
