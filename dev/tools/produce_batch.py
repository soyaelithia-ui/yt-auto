#!/usr/bin/env python3
"""
dev/produce_batch.py - High-Volume Multi-Channel Production Batch Runner.

Orchestrates concurrent or sequential production batches across channels ('horror', 'drama')
and editorial formats ('short', 'longform') with structured progress tracking and notifications.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from src.core.scheduler import AUTO_TOPICS
from src.core.scenic_detector import detect_scenic_loop
from src.agents.image_auditor import ImageAuditorAgent
from src.agents.seo_optimizer import SeoOptimizerAgent
from src.telegram.notifier import TelegramNotifier
from src.log import get_logger

logger = get_logger("dev_produce_batch")


def run_batch(
    count: int = 3,
    channels: List[str] = ["moku"],
    format_mode: str = "short",
    dry_run: bool = False,
    dispatch_telegram: bool = False,
) -> Dict[str, Any]:
    logger.info("=======================================================")
    logger.info("🚀 Iniciando Lote de Producción Multi-Canal (%d entregables)", count)
    logger.info("Canales: %s | Formato: %s | Modo: %s", channels, format_mode, "DRY-RUN" if dry_run else "PROD")
    logger.info("=======================================================")

    notifier = TelegramNotifier() if dispatch_telegram else None
    if notifier:
        notifier.send_message(f"🚀 *Lote de Producción Iniciado*: {count} videos ({format_mode}) para {', '.join(channels)}")

    batch_results: List[Dict[str, Any]] = []
    seo_agent = SeoOptimizerAgent()
    img_auditor = ImageAuditorAgent()

    for idx in range(1, count + 1):
        channel = channels[(idx - 1) % len(channels)]
        topic = AUTO_TOPICS[(idx - 1) % len(AUTO_TOPICS)]
        job_id = f"batch_{int(time.time())}_{idx}"

        logger.info("\n--- [%d/%d] Canal: %s | Tema: '%s' ---", idx, count, channel, topic)
        start_t = time.time()

        # Step 1: Scenic loop
        scenic = detect_scenic_loop(topic, channel)

        # Step 2: SEO Optimization
        seo = seo_agent.optimize(topic, target_format=format_mode, niche=channel)

        # Step 3: Image Auditor vetting
        candidates = [
            {"id": f"asset_brand_{idx}", "name": f"Emblema {channel.capitalize()}", "source_type": "official_emblem"},
            {"id": f"asset_filler_{idx}", "name": "Foto de Stock Genérica", "source_type": "generic_filler_photo"},
        ]
        audits = img_auditor.audit_candidates(topic, candidates, channel_lane=f"{channel}-{format_mode}")

        elapsed = time.time() - start_t

        item_result = {
            "index": idx,
            "job_id": job_id,
            "channel": channel,
            "topic": topic,
            "scenic_loop": scenic,
            "selected_title": seo["selected_title"],
            "audits_summary": f"{audits['approved_count']} Aprobados / {audits['discarded_count']} Descartados",
            "elapsed_seconds": round(elapsed, 2),
            "status": "COMPLETED" if dry_run else "READY",
        }
        batch_results.append(item_result)
        logger.info("Entregable #%d preparado en %.2fs: '%s'", idx, elapsed, seo["selected_title"])

        if notifier:
            notifier.send_message(
                f"✅ *[{idx}/{count}] Entregable Procesado* ({channel}):\n"
                f"• Título: `{seo['selected_title']}`\n"
                f"• Bucle 3D: `{scenic}`\n"
                f"• Auditoría: {item_result['audits_summary']}"
            )

    summary = {
        "status": "SUCCESS",
        "total_requested": count,
        "completed": len(batch_results),
        "results": batch_results,
    }

    if notifier:
        notifier.send_message(f"🎉 *Lote de producción completado con éxito*: {len(batch_results)} entregables generados.")

    logger.info("=======================================================")
    logger.info("✅ Lote completado exitosamente: %d entregables listos.", len(batch_results))
    logger.info("=======================================================")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="High-Volume Multi-Channel Production Batch Runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--count", type=int, default=3, help="Número de videos a generar en el lote")
    parser.add_argument("--channels", nargs="+", default=["horror", "drama"], help="Canales objetivo ('horror' / canal 1, 'drama' / canal 2)")
    parser.add_argument("--format", type=str, default="short", choices=["short", "longform"], help="Formato de video")
    parser.add_argument("-d", "--dry-run", action="store_true", default=False, help="Ejecutar sin invocar renderizado pesado")
    parser.add_argument("--dispatch-telegram", action="store_true", default=False, help="Enviar alertas por Telegram")
    args = parser.parse_args()

    res = run_batch(
        count=args.count,
        channels=args.channels,
        format_mode=args.format,
        dry_run=args.dry_run,
        dispatch_telegram=args.dispatch_telegram,
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
