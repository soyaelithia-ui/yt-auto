"""Operations on loop catalog (loops_catalog.db), bank validation and synchronization."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from src.core.catalog import (
    CHANNEL_CATEGORIES,
    CHANNEL_THEMES,
    SYNTHETIC_MONOCHROME_LOOP_IDS,
    LoopCatalogRepository,
    LoopRecord,
    compute_file_sha256,
    resolve_loop_file_path,
)

__all__ = [
    "LoopRecord",
    "LoopCatalogRepository",
    "compute_file_sha256",
    "resolve_loop_file_path",
    "CHANNEL_CATEGORIES",
    "CHANNEL_THEMES",
    "SYNTHETIC_MONOCHROME_LOOP_IDS",
    "sync_catalog_from_assets",
    "audit_and_cleanup_catalog",
]


def sync_catalog_from_assets(
    repo: LoopCatalogRepository,
    assets_dir: str | Path | None = None,
    *,
    purge_missing: bool = False,
    force_rescan: bool = False,
) -> int:
    """Synchronize bank video loop assets into loops_catalog.db."""
    return repo.sync_catalog_from_assets(
        assets_dir=assets_dir,
        purge_missing=purge_missing,
        force_rescan=force_rescan,
    )


def audit_and_cleanup_catalog(
    repo: LoopCatalogRepository,
    *,
    auto_remove_missing: bool = False,
) -> Dict[str, Any]:
    """Audit catalog records against disk assets and return summary report."""
    return repo.audit_and_cleanup(auto_remove_missing=auto_remove_missing)
