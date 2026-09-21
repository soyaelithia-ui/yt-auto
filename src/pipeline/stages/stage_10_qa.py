"""Stage 10: Automated QA gating (validate_prepublication) and RENDERED status transition."""

from __future__ import annotations

import sys

from src.core.domain import JobStatus, LeaseOwnershipError
from src.core.profiling import CanonicalStage
from src.core.quality import validate_prepublication as default_validate_prepub
from src.log import get_logger
from src.pipeline.context import PipelineContext, active_heartbeat_scope

logger = get_logger("pipeline.stages.stage_10_qa")


def stage_10_qa_gating(ctx: PipelineContext) -> None:
    """Stage 10: Automated QA gating (validate_prepublication) and RENDERED status transition."""
    with ctx.profiler.phase(CanonicalStage.QA_GATING):
        with active_heartbeat_scope(ctx):
            sub_path = (
                ctx.srt_path
                if (ctx.subtitles_active and ctx.srt_path.is_file())
                else (
                    ctx.srt_path
                    if ctx.srt_path.is_file()
                    else (ctx.ass_path if ctx.ass_path.is_file() else None)
                )
            )

            pipe_mod = sys.modules.get("src.pipeline")
            validator = getattr(pipe_mod, "validate_prepublication", default_validate_prepub)

            report = validator(
                channel=ctx.channel_name,
                script=ctx.script,
                title=ctx.youtube_title,
                description=ctx.youtube_description,
                video_path=ctx.video_path,
                subtitle_path=sub_path,
                thumbnail_path=ctx.thumbnail_path,
                recent_texts=ctx.repository.recent_published_texts(ctx.channel_name),
                visual_plan_path=ctx.visual_plan_path,
                expected_story_count=1 if ctx.directed else len(ctx.used_ids),
                visibility="public",
                audio_proof=ctx.audio,
                require_strict_voice=ctx.directed,
                video_mode="longform" if ctx.is_long_lane else "short",
                precomputed_visual=ctx.visual_integrity_report,
                video_engine=ctx.engine_mode,
                require_subtitles=ctx.subtitles_active,
                min_duration_sec=float(ctx.lane.duration_min_sec),
            )
            report.require_pass()

            # Multimodal Vision QA Quality Gate (Blocking)
            from src.agents.video_qa import enforce_multimodal_qa_gate
            enforce_multimodal_qa_gate(
                ctx.run_id,
                db_path=ctx.database,
                video_path=str(ctx.video_path),
            )

            if not ctx.set_owned_status(JobStatus.RENDERED):
                raise LeaseOwnershipError("Ownership perdido antes de marcar RENDERED")

            try:
                from src.cleaner import clean_run_intermediates

                clean_run_intermediates(ctx.work_dir)
            except Exception as cleaner_exc:
                logger.debug("Non-fatal intermediate cleanup error: %s", cleaner_exc)
