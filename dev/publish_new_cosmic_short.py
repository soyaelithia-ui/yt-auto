#!/usr/bin/env python3
"""
dev/publish_new_cosmic_short.py - Generates a new YouTube Short video and uploads it directly.
"""
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from googleapiclient.http import MediaFileUpload
from src.export.pipeline import CosmicVideoPipeline
from src.narrative.schema import NarrativeArchetype, VideoFormat
from src.youtube.uploader import _youtube_service
from lib.video import create_video_thumbnail
from lib.ffmpeg import probe_media


def main():
    print("=================================================================")
    print("🎬 GENERANDO NUEVO VIDEO CON EL PIPELINE ARQUITECTÓNICO CORREGIDO")
    print("=================================================================")

    pipeline = CosmicVideoPipeline(work_dir="work/publish_run")
    out_dir = PROJECT_ROOT / "output" / "published"
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = int(time.time())
    mp4_filename = f"cosmic_short_{timestamp_str}.mp4"
    out_mp4 = out_dir / mp4_filename
    thumb_path = out_dir / f"thumbnail_{timestamp_str}.jpg"

    topic = "REGISTRO CLASIFICADO: ANOMALÍA HIDROACÚSTICA // SECTOR KERMADEC"

    res = pipeline.generate_video(
        topic=topic,
        archetype=NarrativeArchetype.HYDROACOUSTIC_TELEMETRY,
        video_format=VideoFormat.SHORT_VERTICAL,
        duration_sec=30.0,
        output_mp4=out_mp4,
        width=1080,
        height=1920,
        fps=30,
    )

    print("\n✅ Video generado localmente:")
    print(f"   📹 Ruta: {res['video_path']}")
    print(f"   🎵 Audio Dur: {res['audio_duration_sec']:.2f}s")
    print(f"   ⏱️ Video Dur: {res['duration_sec']:.2f}s ({res['total_frames']} frames)")

    probe = probe_media(res["video_path"])
    print(f"   🔍 Sonda FFprobe: {probe.duration:.2f}s | {probe.primary_video.width}x{probe.primary_video.height} @ {probe.primary_video.fps}fps")

    # Generate Thumbnail
    print("\n🖼️ Generando miniatura...")
    try:
        create_video_thumbnail(
            title="SEÑAL DEL ABISMO",
            style="short",
            output_path=str(thumb_path),
        )
    except Exception as th_err:
        print(f"   ⚠️ No se pudo generar miniatura personalizada: {th_err}")

    # YouTube Upload
    print("\n🚀 INICIANDO PUBLICACIÓN EN YOUTUBE...")
    token_path = PROJECT_ROOT / "secrets" / "youtube_token.json"
    youtube = _youtube_service(str(token_path))

    title = "SEÑAL DEL ABISMO: Registro 09-Omega // Trinchera Kermadec #Shorts"
    description = (
        "EXPEDIENTE CLASIFICADO NIVEL 5 // TELEMETRÍA HIDROACÚSTICA\n\n"
        "Transmisión anómala recuperada a 9.200 metros de profundidad. "
        "Audio procesado mediante cadena de radio/búnker y análisis espectral.\n\n"
        "#Shorts #Terror #AnalogHorror #Creepypasta #Misterio #SciFi"
    )
    tags = ["Shorts", "Analog Horror", "Terror", "Misterio", "Sci-Fi", "Creepypasta", "SCP", "Abismo"]

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "24",  # Entertainment
            "defaultLanguage": "es",
            "defaultAudioLanguage": "es",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(out_mp4), chunksize=-1, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            print(f"   ⏳ Progreso de subida: {int(status.progress() * 100)}%")

    video_id = response.get("id")
    print(f"\n🎉 VIDEO PUBLICADO EN YOUTUBE EXITOSAMENTE!")
    print(f"   📌 Video ID: {video_id}")

    # Set custom thumbnail if supported by the channel
    if thumb_path.is_file():
        try:
            print(f"   🖼️ Configurando miniatura...")
            thumb_media = MediaFileUpload(str(thumb_path), resumable=False)
            youtube.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()
            print("   ✅ Miniatura configurada.")
        except Exception as te:
            print(f"   ℹ️ Miniatura estándar asignada por YouTube ({te})")

    short_url = f"https://youtube.com/shorts/{video_id}"
    watch_url = f"https://youtu.be/{video_id}"

    print("\n=================================================================")
    print(f"🔗 ENLACE YOUTUBE SHORTS: {short_url}")
    print(f"🔗 ENLACE REPRODUCTOR DIRECTO: {watch_url}")
    print("=================================================================")


if __name__ == "__main__":
    main()
