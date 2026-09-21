"""
src/cli/publish_cosmic_videos.py - Publish Cosmic & Analog Horror Videos to YouTube API v3.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image, ImageDraw, ImageFont, ImageEnhance

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.config import YOUTUBE_TOKEN_PATH
from src.core.google_auth import build_youtube_service
from src.log import get_logger

logger = get_logger("publish_cosmic_videos")


def create_analog_thumbnail(
    video_path: Path,
    output_thumb_path: Path,
    title_text: str,
    subtitle_text: str,
    width: int,
    height: int,
) -> Path:
    """Generates a high-contrast analog horror thumbnail from video frame or procedural canvas."""
    frame_path = output_thumb_path.parent / f"frame_{output_thumb_path.stem}.png"
    
    extracted = False
    if video_path.is_file():
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-ss", "00:00:01.000",
                    "-i", str(video_path),
                    "-vframes", "1",
                    str(frame_path),
                ],
                capture_output=True,
                check=True,
            )
            extracted = frame_path.is_file() and frame_path.stat().st_size > 0
        except Exception as e:
            logger.warning("No se pudo extraer frame del video, generando canvas procedural: %s", e)

    if extracted:
        img = Image.open(frame_path).resize((width, height), Image.Resampling.LANCZOS)
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.3)
    else:
        img = Image.new("RGB", (width, height), (3, 20, 13))

    # Vignette & dark grading overlays
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    
    # Top and bottom gradient shadows
    top_h = int(height * 0.35)
    for y in range(top_h):
        alpha = int(220 * (1.0 - (y / top_h)))
        draw_ov.line([(0, y), (width, y)], fill=(2, 10, 8, alpha))
        
    bot_h = int(height * 0.45)
    for y in range(height - bot_h, height):
        alpha = int(245 * ((y - (height - bot_h)) / bot_h))
        draw_ov.line([(0, y), (width, y)], fill=(2, 10, 8, alpha))
        
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Fonts
    try:
        font_main = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size=int(width * 0.052))
        font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", size=int(width * 0.032))
    except Exception:
        font_main = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    # Telemetry Header Badge
    draw.rectangle(
        [int(width * 0.04), int(height * 0.05), int(width * 0.96), int(height * 0.11)],
        outline=(0, 255, 102),
        width=3,
    )
    draw.text(
        (int(width * 0.07), int(height * 0.065)),
        "REC [●] // REGISTRO CLASIFICADO NIVEL-5",
        fill=(0, 255, 102),
        font=font_sub,
    )

    # Main title with shadow
    y_pos_title = int(height * 0.68)
    for off_x, off_y in [(-3, -3), (3, 3), (-3, 3), (3, -3), (0, 4)]:
        draw.text(
            (int(width * 0.05) + off_x, y_pos_title + off_y),
            title_text,
            fill=(0, 0, 0),
            font=font_main,
        )
    draw.text(
        (int(width * 0.05), y_pos_title),
        title_text,
        fill=(255, 230, 80),
        font=font_main,
    )

    # Subtitle
    y_pos_sub = int(height * 0.84)
    draw.text(
        (int(width * 0.05), y_pos_sub),
        subtitle_text,
        fill=(0, 255, 102),
        font=font_sub,
    )

    output_thumb_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_thumb_path), "JPEG", quality=95)
    logger.info("✅ Miniatura analógica generada: %s (%dx%d)", output_thumb_path.name, width, height)
    return output_thumb_path


def upload_to_youtube_direct(
    video_path: Path,
    thumbnail_path: Path,
    title: str,
    description: str,
    tags: List[str],
    token_path: str = YOUTUBE_TOKEN_PATH,
    privacy_status: str = "public",
) -> Dict[str, Any]:
    """Uploads video to YouTube channel via Google API Client with automatic chunked upload."""
    from googleapiclient.http import MediaFileUpload

    logger.info("Iniciando subida a YouTube: '%s' (%s)", title, video_path.name)
    youtube = build_youtube_service(token_path=token_path)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags,
            "categoryId": "24",  # Entertainment
            "defaultLanguage": "es",
            "defaultAudioLanguage": "es",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video_path), chunksize=5 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info("Progreso de subida: %d%%", int(status.progress() * 100))

    video_id = response.get("id")
    if not video_id:
        raise RuntimeError(f"YouTube no retornó ID de video: {response}")

    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    short_url = f"https://youtu.be/{video_id}"
    logger.info("✅ Video publicado exitosamente: ID=%s | URL=%s", video_id, watch_url)

    # Set Custom Thumbnail
    if thumbnail_path.is_file():
        try:
            logger.info("Adjuntando miniatura personalizada: %s", thumbnail_path.name)
            thumb_media = MediaFileUpload(str(thumbnail_path), resumable=False)
            youtube.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()
            logger.info("✅ Miniatura personalizada establecida para video %s", video_id)
        except Exception as exc:
            logger.warning("No se pudo establecer la miniatura personalizada en YouTube: %s", exc)

    return {
        "status": "PUBLISHED",
        "video_id": video_id,
        "watch_url": watch_url,
        "short_url": short_url,
        "title": title,
        "privacy": privacy_status,
        "file": str(video_path),
    }


def publish_all_cosmic_videos() -> List[Dict[str, Any]]:
    """Publishes both generated cosmic horror videos to YouTube."""
    results = []

    # 1. Video 1: Short Vertical
    short_video = ROOT_DIR / "output" / "cosmic_marianas_short_1080x1920.mp4"
    if not short_video.is_file():
        # Fallback to test_short_5s.mp4 if present
        alt = ROOT_DIR / "output" / "test_short_5s.mp4"
        if alt.is_file():
            short_video = alt

    short_thumb = ROOT_DIR / "output" / "cosmic_marianas_short_thumbnail.jpg"
    create_analog_thumbnail(
        video_path=short_video,
        output_thumb_path=short_thumb,
        title_text="FOSA DE LAS MARIANAS\nANOMALÍA BLOOP-7",
        subtitle_text="PROFUNDIDAD: -11,400M // SEÑAL HIDROACÚSTICA",
        width=1080,
        height=1920,
    )

    short_title = "FOSA DE LAS MARIANAS // Registro Hidroacústico Anomalía Bloop-7 #Shorts"
    short_desc = """REC [●] REGISTRO HIDROACÚSTICO CLASIFICADO NIVEL-5
Ubicación: Fosa de las Marianas (-11,400 metros de profundidad).
Las boyas sumergidas registraron una fluctuación rítmica no biológica de frecuencia ultrabaja.

⚠️ Audio masterizado con sub-drone binaural y filtro hidroacústico analógico.

#HorrorCosmico #AnalogHorror #Shorts #FosaDeLasMarianas #Creepypasta #Misterio #Paranormal #DeepSea"""

    short_tags = [
        "horror cosmico",
        "analog horror",
        "fosa de las marianas",
        "bloop",
        "short",
        "shorts",
        "misterio",
        "terror",
        "audio log",
        "creepypasta",
    ]

    res_short = upload_to_youtube_direct(
        video_path=short_video,
        thumbnail_path=short_thumb,
        title=short_title,
        description=short_desc,
        tags=short_tags,
    )
    results.append(res_short)

    # 2. Video 2: Longform Horizontal
    long_video = ROOT_DIR / "output" / "cosmic_containment_long_1920x1080.mp4"
    long_thumb = ROOT_DIR / "output" / "cosmic_containment_long_thumbnail.jpg"
    create_analog_thumbnail(
        video_path=long_video,
        output_thumb_path=long_thumb,
        title_text="PROTOCOLO DE CONTENCIÓN\nDIRECTIVA C-88",
        subtitle_text="FALLO DE ANOMALÍA COGNITIVA // SECTOR DEPURADO",
        width=1920,
        height=1080,
    )

    long_title = "PROTOCOLO DE CONTENCIÓN CLASIFICADO // Directiva C-88 [Horror Cósmico]"
    long_desc = """DOCUMENTO OFICIAL // NIVEL DE ACCESO ULTRASECRETO
Directiva C-88: Manual de Procedimientos ante Fallo de Contención de Entidades No Euclidianas y Distorsión Ontológica.

Índice de Telemetría:
00:00 - Transmisión de Emergencia y Telemetría Base
00:02 - Activación de Sensores y Detección de Micro-anomalía
00:05 - Escalada de Presión y Deformación Espaciotemporal
00:08 - Protocolo de Depuración y Aislamiento del Sector

⚠️ Producción audiovisual generada con motor procedural WebGL Rec.709, CRT phosphor shaders y audio binaural sub-drone EBU R128 (-16 LUFS).

#AnalogHorror #HorrorCosmico #FundacionSCP #CienciaFiccion #Terror #Documental #Misterio"""

    long_tags = [
        "horror cosmico",
        "analog horror",
        "protocolo de contencion",
        "directiva c88",
        "terror psicologico",
        "creepypasta",
        "misterio",
        "ciencia ficcion",
        "fundacion scp",
    ]

    if long_video.is_file():
        res_long = upload_to_youtube_direct(
            video_path=long_video,
            thumbnail_path=long_thumb,
            title=long_title,
            description=long_desc,
            tags=long_tags,
        )
        results.append(res_long)

    return results


if __name__ == "__main__":
    published = publish_all_cosmic_videos()
    print("\n" + "=" * 60)
    print("🎬 VIDEOS PUBLICADOS EN YOUTUBE:")
    print("=" * 60)
    for p in published:
        print(f"▶ [{p['video_id']}] {p['title']}")
        print(f"   URL: {p['watch_url']}")
        print(f"   Short URL: {p['short_url']}\n")
    print("=" * 60)
