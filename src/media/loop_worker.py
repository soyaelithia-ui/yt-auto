"""
src/media/loop_synthesizer_worker.py - Autonomous Background Loop Synthesizer & Buffer Maintainer.

Continuously monitors the local SQLite loop catalog and synthesizes new procedural
web-based video loops (HTML5 Canvas / WebGL / Three.js / CSS) to ensure a healthy,
diverse stock of background loops across all channels, lanes, and thematic categories.
"""
from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.config import DEFAULT_DB_PATH
from src.core.catalog import LoopCatalogRepository, LoopRecord
from src.log import get_logger
from src.media.web_renderer import (
    CATEGORY_TECH_MAP,
    RenderSpec,
    THEMATIC_TEMPLATES,
    WebVideoRenderer,
)

logger = get_logger("loop_synthesizer_worker")

__all__ = [
    "LoopSynthesizerWorker",
    "maintain_loop_buffer",
    "synthesize_on_demand",
]

DEFAULT_CATEGORIES = (
    "cosmic_horror",
    "monsters",
    "dark_ambient",
    "dark_forest",
    "space_abyss",
    "scp",
    "drama_aita",
)


class LoopSynthesizerWorker:
    """Autonomous worker maintaining loop stock across all thematic categories."""

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        renderer: Optional[WebVideoRenderer] = None,
    ) -> None:
        self.db_path = db_path
        self.catalog = LoopCatalogRepository(db_path=db_path)
        self.renderer = renderer or WebVideoRenderer(db_path=db_path)

    def count_loops_for_category(self, category: str, orientation: str) -> int:
        """Counts existing valid loops for category and orientation in the database."""
        records = self.catalog.list_loops(category=category, orientation=orientation, limit=1000)
        valid = [r for r in records if Path(r.file_path).is_file() and Path(r.file_path).stat().st_size > 0]
        return len(valid)

    def maintain_buffer(
        self,
        target_per_category: int = 2,
        categories: Sequence[str] = DEFAULT_CATEGORIES,
        orientations: Sequence[str] = ("vertical", "horizontal"),
        duration_sec: float = 6.0,
        fps: int = 30,
    ) -> Dict[str, Any]:
        """
        Scans catalog stock and automatically generates missing loops up to target.
        """
        logger.info(
            "Starting autonomous loop buffer maintenance (target=%d/cat, orient=%s)",
            target_per_category, orientations
        )
        total_generated = 0
        updated_categories: List[str] = []

        for cat in categories:
            cat_norm = cat.strip().lower().replace("-", "_").replace(" ", "_")
            for orient in orientations:
                orient_norm = "horizontal" if orient in ("horizontal", "16:9") else "vertical"
                current_count = self.count_loops_for_category(cat_norm, orient_norm)
                needed = target_per_category - current_count

                if needed > 0:
                    logger.info(
                        "Category '%s' [%s] stock is %d/%d. Synthesizing %d new loop(s)...",
                        cat_norm, orient_norm, current_count, target_per_category, needed
                    )
                    for _ in range(needed):
                        seed = random.randint(1000, 999999)
                        spec = RenderSpec(
                            category=cat_norm,
                            orientation=orient_norm,
                            duration_sec=duration_sec,
                            fps=fps,
                            seed=seed,
                        )
                        try:
                            rec = self.renderer.render_loop(spec, register_in_db=True)
                            total_generated += 1
                            if cat_norm not in updated_categories:
                                updated_categories.append(cat_norm)
                            time.sleep(0.05)
                        except Exception as e:
                            logger.error("Failed synthesizing loop for %s [%s]: %s", cat_norm, orient_norm, e)

        logger.info(
            "Loop buffer maintenance complete: %d new loop(s) generated across %s",
            total_generated, updated_categories
        )
        return {
            "generated_count": total_generated,
            "updated_categories": updated_categories,
            "timestamp": time.time(),
        }

    def synthesize_on_demand(
        self,
        category: str,
        orientation: str = "vertical",
        seed: Optional[int] = None,
        duration_sec: float = 6.0,
        fps: int = 30,
    ) -> LoopRecord:
        """Synthesizes a single thematic loop immediately on-demand."""
        seed_val = seed if seed is not None else random.randint(1000, 999999)
        spec = RenderSpec(
            category=category,
            orientation=orientation,
            duration_sec=duration_sec,
            fps=fps,
            seed=seed_val,
        )
        return self.renderer.render_loop(spec, register_in_db=True)


def maintain_loop_buffer(
    target_per_category: int = 2,
    db_path: str = DEFAULT_DB_PATH,
    categories: Sequence[str] = DEFAULT_CATEGORIES,
    orientations: Sequence[str] = ("vertical", "horizontal"),
    duration_sec: float = 6.0,
    fps: int = 30,
) -> Dict[str, Any]:
    worker = LoopSynthesizerWorker(db_path=db_path)
    return worker.maintain_buffer(
        target_per_category=target_per_category,
        categories=categories,
        orientations=orientations,
        duration_sec=duration_sec,
        fps=fps,
    )


def synthesize_on_demand(
    category: str,
    orientation: str = "vertical",
    db_path: str = DEFAULT_DB_PATH,
    seed: Optional[int] = None,
) -> LoopRecord:
    worker = LoopSynthesizerWorker(db_path=db_path)
    return worker.synthesize_on_demand(category=category, orientation=orientation, seed=seed)
