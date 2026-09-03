"""
src/cli/handlers/loop.py - CLI Handler for Web-Based Video Loops & Catalog Management.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from src.config import DEFAULT_DB_PATH
from src.core.catalog import LoopCatalogRepository
from src.media.loop_worker import LoopSynthesizerWorker, maintain_loop_buffer

logger = logging.getLogger("cli.loop")

__all__ = ["handle_loop"]


def handle_loop(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Entrypoint for `main.py loop` subcommands."""
    action = getattr(args, "loop_action", None) or "list"
    db_path = getattr(args, "db_path", DEFAULT_DB_PATH) or DEFAULT_DB_PATH
    as_json = getattr(args, "json", False)

    catalog = LoopCatalogRepository(db_path=db_path)
    worker = LoopSynthesizerWorker(db_path=db_path)

    if action in ("list", "catalog"):
        category = getattr(args, "category", None)
        orientation = getattr(args, "orientation", None)
        limit = getattr(args, "limit", 50)

        records = catalog.list_loops(category=category, orientation=orientation, limit=limit)
        if as_json:
            print(json.dumps([r.to_dict() for r in records], indent=2, ensure_ascii=False))
            return 0

        print(f"\n🎬 Catálogo de Video Loops Procedurales Web ({len(records)} registros):")
        print("=" * 95)
        print(f"{'ID':<28} | {'Categoría':<14} | {'Orientación':<10} | {'Tecnología':<12} | {'Uso':<5} | {'Tamaño':<8}")
        print("-" * 95)
        for r in records:
            size_kb = f"{r.file_size_bytes // 1024} KB"
            print(f"{r.loop_id:<28} | {r.category:<14} | {r.orientation:<10} | {r.technology:<12} | {r.usage_count:<5} | {size_kb:<8}")
        print("=" * 95)
        stats = catalog.get_stats()
        print(f"Total: {stats['total_loops']} loops | Categorías: {list(stats['by_category'].keys())}\n")
        return 0

    elif action == "generate":
        category = getattr(args, "category", "cosmic_horror")
        orientation = getattr(args, "orientation", "vertical")
        count = getattr(args, "count", 1)
        duration = getattr(args, "duration", 6.0)
        fps = getattr(args, "fps", 30)
        seed_base = getattr(args, "seed", None)

        if not as_json:
            print(f"🚀 Generando {count} bucle(s) procedural(es) web para '{category}' [{orientation}]...")
        generated = []
        for i in range(count):
            seed = (seed_base + i) if seed_base is not None else None
            rec = worker.synthesize_on_demand(
                category=category,
                orientation=orientation,
                seed=seed,
                duration_sec=duration,
                fps=fps,
            )
            generated.append(rec.to_dict())
            if not as_json:
                print(f"  ✅ Generado: {rec.loop_id} ({rec.file_size_bytes // 1024} KB) -> {rec.file_path}")

        if as_json:
            print(json.dumps(generated, indent=2, ensure_ascii=False))
        return 0


    elif action == "preview":
        category = getattr(args, "category", "cosmic_horror")
        orientation = getattr(args, "orientation", "vertical")
        seed = getattr(args, "seed", 42) or 42
        output = getattr(args, "output", None) or f"assets/loops/preview_{category}_{orientation}.png"

        rec = catalog.get_best_loop(category=category, orientation=orientation)
        if rec and Path(rec.file_path).exists():
            out_p = Path(output).resolve()
            out_p.parent.mkdir(parents=True, exist_ok=True)
            import subprocess
            subprocess.run([
                "ffmpeg", "-y", "-ss", "0.5", "-i", str(rec.file_path),
                "-vframes", "1", str(out_p)
            ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"🖼️ Vista previa generada en: {out_p}")
            return 0
        else:
            print(f"⚠️ No se encontró loop en catálogo para '{category}' [{orientation}].")
            return 1

    elif action == "audit":
        cleanup = getattr(args, "cleanup", False)
        report = catalog.audit_and_cleanup(auto_remove_missing=cleanup)
        if as_json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 0

        print("\n🔍 Auditoría de Integridad del Catálogo de Loops:")
        print("=" * 60)
        print(f"Total verificados : {report['total_checked']}")
        print(f"Válidos e íntegros: {report['valid']}")
        print(f"Archivos faltantes: {report['missing']}")
        print(f"SHA discrepantes  : {report['corrupted']}")
        if cleanup and report["removed_ids"]:
            print(f"Registros eliminados ({len(report['removed_ids'])}): {report['removed_ids']}")
        print("=" * 60 + "\n")
        return 0

    elif action in ("daemon", "maintain"):
        target = getattr(args, "target", 2)
        duration = getattr(args, "duration", 6.0)
        fps = getattr(args, "fps", 30)

        print(f"⚙️ Iniciando mantenimiento activo del buffer de bucles (objetivo: {target} por categoría)...")
        res = worker.maintain_buffer(
            target_per_category=target,
            duration_sec=duration,
            fps=fps,
        )
        if as_json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return 0

        print(f"✅ Mantenimiento completado: {res['generated_count']} nuevos loops generados en categorías: {res['updated_categories']}")
        return 0

    else:
        parser.print_help()
        return 1
