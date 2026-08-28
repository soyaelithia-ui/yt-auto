#!/usr/bin/env python3
"""
dev/upload_showcase_to_youtube.py - Uploads both generated showcase videos directly to YouTube.
"""
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from googleapiclient.http import MediaFileUpload
from src.youtube.uploader import _youtube_service
from lib.video import create_video_thumbnail


def upload_single_video(
    youtube,
    video_path: Path,
    thumbnail_path: Path,
    title: str,
    description: str,
    tags: list[str],
    is_short: bool = False,
) -> str:
    print(f"\n📤 Subiendo {'Short' if is_short else 'Video Largo'}: '{title}'...")
    
    # 1. Insert Video
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

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    
    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            print(f"   ⏳ Progreso de subida: {int(status.progress() * 100)}%")

    video_id = response.get("id")
    print(f"   ✅ Video subido con éxito. Video ID: {video_id}")

    # 2. Set Thumbnail
    if thumbnail_path.is_file():
        try:
            print(f"   🖼️ Subiendo miniatura ({thumbnail_path.name})...")
            thumb_media = MediaFileUpload(str(thumbnail_path), resumable=False)
            youtube.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()
            print(f"   ✅ Miniatura configurada.")
        except Exception as e:
            print(f"   ⚠️ No se pudo establecer miniatura personalizada: {e}")

    # 3. Return Link
    if is_short:
        return f"https://youtube.com/shorts/{video_id}"
    return f"https://youtu.be/{video_id}"


def main():
    token_path = PROJECT_ROOT / "secrets" / "youtube_token.json"
    youtube = _youtube_service(str(token_path))

    showcase_dir = PROJECT_ROOT / "output" / "showcase"
    short_video = showcase_dir / "showcase_short_vertical.mp4"
    long_video = showcase_dir / "showcase_longform_horizontal.mp4"

    short_thumb = showcase_dir / "thumbnail_short.jpg"
    long_thumb = showcase_dir / "thumbnail_long.jpg"

    # Create thumbnails
    if not short_thumb.is_file():
        create_video_thumbnail(
            title="INCIDENTE EN EL FARO 14",
            style="short",
            output_path=str(short_thumb),
        )
    if not long_thumb.is_file():
        create_video_thumbnail(
            title="EL PÁRAMO DE LOS MONOLITOS",
            style="creepypasta",
            output_path=str(long_thumb),
        )

    # Upload Short
    short_url = upload_single_video(
        youtube=youtube,
        video_path=short_video,
        thumbnail_path=short_thumb,
        title="Incidente en el Faro de la Fosa 14 #Shorts",
        description=(
            "Registro clasificado de vigilancia del Faro 14. "
            "Detección de anomalía hidroacústica y coloso en la fosa abisal.\n\n"
            "#terror #misterio #shorts #scp #anomalia #horror"
        ),
        tags=["terror", "scp", "misterio", "shorts", "faro", "abismo", "anomalia"],
        is_short=True,
    )

    # Upload Longform
    long_url = upload_single_video(
        youtube=youtube,
        video_path=long_video,
        thumbnail_path=long_thumb,
        title="La Travesía por el Páramo de los Monolitos Silentes | Relato de Horror Cósmico",
        description=(
            "Expedición a través de la estepa de cenizas grises hacia la estación 49. "
            "Un viaje hacia los límites de la consciencia, búnkeres olvidados y el vacío absoluto.\n\n"
            "#terror #horrorcosmico #creepypasta #misterio #audiolibro #scifi"
        ),
        tags=["terror", "horror cosmico", "creepypasta", "misterio", "monolitos", "relato de terror", "audiolibro"],
        is_short=False,
    )

    print("\n" + "=" * 80)
    print("🎉 AMBOS VIDEOS PUBLICADOS EXITOSAMENTE EN YOUTUBE")
    print("=" * 80)
    print(f"📱 Short Vertical:      {short_url}")
    print(f"🖥️ Video Largo:         {long_url}")
    print("=" * 80)


if __name__ == "__main__":
    main()
