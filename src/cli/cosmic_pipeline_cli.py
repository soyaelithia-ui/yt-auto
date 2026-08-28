#!/usr/bin/env python3
"""
src/cli/cosmic_pipeline_cli.py - Command-Line Interface for Cosmic/Analog Horror Video Pipeline.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add repo root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.narrative.schema import NarrativeArchetype, VideoFormat
from src.export.pipeline import CosmicVideoPipeline
from src.log import get_logger

logger = get_logger("cosmic_cli")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generador Audiovisual de Horror Cósmico, Analog Horror y Ciencia Ficción Procedural."
    )
    parser.add_argument(
        "--format",
        choices=["SHORT_VERTICAL", "LONG_HORIZONTAL"],
        default="SHORT_VERTICAL",
        help="Formato de salida del video: SHORT_VERTICAL (1080x1920) o LONG_HORIZONTAL (1920x1080).",
    )
    parser.add_argument(
        "--archetype",
        choices=[a.value for a in NarrativeArchetype],
        default=NarrativeArchetype.HYDROACOUSTIC_TELEMETRY.value,
        help="Arquetipo narrativo a generar.",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="Título o tema clasificado del expediente.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Duración del video en segundos (por defecto: 35s para Shorts, 240s para Horizontal).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Ruta de destino del archivo MP4 final.",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Fotogramas por segundo (default: 30).",
    )

    args = parser.parse_args()

    v_format = VideoFormat(args.format)
    pipeline = CosmicVideoPipeline()

    try:
        res = pipeline.generate_video(
            topic=args.topic,
            archetype=args.archetype,
            video_format=v_format,
            duration_sec=args.duration,
            output_mp4=args.output,
            fps=args.fps,
        )
        print(f"\n[OK] Video generado con éxito:")
        print(f"  Ruta: {res['video_path']}")
        print(f"  Resolución: {res['width']}x{res['height']}")
        print(f"  Duración: {res['duration_sec']:.1f}s @ {res['fps']}fps\n")
        return 0
    except Exception as exc:
        logger.exception("Error en pipeline cósmico: %s", exc)
        print(f"\n[ERROR] Fallo en la generación de video: {exc}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
