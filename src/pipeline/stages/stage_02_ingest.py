"""Stage 2: Spanish source normalization, multistory gathering, and script curation."""

from __future__ import annotations

import os
from typing import Any

from src.config import LONG_MIN_WORDS
from src.core.domain import JobStatus
from src.core.profiling import CanonicalStage
from src.core.repository import connect
from src.log import get_logger
from src.pipeline.context import PipelineContext
from src.pipeline.utils import (
    _dispatch_curate_script,
    _record_combined_stories,
    is_pipeline_test_environment as is_test_environment,
)

logger = get_logger("pipeline.stages.stage_02_ingest")


def stage_02_ingest_translate(ctx: PipelineContext) -> None:
    """Stage 2: Spanish source normalization, multistory gathering, and script curation."""
    with ctx.profiler.phase(CanonicalStage.INGEST_TRANSLATE):
        if ctx.directed:
            ctx.repository.require_single_story_run(ctx.run_id, ctx.story_id)
        from src.llm import ensure_spanish_source

        ctx.content, ctx.title = ensure_spanish_source(str(ctx.story["content"]), str(ctx.story["title"]))

        additional: list[dict[str, Any]] = []
        ctx.is_long_lane = ctx.is_long_lane or (getattr(ctx.lane, "orientation", "") == "horizontal")
        if (
            not ctx.directed
            and ctx.lane.multistory_collection
            and len(ctx.content.split()) < max(LONG_MIN_WORDS, ctx.lane.words_min)
        ):
            target_words = max(LONG_MIN_WORDS, ctx.lane.words_min)
            current_words = len(ctx.content.split())
            with connect(ctx.database, read_only=True) as conn:
                for row in conn.execute(
                    "SELECT * FROM stories WHERE channel = ? AND (lane_id IS NULL OR lane_id = ?) AND status = ? AND story_id != ? ORDER BY created_at LIMIT 5",
                    (ctx.channel_name, ctx.lane.id, JobStatus.PENDING.value, ctx.story_id),
                ):
                    candidate = dict(row)
                    c_content, c_title = ensure_spanish_source(
                        str(candidate.get("content") or ""), str(candidate.get("title") or "")
                    )
                    candidate["content"], candidate["title"] = c_content, c_title
                    additional.append(candidate)
                    current_words += len(c_content.split())
                    if current_words >= target_words:
                        break
        ctx.used_ids = [ctx.story_id] + [str(item["story_id"]) for item in additional]
        if ctx.directed:
            if ctx.used_ids != [ctx.story_id]:
                raise RuntimeError("El modo directed intentó agregar historias adicionales")
            ctx.repository.require_single_story_run(ctx.run_id, ctx.story_id)
        else:
            _record_combined_stories(ctx.database, ctx.run_id, ctx.used_ids)

        ctx.words_min = int(ctx.lane.words_min) if not ctx.is_long_lane else max(LONG_MIN_WORDS, ctx.lane.words_min)
        ctx.words_max = getattr(ctx.lane, "words_max", 4500) if ctx.is_long_lane else ctx.lane.words_max
        curate_provider = "C" if is_test_environment() or os.environ.get("FAST_CURATE") == "1" else "A"
        ctx.script = _dispatch_curate_script(
            ctx.content,
            ctx.title,
            additional_stories=[] if not ctx.is_long_lane or ctx.directed else additional,
            min_words=ctx.words_min,
            provider=curate_provider,
            channel=ctx.channel_name,
            strict_single_story=ctx.directed or not ctx.is_long_lane,
            max_words=ctx.words_max,
        )
