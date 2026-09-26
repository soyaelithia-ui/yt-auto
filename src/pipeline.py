"""Safe end-to-end orchestration that preserves artifacts on every ambiguous result.

Backward-compatible facade delegating execution to the modular src.pipeline package.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

from src.core.domain import (
    AuthenticationError,
    JobStatus,
    LeaseOwnershipError,
    ManualInterventionRequired,
    ProviderTimeoutError,
    QuotaError,
    canonical_channel,
)
from src.core.guard import memory_checkpoint
from src.core.profiling import CanonicalStage, PipelineProfiler
from src.core.providers import CapabilityUnavailable
from src.log import get_logger
from src.observability import set_run_context
from src.pipeline.context import ClaimedLeaseContext, RunContext, active_heartbeat_scope
from src.pipeline.stages import (
    stage_01_claim_lease,
    stage_02_ingest_translate,
    stage_03_editorial_barrier,
    stage_04_mood_theme,
    stage_05_tts_synthesis,
    stage_06_duration_alignment,
    stage_07_subtitle_generation,
    stage_08_loop_scene,
    stage_09_video_rendering,
    stage_10_qa_gating,
    stage_11_thumbnail_metadata,
    stage_12_dedup_simhash,
    stage_13_backup_publish,
)
from src.pipeline.utils import (
    _apply_resume_plan_checkpoints,
    _handle_pipeline_exception,
    _marker,
    _prepare_pipeline_paths,
    _resolve_engine_mode,
)

logger = get_logger("pipeline")


def _dispatch_stage(name: str, default_fn: Callable, current_fn: Callable) -> Callable:
    """Resolve stage implementation dynamically from src.pipeline to honor test patches."""
    mod = sys.modules.get("src.pipeline")
    if mod is not None and hasattr(mod, name):
        resolved = getattr(mod, name)
        if callable(resolved) and resolved is not current_fn:
            return resolved
    return default_fn


def _stage_01_claim_lease(
    *,
    channel_key: Any,
    channel_name: str,
    db_path: str | None,
    story_id: str | None,
    story: dict[str, Any] | None,
    directed: bool,
    generate_only: bool,
    owner: str | None,
    lane_id: str | None,
    profiler: PipelineProfiler,
) -> tuple[ClaimedLeaseContext | dict[str, Any] | None, dict[str, Any] | None]:
    """Stage 1: Initialize repository, recover expired leases, claim story, resolve lane."""
    target = _dispatch_stage("_stage_01_claim_lease", stage_01_claim_lease, _stage_01_claim_lease)
    return target(
        channel_key=channel_key,
        channel_name=channel_name,
        db_path=db_path,
        story_id=story_id,
        story=story,
        directed=directed,
        generate_only=generate_only,
        owner=owner,
        lane_id=lane_id,
        profiler=profiler,
    )


def _stage_02_ingest_translate(ctx: RunContext) -> None:
    """Stage 2: Spanish source normalization, multistory gathering, and script curation."""
    _dispatch_stage("_stage_02_ingest_translate", stage_02_ingest_translate, _stage_02_ingest_translate)(ctx)


def _stage_03_editorial_barrier(ctx: RunContext) -> None:
    """Stage 3: Editorial barrier, beat extraction, pre-TTS validation, and script artifact persistence."""
    _dispatch_stage("_stage_03_editorial_barrier", stage_03_editorial_barrier, _stage_03_editorial_barrier)(ctx)


def _stage_04_mood_theme(ctx: RunContext) -> None:
    """Stage 4: Visual plan planning, shot pacing, and background audio resolution."""
    _dispatch_stage("_stage_04_mood_theme", stage_04_mood_theme, _stage_04_mood_theme)(ctx)


def _stage_05_tts_synthesis(ctx: RunContext) -> None:
    """Stage 5: Voice audio generation via TTS and optional EBU R128 mastering."""
    _dispatch_stage("_stage_05_tts_synthesis", stage_05_tts_synthesis, _stage_05_tts_synthesis)(ctx)


def _stage_06_duration_alignment(ctx: RunContext) -> None:
    """Stage 6: Re-condensation (shorts) or auto-expansion (longform) to align duration."""
    _dispatch_stage("_stage_06_duration_alignment", stage_06_duration_alignment, _stage_06_duration_alignment)(ctx)


def _stage_07_subtitle_generation(ctx: RunContext) -> None:
    """Stage 7: Subtitle creation (ASS & SRT) and grammar/syntax validation if active."""
    _dispatch_stage("_stage_07_subtitle_generation", stage_07_subtitle_generation, _stage_07_subtitle_generation)(ctx)


def _stage_08_loop_scene(ctx: RunContext) -> None:
    """Stage 8: Build scene manifest and resolve stream-copy / subtitle mux flags."""
    _dispatch_stage("_stage_08_loop_scene", stage_08_loop_scene, _stage_08_loop_scene)(ctx)


def _stage_09_video_rendering(ctx: RunContext) -> None:
    """Stage 9: Local asset video composition via stream-copy."""
    _dispatch_stage("_stage_09_video_rendering", stage_09_video_rendering, _stage_09_video_rendering)(ctx)


def _stage_10_qa_gating(ctx: RunContext) -> None:
    """Stage 10: Automated QA gating (validate_prepublication) and RENDERED status transition."""
    _dispatch_stage("_stage_10_qa_gating", stage_10_qa_gating, _stage_10_qa_gating)(ctx)


def _stage_11_thumbnail_metadata(ctx: RunContext) -> None:
    """Stage 11: Thumbnail generation (with climax frame extraction) and metadata persistence."""
    _dispatch_stage("_stage_11_thumbnail_metadata", stage_11_thumbnail_metadata, _stage_11_thumbnail_metadata)(ctx)


def _stage_12_dedup_simhash(ctx: RunContext) -> None:
    """Stage 12: SimHash and SHA256 deduplication gating against recent channel publications."""
    _dispatch_stage("_stage_12_dedup_simhash", stage_12_dedup_simhash, _stage_12_dedup_simhash)(ctx)


def _stage_13_backup_publish(ctx: RunContext) -> dict[str, Any]:
    """Stage 13: Drive backup, code verdict, Telegram human review gate, YouTube publish, and commit."""
    return _dispatch_stage("_stage_13_backup_publish", stage_13_backup_publish, _stage_13_backup_publish)(ctx)


def _record_production_metrics_lineage(
    ctx: RunContext,
    profiler: PipelineProfiler,
    scene_manifest_path: Path,
    video_path: Path,
    repository: Any,
    run_id: str,
    story_id: str,
) -> None:
    """Record scene asset lineage and aggregated telemetry metrics."""
    # Scene asset lineage (outside stage-9 timer — SQLite I/O is not render)
    try:
        if scene_manifest_path.exists():
            from src.visuals import SceneAssetTracker

            SceneAssetTracker(repository=repository).extract_and_record(
                run_id=run_id,
                story_id=story_id,
                manifest_path=scene_manifest_path,
            )
    except Exception as sat_err:
        logger.warning("Could not record scene assets in repository: %s", sat_err, exc_info=True)

    try:
        tts_phase = profiler.get_phase(CanonicalStage.TTS_SYNTHESIS)
        render_phase = profiler.get_phase(CanonicalStage.VIDEO_RENDERING)
        tts_sec = tts_phase.duration_sec if tts_phase else None
        render_elapsed = (
            ctx.compositor_metrics.get("render_time_sec", 0.0)
            if isinstance(ctx.compositor_metrics, dict) and "render_time_sec" in ctx.compositor_metrics
            else (render_phase.duration_sec if render_phase else 0.0)
        )
        video_size = video_path.stat().st_size if video_path.exists() else 0
        repository.record_production_metrics(
            run_id=run_id,
            story_id=story_id,
            audio_duration_sec=float(ctx.audio.get("duration_sec", 0.0) or 0.0),
            render_time_sec=float(render_elapsed),
            tts_time_sec=tts_sec,
            video_size_bytes=int(video_size),
            integrated_lufs=None,
            qa_audit_passed=(
                bool(ctx.visual_integrity_report.get("passed", True))
                if isinstance(ctx.visual_integrity_report, dict)
                else True
            ),
        )
    except Exception as pm_err:
        logger.warning("Could not record production metrics: %s", pm_err, exc_info=True)


def run_pipeline_once(
    *,
    channel: str,
    db_path: str | None = None,
    generate_only: bool = False,
    story_id: str | None = None,
    lane_id: str | None = None,
    video_engine: str | None = None,
    compositor: str | None = None,
    enable_subtitles: bool | None = None,
    loop_category: str | None = None,
    run_id: str | None = None,
    owner: str | None = None,
    story: dict[str, Any] | None = None,
    directed: bool | None = None,
    visual_pipeline: str | None = None,
) -> dict[str, Any]:
    """Produce exactly one video governed by its lane (config/lanes.json)."""
    channel_key = canonical_channel(channel)
    channel_name = channel_key.value
    if directed is None:
        directed = story is None and story_id is not None
    requested_story_id = str(story_id or (story.get("story_id") if story else "") or "").strip()
    if directed and not requested_story_id:
        raise ValueError("--story-id no puede estar vacío")

    profiler = PipelineProfiler(
        run_id=run_id or requested_story_id or None,
        story_id=requested_story_id or None,
        channel=channel_name,
    )

    claimed_ctx, early_exit = _stage_01_claim_lease(
        channel_key=channel_key,
        channel_name=channel_name,
        db_path=db_path,
        story_id=story_id,
        story=story,
        directed=directed,
        generate_only=generate_only,
        owner=owner,
        lane_id=lane_id,
        profiler=profiler,
    )
    if early_exit is not None:
        return early_exit

    story = claimed_ctx["story"]
    story_id = claimed_ctx["story_id"]
    run_id = str(story.get("run_id") or run_id or story_id)
    profiler.run_id = run_id
    profiler.story_id = story_id
    lane = claimed_ctx["lane"]
    if visual_pipeline and hasattr(lane, "with_overrides"):
        lane = lane.with_overrides({"visual_pipeline": visual_pipeline})
        claimed_ctx["lane"] = lane
    repository = claimed_ctx["repository"]

    engine_mode, is_loop_mode, _ = _resolve_engine_mode(lane, video_engine, compositor)
    is_multiscene_mode = False
    if engine_mode == "multiscene" and os.environ.get("FORCE_MULTISCENE", "0") != "1":
        logger.info("Coercing video_engine=%r to local loop mode", engine_mode)
        engine_mode = "loop"
        is_loop_mode = True
    subtitles_active = False
    if enable_subtitles is True:
        subtitles_active = True

    set_run_context(run_id=run_id, story_id=story_id, channel=channel_name, component="pipeline")
    memory_checkpoint("lease_claimed")

    paths = _prepare_pipeline_paths(run_id)
    pipe_mod = sys.modules.get("src.pipeline")
    marker_fn = getattr(pipe_mod, "_marker", _marker)
    marker_fn(paths["work_dir"], run_id, active=True)
    _apply_resume_plan_checkpoints(claimed_ctx["database"], story_id, lane.id, run_id, paths)

    ctx = RunContext(
        story=story,
        story_id=story_id,
        run_id=run_id,
        channel_name=channel_name,
        channel_key=channel_key,
        lane=lane,
        repository=repository,
        database=claimed_ctx["database"],
        owner=claimed_ctx["owner"],
        lease_seconds=claimed_ctx["lease_seconds"],
        settings=claimed_ctx["settings"],
        branding=claimed_ctx["branding"],
        profiler=profiler,
        directed=directed,
        generate_only=generate_only,
        engine_mode=engine_mode,
        is_loop_mode=is_loop_mode,
        is_multiscene_mode=is_multiscene_mode,
        subtitles_active=subtitles_active,
        loop_category=loop_category,
        **paths,
    )

    try:
        with active_heartbeat_scope(ctx):
            _stage_02_ingest_translate(ctx)
            _stage_03_editorial_barrier(ctx)
            _stage_05_tts_synthesis(ctx)
            _stage_06_duration_alignment(ctx)
            _stage_07_subtitle_generation(ctx)
            memory_checkpoint("render_start")
            _stage_04_mood_theme(ctx)
            _stage_08_loop_scene(ctx)
            _stage_09_video_rendering(ctx)

            _record_production_metrics_lineage(
                ctx=ctx,
                profiler=profiler,
                scene_manifest_path=paths["scene_manifest_path"],
                video_path=paths["video_path"],
                repository=repository,
                run_id=run_id,
                story_id=story_id,
            )

            _stage_11_thumbnail_metadata(ctx)
            _stage_12_dedup_simhash(ctx)
            _stage_10_qa_gating(ctx)
            return _stage_13_backup_publish(ctx)

    except LeaseOwnershipError:
        return ctx.lease_lost_result()
    except CapabilityUnavailable as exc:
        return _handle_pipeline_exception(
            exc, code=getattr(exc, "code", "CapabilityUnavailable"), status=JobStatus.RETRYABLE_FAILED, retry_delay=900, ctx=ctx
        )
    except QuotaError as exc:
        target = (
            JobStatus.WAITING_IMAGE_QUOTA
            if not paths["thumbnail_path"].exists() and paths["video_path"].exists()
            else JobStatus.WAITING_LLM_QUOTA
        )
        return _handle_pipeline_exception(exc, code=getattr(exc, "code", "QuotaError"), status=target, ctx=ctx)
    except ManualInterventionRequired as exc:
        return _handle_pipeline_exception(
            exc, code=getattr(exc, "code", "ManualInterventionRequired"), status=JobStatus.RETRYABLE_FAILED, ctx=ctx
        )
    except (AuthenticationError, ProviderTimeoutError, OSError, ValueError) as exc:
        code = getattr(exc, "code", type(exc).__name__)
        logger.warning("Pipeline execution failed with retryable error (%s): %s", code, exc, exc_info=True)
        return _handle_pipeline_exception(
            exc, code=getattr(exc, "code", "pipeline_validation"), status=JobStatus.RETRYABLE_FAILED, retry_delay=900, ctx=ctx
        )
    except Exception as exc:
        logger.exception("Unexpected pipeline failure for story %s: %s", story_id, exc)
        return _handle_pipeline_exception(
            exc, code="unexpected", status=JobStatus.RETRYABLE_FAILED, retry_delay=1800, ctx=ctx
        )
