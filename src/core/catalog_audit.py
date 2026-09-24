"""
src/core/catalog_audit.py - Loop catalog integrity audit and synthetic placeholder cleanup.

Audits physical file existence, detects SHA-256 corruption, prunes orphan rows,
and purges synthetic monochrome placeholders.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Set

from src.core.catalog_sync import compute_file_sha256, resolve_loop_file_path
from src.log import get_logger

logger = get_logger("loop_catalog.audit")

SYNTHETIC_MONOCHROME_LOOP_IDS: Set[str] = {
    "loop_maritime_lighthouse_h_544374",
    "loop_arctic_desolation_v_800210",
}


def purge_synthetic_monochrome_loops(repo: Any) -> int:
    """Purges synthetic monochrome loops from the database."""
    sql = """
    DELETE FROM video_loops
    WHERE loop_id IN ('loop_maritime_lighthouse_h_544374', 'loop_arctic_desolation_v_800210')
       OR (technology = 'ffmpeg_lavfi' AND sha256 = 'procedural')
    """
    with repo._get_connection() as conn:
        cur = conn.execute(sql)
        deleted = cur.rowcount
        conn.commit()
    logger.info("Purged %d synthetic monochrome loops from catalog", deleted)
    return deleted


def audit_and_cleanup(repo: Any, auto_remove_missing: bool = False) -> Dict[str, Any]:
    """
    Audits physical file existence and SHA-256 integrity for all cataloged loops.
    Optionally removes database records pointing to missing files.
    """
    all_loops = repo.list_loops(limit=10000)
    valid_count = 0
    missing_count = 0
    corrupted_count = 0
    removed_ids: list[str] = []

    for rec in all_loops:
        p = resolve_loop_file_path(rec.file_path)
        if not p.is_file() or p.stat().st_size == 0:
            missing_count += 1
            if auto_remove_missing:
                repo.delete_loop(rec.loop_id, delete_file=False)
                removed_ids.append(rec.loop_id)
            continue

        current_sha = compute_file_sha256(p)
        if current_sha != rec.sha256:
            corrupted_count += 1
            logger.warning(
                "SHA mismatch for loop '%s': expected %s, got %s",
                rec.loop_id,
                rec.sha256,
                current_sha,
            )
        else:
            valid_count += 1

    return {
        "total_checked": len(all_loops),
        "valid": valid_count,
        "missing": missing_count,
        "corrupted": corrupted_count,
        "removed_ids": removed_ids,
    }
