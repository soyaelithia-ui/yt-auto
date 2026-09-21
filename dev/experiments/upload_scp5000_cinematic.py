#!/usr/bin/env python3
"""
dev/upload_scp5000_cinematic.py - Upload the 100% Code-Based Multi-Scene SCP-5000 Video & Short to YouTube.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from src.youtube.uploader import upload_video_via_api

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("upload_scp5000_cinematic")

OUTPUT_DIR = ROOT_DIR / "output"

cand1 = ROOT_DIR / "secrets" / "youtube_token.json"
cand2 = ROOT_DIR / "secrets" / "unified_credentials" / "google_cloud_youtube" / "youtube_token_primary_moku.json"
TOKEN_PATH = cand1 if cand1.is_file() else cand2

def main():
    logger.info("🔑 Usando token OAuth: %s", TOKEN_PATH)
    results = {}

    # 1. Upload Longform Multi-Scene Video
    long_video = OUTPUT_DIR / "scp5000_why_longform_1080p.mp4"
    long_thumb = OUTPUT_DIR / "scp5000_thumbnail_hd.jpg"
    long_title = "SCP-5000: ¿Por Qué? - La Guerra de la Fundación contra la Humanidad"
    from src.branding import get_channel_branding
    branding = get_channel_branding("moku")

    long_desc = (
        f"{long_title}\n\n"
        "Dentro del Sitio-62C fue hallado un traje mecánico chamuscado con el cadáver de un técnico y una grabación imposible: "
        "la historia de cuando la Fundación SCP decidió exterminar deliberadamente a toda la especie humana tras descubrir un parásito cósmico en el alma humana.\n\n"
        "TIMESTAMPS:\n"
        "00:00 - Acto 1: El Hallazgo del Traje SCP-5000 en el Sitio-62C\n"
        "01:13 - Acto 2: El Proyecto Pneuma y el Mapeo de la Noosfera\n"
        "02:27 - Acto 3: La Declaración de Guerra del Consejo O5\n"
        "03:41 - Acto 4: El Despliegue Masivo de Anomalías (682, 096, 173)\n"
        "04:55 - Acto 5: La Caída de Ganzir y las Fuerzas de Contención\n"
        "06:08 - Acto 6: La Odisea de Pietro Wilson con la Maleta SCP-055\n"
        "07:22 - Acto 7: El Sacrificio Final en el Abismo de SCP-579\n"
        "08:36 - Acto 8: El Reinicio de la Realidad y la Nota: ¿Por Qué?\n\n"
        f"🔔 Suscríbete a {branding.handle} para más expedientes clasificados y documentales de la Fundación SCP.\n\n"
        "#SCP #SCP5000 #FundacionSCP #TerrorPsicologico #DocumentalSCP #Creepypasta"
    )
    long_tags = [
        "SCP", "SCP-5000", "SCP 5000", "Por Que", "Fundacion SCP",
        "Terror Psicologico", "Documental SCP", "Creepypasta", "Pietro Wilson",
        "Proyecto Pneuma", "Consejo O5", branding.display_name
    ]

    logger.info("🚀 [1/2] Subiendo Video Largo Multi-Escena: %s", long_title)
    uploaded_long_id = None
    def on_long_id(vid: str):
        nonlocal uploaded_long_id
        uploaded_long_id = vid
        logger.info("🎯 Video ID asignado para Longform: %s", vid)

    res_long = upload_video_via_api(
        video_path=str(long_video),
        title=long_title,
        description=long_desc,
        tags=long_tags,
        thumbnail_path=str(long_thumb),
        token_path=str(TOKEN_PATH),
        on_video_id=on_long_id,
        channel="moku",
    )
    final_long_id = res_long.get("video_id") or uploaded_long_id
    long_url = f"https://www.youtube.com/watch?v={final_long_id}"
    results["longform"] = {
        "title": long_title,
        "video_id": final_long_id,
        "url": long_url,
    }
    logger.info("✅ VIDEO LARGO PUBLICADO: %s", long_url)

    # 2. Upload Short Video
    short_video = OUTPUT_DIR / "scp5000_why_short_1080x1920.mp4"
    short_thumb = OUTPUT_DIR / "scp5000_short_thumbnail.jpg"
    short_title = "¿Por Qué la Fundación SCP Declaró la Guerra a la Humanidad? #Shorts #SCP #SCP5000"
    short_desc = (
        "En el año 2020, el Consejo O5 tomó la decisión más aterradora de la historia: "
        "liberar a todos los monstruos para exterminar a la humanidad. Un solo técnico sobrevivió dentro del traje SCP-5000 para reiniciar la realidad.\n\n"
        f"#Shorts #SCP #SCP5000 #FundacionSCP #Terror #Creepypasta #{branding.display_name}"
    )
    short_tags = [
        "Shorts", "SCP", "SCP-5000", "SCP 5000", "Fundacion SCP",
        "Terror", "Creepypasta", branding.display_name
    ]

    logger.info("🚀 [2/2] Subiendo Short Vertical: %s", short_title)
    uploaded_short_id = None
    def on_short_id(vid: str):
        nonlocal uploaded_short_id
        uploaded_short_id = vid
        logger.info("🎯 Video ID asignado para Short: %s", vid)

    res_short = upload_video_via_api(
        video_path=str(short_video),
        title=short_title,
        description=short_desc,
        tags=short_tags,
        thumbnail_path=str(short_thumb),
        token_path=str(TOKEN_PATH),
        on_video_id=on_short_id,
        channel="moku",
    )
    final_short_id = res_short.get("video_id") or uploaded_short_id
    short_yt_url = f"https://www.youtube.com/shorts/{final_short_id}"
    results["short"] = {
        "title": short_title,
        "video_id": final_short_id,
        "url": f"https://www.youtube.com/watch?v={final_short_id}",
        "shorts_url": short_yt_url,
    }
    logger.info("✅ SHORT VERTICAL PUBLICADO: %s", short_yt_url)

    print("\n" + "=" * 68)
    print("🎉 ¡SUBIDA MULTI-ESCENA A YOUTUBE COMPLETADA EXITOSAMENTE!")
    print("=" * 68)
    print(f"🎬 Video Largo: {long_url}")
    print(f"📱 Short:       {short_yt_url}")
    print("=" * 68 + "\n")

    with open(OUTPUT_DIR / "uploaded_scp5000_multi_act_urls.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    return 0

if __name__ == "__main__":
    sys.exit(main())
