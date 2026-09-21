"""Stage 1: Initialize repository, recover expired leases, claim story, resolve lane."""

from __future__ import annotations

import os
import socket
from collections.abc import Mapping
from typing import Any

from src.branding import get_channel_branding
from src.config import SETTINGS, get_channel_settings
from src.core.contracts.story import StoryRecord
from src.core.lanes import resolve_lane_for_run
from src.core.profiling import CanonicalStage, PipelineProfiler
from src.core.repository import QueueRepository, connect
from src.log import get_logger
from src.pipeline.utils import is_pipeline_test_environment as is_test_environment

from src.pipeline.context import ClaimedLeaseContext

logger = get_logger("pipeline.stages.stage_01_lease")


def _claim_or_enqueue_story(
    *,
    repository: QueueRepository,
    channel_key: Any,
    channel_name: str,
    settings: Any,
    database: str,
    lane_id: str | None,
    requested_story_id: str,
    story: StoryRecord | Mapping[str, Any] | None,
    directed: bool,
    generate_only: bool,
    owner: str,
    lease_seconds: int,
) -> StoryRecord | None:
    """Resolve story by direct argument, directed claim, or queue claim with scraper fallback."""
    if story is not None:
        return story if isinstance(story, StoryRecord) else StoryRecord.from_dict(story)
    if directed:
        exact = repository.claim_exact(
            requested_story_id,
            channel_key,
            owner=owner,
            mode="directed-generate-only" if generate_only else "directed-publish",
            lease_seconds=lease_seconds,
        )
        return StoryRecord.from_dict(exact) if exact else None
    if not is_test_environment():
        from src.core.scoring import filter_and_score_story
        from src.db import is_story_duplicate
        from src.scraper import fetch_reddit_stories

        stories = fetch_reddit_stories(subreddit=settings.source_feed, limit=25)
        ingest_lane = resolve_lane_for_run(channel_key, lane_id)
        for s_item in stories:
            if is_story_duplicate(channel_name, s_item["id"], s_item.get("content"), database):
                continue
            verdict = filter_and_score_story(s_item, lane=ingest_lane)
            if not verdict.passed:
                logger.info(
                    "Skipping Reddit story %s (hybrid=%.3f): %s",
                    s_item.get("id"),
                    verdict.hybrid_score,
                    verdict.rejection_summary or "quality_gate",
                )
                continue
            repository.enqueue(
                s_item["id"],
                s_item["title"],
                s_item["content"],
                s_item["url"],
                channel_key,
                score=int(verdict.db_rank_score),
                upvote_ratio=float(s_item.get("upvote_ratio") or 0.0),
                num_comments=int(s_item.get("num_comments") or 0),
                lane_id=getattr(ingest_lane, "id", None),
            )
    claimed = repository.claim(
        channel_key,
        owner=owner,
        mode="generate-only" if generate_only else "publish",
        lease_seconds=lease_seconds,
    )
    if claimed is None and is_test_environment():
        probe_lane = resolve_lane_for_run(channel_key, lane_id)
        is_vert = probe_lane.orientation == "vertical"
        repository.enqueue(
            f"sample-short-{channel_name}" if is_vert else f"sample-{channel_name}",
            "Las Escaleras Sin Fin" if is_vert else "Una historia de prueba",
            "Alguien dejó una escalera donde no debería estar. Cada piso parece el mismo, y el silencio se nota distinto."
            if is_vert
            else "Esta es una historia de prueba escrita en español para validar el sistema.",
            f"https://example.invalid/{channel_name}/{'sample-short' if is_vert else 'sample'}",
            channel_key,
        )
        claimed = repository.claim(
            channel_key,
            owner=owner,
            mode="generate-only" if generate_only else "publish",
            lease_seconds=lease_seconds,
        )
    return StoryRecord.from_dict(claimed) if claimed is not None else None


def stage_01_claim_lease(
    *,
    channel_key: Any,
    channel_name: str,
    db_path: str | None,
    story_id: str | None,
    story: StoryRecord | Mapping[str, Any] | None,
    directed: bool,
    generate_only: bool,
    owner: str | None,
    lane_id: str | None,
    profiler: PipelineProfiler,
) -> tuple[ClaimedLeaseContext | None, dict[str, Any] | None]:
    """Stage 1: Initialize repository, recover expired leases, claim story, resolve lane."""
    with profiler.phase(CanonicalStage.CLAIM_LEASE):
        settings = get_channel_settings(channel_key)
        branding = get_channel_branding(channel_name)
        database = db_path or str(SETTINGS.database_path)
        repository = QueueRepository(database)
        repository.initialize()
        try:
            repository.recover_expired_leases()
        except Exception as exc:
            logger.warning("Failed to recover expired leases on startup: %s", exc)
        if owner is None:
            owner = f"lane-{lane_id}:{socket.gethostname()}:{os.getpid()}" if lane_id else f"{socket.gethostname()}:{os.getpid()}"
        lease_seconds = SETTINGS.render_timeout_seconds + 1_800
        requested_story_id = str(story_id or (story.get("story_id") if story else "") or "").strip()

        claimed_story = _claim_or_enqueue_story(
            repository=repository,
            channel_key=channel_key,
            channel_name=channel_name,
            settings=settings,
            database=database,
            lane_id=lane_id,
            requested_story_id=requested_story_id,
            story=story,
            directed=directed,
            generate_only=generate_only,
            owner=owner,
            lease_seconds=lease_seconds,
        )
        if not claimed_story:
            return None, {
                "status": "STORY_NOT_CLAIMABLE" if directed else "NO_PENDING_STORIES",
                "channel": channel_name,
                **({"story_id": requested_story_id} if directed else {}),
            }

        lane = resolve_lane_for_run(channel_key, lane_id, story_row=dict(claimed_story))
        try:
            with connect(database) as conn:
                conn.execute("UPDATE stories SET lane_id = ? WHERE story_id = ?", (lane.id, str(claimed_story["story_id"])))
                run_id_val = str(claimed_story.get("run_id") or "")
                if run_id_val:
                    try:
                        conn.execute("UPDATE runs SET lane_id = ? WHERE run_id = ?", (lane.id, run_id_val))
                    except Exception:
                        pass
                conn.commit()
        except Exception:
            logger.debug("No se pudo persistir lane_id en la historia", exc_info=True)

        claimed_ctx = ClaimedLeaseContext(
            story=claimed_story,
            story_id=str(claimed_story["story_id"]),
            run_id=str(claimed_story.get("run_id") or ""),
            lane=lane,
            repository=repository,
            database=database,
            owner=owner,
            lease_seconds=lease_seconds,
            settings=settings,
            branding=branding,
        )
        return claimed_ctx, None
