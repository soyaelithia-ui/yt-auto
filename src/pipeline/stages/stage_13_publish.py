"""Stage 13: Drive backup, code verdict, Telegram human review gate, YouTube publish, and commit."""

from __future__ import annotations

import os
import time
from typing import Any

from src.config import SETTINGS
from src.core.domain import (
    AmbiguousUploadError,
    JobStatus,
    LeaseOwnershipError,
    YouTubeQuotaExceededError,
    YouTubeUploadLimitError,
)
from src.core.providers import DriveProof
from src.core.profiling import CanonicalStage
from src.core.quality import normalize_text
from src.log import get_logger
from src.pipeline.context import PipelineContext
from src.pipeline.utils import (
    _drive_review_url,
    _marker,
    _peak_rss_metric,
    is_pipeline_test_environment as is_test_environment,
)
from src.sanitizer import sanitize_filename

logger = get_logger("pipeline.stages.stage_13_publish")


def _handle_drive_backup(
    ctx: PipelineContext,
) -> tuple[str | None, DriveProof | None, dict[str, Any] | None]:
    """Upload video to Google Drive for backup and reviewer access."""
    drive_url: str | None = None
    drive_proof: DriveProof | None = None
    folder_id = getattr(SETTINGS, "drive_approved_video_folder_id", "") or SETTINGS.drive_folder_id
    if not folder_id:
        logger.info("Drive backup omitido: DRIVE_FOLDER_ID no está configurado")
        return None, None, None

    from src.drive import upload_to_drive_verified

    try:
        drive_proof = upload_to_drive_verified(
            str(ctx.video_path),
            folder_id=folder_id,
            sa_key_path=str(SETTINGS.drive_key_path),
            display_name=f"{sanitize_filename(ctx.spanish_title)}.mp4",
            token_path=str(ctx.settings.youtube_token_path),
            idempotency_key=f"YTShort:{ctx.channel_name}:{ctx.story_id}",
            on_file_id=lambda fid: ctx.repository.record_drive_upload_id(ctx.story_id, ctx.run_id, fid, owner=ctx.owner),
        )
        ctx.repository.record_provider_attempt(ctx.run_id, "drive", "upload_and_verify", outcome="verified")
        ctx.repository.record_artifact(
            ctx.run_id,
            "drive_video",
            remote_provider="drive",
            remote_id=drive_proof.file_id,
            remote_name=drive_proof.name,
            size_bytes=drive_proof.size_bytes,
            verified=True,
        )
        if drive_proof and drive_proof.file_id:
            drive_url = _drive_review_url(drive_proof)
        if not ctx.set_owned_status(JobStatus.DRIVE_BACKED_UP):
            raise LeaseOwnershipError("Ownership perdido después de confirmar Drive")
    except Exception as exc:
        ctx.repository.record_provider_attempt(
            ctx.run_id,
            "drive",
            "upload_and_verify",
            outcome="failed",
            error_code=getattr(exc, "code", "drive_error"),
            error_detail=str(exc),
        )
        if ctx.directed and isinstance(exc, AmbiguousUploadError):
            return None, None, ctx.fail("drive_upload_ambiguous", str(exc), status=JobStatus.UPLOAD_UNCONFIRMED)
        logger.warning("Drive backup attempt failed: %s", exc)

    return drive_url, drive_proof, None


def _evaluate_technical_verdict(ctx: PipelineContext) -> dict[str, Any]:
    """Run automated code-based QA verdict if enabled."""
    verdict_payload: dict[str, Any] = {}
    try:
        from src.core.verdict import evaluate_video, is_code_review_enabled

        if is_code_review_enabled():
            verdict = evaluate_video(
                str(ctx.video_path),
                work_dir=str(ctx.work_dir),
                script_text=ctx.script,
                ass_path=str(ctx.ass_path) if ctx.ass_path.is_file() else None,
                subtitle_path=str(ctx.srt_path) if ctx.srt_path.is_file() else None,
                thumbnail_path=str(ctx.thumbnail_path) if ctx.thumbnail_path.is_file() else None,
                story_id=ctx.story_id,
                run_id=ctx.run_id,
                channel=ctx.channel_name,
                video_mode="long" if ctx.is_long_lane else "short",
                precomputed_visual=ctx.visual_integrity_report,
            )
            verdict_passed = getattr(verdict, "passed", getattr(verdict, "approved", False))
            from dataclasses import asdict, is_dataclass

            verdict_payload = asdict(verdict) if is_dataclass(verdict) else (verdict if isinstance(verdict, dict) else {})
            if not verdict_passed:
                logger.warning(
                    "Short %s advertencia en veredicto técnico: %s", ctx.story_id, getattr(verdict, "reasons", [])
                )
            else:
                logger.info("Short %s evaluado exitosamente por veredicto técnico", ctx.story_id)
    except Exception as exc:
        logger.warning("Code-based review evaluation failed (%s); continuing to Telegram review", exc, exc_info=True)
    return verdict_payload


def _handle_review_gate(
    ctx: PipelineContext,
    drive_url: str | None,
    drive_proof: DriveProof | None,
    verdict_payload: dict[str, Any],
) -> tuple[Any, str, dict[str, Any] | None]:
    from review import ReviewJobManager, ReviewStatus

    review_manager = ReviewJobManager()
    # Deliver video and metadata to Telegram for review and visibility
    review_job = review_manager.submit_video_for_review(
        job_id=ctx.story_id,
        project="YTShort",
        channel=ctx.channel_name,
        content_type=ctx.lane.review_content_type,
        original_video_path=str(ctx.video_path),
        thumbnail_path=str(ctx.thumbnail_path) if ctx.thumbnail_path.is_file() else None,
        title=ctx.youtube_title,
        description=ctx.youtube_description,
        script=ctx.script,
        subtitle_path=str(ctx.ass_path) if ctx.ass_path.is_file() else (str(ctx.srt_path) if ctx.srt_path.is_file() else None),
        work_dir=str(ctx.work_dir),
        drive_url=drive_url,
        metadata={"code_verdict": verdict_payload} if verdict_payload else None,
    )
    ctx.review_job_version = getattr(review_job, "version", 1)

    auto_approve = (
        is_test_environment()
        or os.environ.get("TEST_MODE") == "1"
        or os.environ.get("AUTO_APPROVE", "1").strip() not in ("0", "false", "no")
    )
    if auto_approve:
        uid = int(os.environ.get("REVIEW_APPROVER_USER_ID") or os.environ.get("TELEGRAM_ALLOWED_USER_ID") or "0")
        approved_job = review_manager.code_approve(
            ctx.story_id,
            review_job.version,
            verdict_payload or {"approved": True, "passed": True, "source": "auto_approve"},
            user_id=uid,
        )
        review_job = approved_job
        review_job.status = ReviewStatus.APPROVED.value
        logger.info(
            "Review job %s v%s delivered to Telegram and approved for publication",
            ctx.story_id,
            review_job.version,
        )
    try:
        from src.core.contracts import ReviewContract
        ctx.review_contract = ReviewContract.from_job(review_job)
    except Exception as exc:
        logger.debug("ReviewContract binding skipped: %s", exc)
    if review_job.status == ReviewStatus.FAILED.value:
        return None, "", ctx.fail("review_delivery_failed", review_job.delivery_error or "Telegram did not confirm review delivery")
    return review_job, review_job.status, None


def _handle_youtube_upload(
    ctx: PipelineContext,
    review_job: Any,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Execute YouTube upload and catch quota/limit conditions."""
    from src.core.guard import memory_checkpoint

    memory_checkpoint("publish_start")
    from src.youtube.uploader import upload_video

    try:
        result = upload_video(
            str(ctx.video_path),
            ctx.youtube_title,
            ctx.youtube_description,
            tags=ctx.branding.tags,
            channel=ctx.channel_name,
            thumbnail_path=str(ctx.thumbnail_path),
            token_path=str(ctx.settings.youtube_token_path),
            api_only=False,
            expected_channel_id=ctx.settings.expected_youtube_channel_id,
            on_video_id=lambda vid: ctx.repository.record_youtube_upload_id(ctx.story_id, ctx.run_id, vid, owner=ctx.owner),
            job_id=ctx.story_id,
            version=review_job.version,
        )
        ctx.repository.record_provider_attempt(
            ctx.run_id, "youtube", "upload_and_verify", outcome=str(result.get("status") or "unknown").lower()
        )
        return result, None
    except (YouTubeUploadLimitError, YouTubeQuotaExceededError) as exc:
        retry_delay = 14400 if isinstance(exc, YouTubeUploadLimitError) else 3600
        retry_at = int(time.time()) + retry_delay
        ctx.repository.record_provider_attempt(
            ctx.run_id,
            "youtube",
            "upload_and_verify",
            outcome="limit_exceeded" if isinstance(exc, YouTubeUploadLimitError) else "quota_exceeded",
            error_code=exc.code,
            error_detail=str(exc),
        )
        if not ctx.set_owned_status(
            JobStatus.WAITING_YOUTUBE_LIMIT,
            error_code=exc.code,
            error_detail=str(exc),
            retry_at=retry_at,
        ):
            return None, ctx.lease_lost_result()
        _marker(ctx.work_dir, ctx.run_id, active=False)
        return None, {
            "status": JobStatus.WAITING_YOUTUBE_LIMIT.value,
            "story_id": ctx.story_id,
            "run_id": ctx.run_id,
            "channel": ctx.channel_name,
            "work_dir": str(ctx.work_dir),
            "retry_at": retry_at,
            "profiling": ctx.profiler.to_dict(),
        }
    except Exception as exc:
        ctx.repository.record_provider_attempt(
            ctx.run_id,
            "youtube",
            "upload_and_verify",
            outcome="failed",
            error_code=getattr(exc, "code", "youtube_error"),
            error_detail=str(exc),
        )
        if ctx.directed:
            if not ctx.set_owned_status(
                JobStatus.UPLOAD_UNCONFIRMED,
                error_code=getattr(exc, "code", "youtube_unconfirmed"),
                error_detail=str(exc),
            ):
                return None, ctx.lease_lost_result()
            _marker(ctx.work_dir, ctx.run_id, active=False)
            return None, {
                "status": JobStatus.UPLOAD_UNCONFIRMED.value,
                "story_id": ctx.story_id,
                "run_id": ctx.run_id,
                "channel": ctx.channel_name,
                "work_dir": str(ctx.work_dir),
                "profiling": ctx.profiler.to_dict(),
            }
        raise


def _finalize_published_run(
    ctx: PipelineContext,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Record publication proofs, fingerprints, retention markers, and post-publish cleanup."""
    from review import ReviewStatus
    from src.cleaner import delete_local_post_publication
    from src.core.providers import publication_proof_from_response
    from src.retention import mark_run_retention_satisfied

    if ctx.directed:
        ctx.repository.require_single_story_run(ctx.run_id, ctx.story_id)
    proof = publication_proof_from_response(
        result,
        expected_channel=ctx.channel_key,
        expected_title=ctx.youtube_title,
        expected_description=ctx.youtube_description,
    )
    ctx.repository.mark_published(ctx.story_id, ctx.run_id, proof, provider=str(result["method"]), owner=ctx.owner)

    # Autonomous pinned comment dispatch and failure marking
    comment_status = "none"
    comment_error = None
    pinned_comment_text = getattr(ctx, "pinned_comment", None)
    if not pinned_comment_text and getattr(ctx, "metadata_path", None) and ctx.metadata_path.is_file():
        try:
            import json
            m_data = json.loads(ctx.metadata_path.read_text(encoding="utf-8"))
            pinned_comment_text = m_data.get("pinned_comment")
        except Exception:
            pass

    if pinned_comment_text and proof.video_id:
        try:
            from src.youtube.comments import post_pinned_comment
            c_res = post_pinned_comment(
                video_id=proof.video_id,
                comment_text=pinned_comment_text,
                token_path=str(ctx.settings.youtube_token_path),
                channel=ctx.channel_name,
            )
            comment_status = c_res.status
            comment_error = c_res.error
        except Exception as c_exc:
            comment_status = "failed"
            comment_error = str(c_exc)
            logger.warning("Pinned comment dispatch failed for %s: %s", proof.video_id, c_exc)

    try:
        from src.core.inventory import record_published_inventory
        record_published_inventory(
            db_path=ctx.database,
            run_id=ctx.run_id,
            story_id=ctx.story_id,
            video_id=proof.video_id,
            url=proof.url,
            channel=ctx.channel_name,
            title=proof.title,
            description=proof.description,
            provider=str(result["method"]),
            visibility=proof.visibility,
            video_sha256=getattr(ctx, "video_sha256", None) or ctx.file_fingerprints.get("video"),
            drive_video_id=getattr(ctx, "drive_video_id", None) or (ctx.drive_proof.file_id if getattr(ctx, "drive_proof", None) else None),
            full_script=getattr(ctx, "clean_script", None) or getattr(ctx, "script", None),
            used_resources={
                "loop": str(getattr(ctx, "resolved_loop_path", "")),
                "music": str(getattr(ctx, "music_track_path", "")),
                "voice": getattr(ctx.lane, "voice", ""),
            },
            comment_status=comment_status,
            comment_error=comment_error,
            pinned_comment=pinned_comment_text,
        )
    except Exception as inv_exc:
        logger.warning("Failed to record publication in inventory: %s", inv_exc)
    if getattr(ctx, "review_contract", None) is not None:
        try:
            ctx.review_contract.status = ReviewStatus.PUBLISHED.value
            ctx.review_contract.published_id = proof.video_id
            ctx.review_contract.published_url = proof.url
        except Exception:
            pass
    try:
        from review import ReviewJobManager
        rm = ReviewJobManager()
        r_ver = getattr(ctx, "review_job_version", 1)
        if hasattr(rm, "store") and hasattr(rm.store, "confirm_publication"):
            try:
                rm.store.confirm_publication(
                    ctx.story_id,
                    r_ver,
                    published_id=proof.video_id,
                    published_url=proof.url,
                )
            except Exception as st_exc:
                logger.debug("Review store publication confirmation notice: %s", st_exc)
        if hasattr(rm, "_notify_published"):
            rm._notify_published(ctx.story_id, r_ver, proof.url)
        if hasattr(rm, "bot") and getattr(rm.bot, "chat_id", None) and getattr(rm.bot, "token", None):
            rm.bot.send_message(
                chat_id=rm.bot.chat_id,
                text=(
                    f"🚀 *Video publicado en YouTube*\n\n"
                    f"🎬 *{proof.title}*\n"
                    f"🔗 {proof.url}\n"
                    f"📺 Canal: `{ctx.channel_name}`\n"
                    f"🆔 Run: `{ctx.run_id[:8]}`"
                ),
                parse_mode="Markdown",
            )
    except Exception as notify_exc:
        logger.warning("Telegram publication notification failed: %s", notify_exc)
    post_commit_errors: list[str] = []
    for kind, payload in ctx.text_fingerprints.items():
        try:
            ctx.repository.record_fingerprint(
                ctx.run_id,
                ctx.story_id,
                ctx.channel_name,
                kind,
                payload,
                normalized_text=normalize_text(str(payload)) if isinstance(payload, str) else None,
            )
        except Exception as exc:
            logger.warning("Post-commit artifact recording failed: %s", exc, exc_info=True)
            post_commit_errors.append(f"fingerprint {kind}: {exc}")
    for kind, digest in ctx.file_fingerprints.items():
        try:
            ctx.repository.record_fingerprint_digest(ctx.run_id, ctx.story_id, ctx.channel_name, kind, digest)
        except Exception as exc:
            logger.warning("Post-commit fingerprint recording failed: %s", exc, exc_info=True)
            post_commit_errors.append(f"fingerprint {kind}: {exc}")
    marker_deactivated = False
    try:
        _marker(ctx.work_dir, ctx.run_id, active=False)
        marker_deactivated = True
    except Exception as exc:
        logger.warning("Post-commit marker deactivation failed: %s", exc, exc_info=True)
        post_commit_errors.append(f"marker: {exc}")
    retention_satisfied = False
    if marker_deactivated:
        try:
            retention_satisfied = mark_run_retention_satisfied(
                str(ctx.video_path), published_id=proof.video_id, published_url=proof.url
            )
            if not retention_satisfied:
                post_commit_errors.append("retention: no se encontró un marcador de run válido")
        except Exception as exc:
            logger.warning("Post-commit retention satisfaction failed: %s", exc, exc_info=True)
            post_commit_errors.append(f"retention: {exc}")
    if post_commit_errors:
        logger.error("Publication committed; post-commit tasks failed: %s", "; ".join(post_commit_errors))
    try:
        delete_local_post_publication(ctx.work_dir, ctx.video_path)
    except Exception as clean_exc:
        logger.warning("Post-commit local cleanup failed: %s", clean_exc)
    ctx.profiler.emit_telemetry(db_path=ctx.database)
    logger.info("\n" + ctx.profiler.format_table())
    return {
        "status": JobStatus.PUBLISHED.value,
        "story_id": ctx.story_id,
        "run_id": ctx.run_id,
        "channel": ctx.channel_name,
        "url": proof.url,
        "work_dir": str(ctx.work_dir),
        "retention_satisfied": retention_satisfied,
        "profiling": ctx.profiler.to_dict(),
        **({"post_commit_warning": post_commit_errors} if post_commit_errors else {}),
    }


def _handle_upload_outcome(ctx: PipelineContext, result: dict[str, Any]) -> dict[str, Any] | None:
    """Handle special upload states: rate limits, unconfirmed uploads, or non-published statuses."""
    status_val = str(result.get("status") or "")
    if status_val in ("WAITING_YOUTUBE_LIMIT", JobStatus.WAITING_YOUTUBE_LIMIT.value):
        retry_delay = int(result.get("retry_after_seconds") or 14400)
        retry_at = int(time.time()) + retry_delay
        if not ctx.set_owned_status(
            JobStatus.WAITING_YOUTUBE_LIMIT,
            error_code="youtube_upload_limit",
            error_detail=str(result.get("reason") or "Límite diario de YouTube alcanzado"),
            retry_at=retry_at,
        ):
            return ctx.lease_lost_result()
        _marker(ctx.work_dir, ctx.run_id, active=False)
        return {
            "status": JobStatus.WAITING_YOUTUBE_LIMIT.value,
            "story_id": ctx.story_id,
            "run_id": ctx.run_id,
            "channel": ctx.channel_name,
            "work_dir": str(ctx.work_dir),
            "retry_at": retry_at,
            "profiling": ctx.profiler.to_dict(),
        }

    if status_val == "UPLOAD_UNCONFIRMED":
        retry_at = int(time.time()) + 14400
        if not ctx.set_owned_status(
            JobStatus.UPLOAD_UNCONFIRMED,
            error_code="youtube_unconfirmed",
            error_detail=str(result.get("reason") or "respuesta ambigua"),
            retry_at=retry_at,
        ):
            return ctx.lease_lost_result()
        _marker(ctx.work_dir, ctx.run_id, active=False)
        return {
            "status": JobStatus.UPLOAD_UNCONFIRMED.value,
            "story_id": ctx.story_id,
            "run_id": ctx.run_id,
            "channel": ctx.channel_name,
            "work_dir": str(ctx.work_dir),
            "profiling": ctx.profiler.to_dict(),
        }

    if status_val != "PUBLISHED":
        if not ctx.set_owned_status(JobStatus.DRIVE_BACKED_UP):
            return ctx.lease_lost_result()
        if not ctx.repository.finish_run(ctx.run_id, JobStatus.DRIVE_BACKED_UP, owner=ctx.owner):
            return ctx.lease_lost_result()
        _marker(ctx.work_dir, ctx.run_id, active=False)
        ctx.profiler.emit_telemetry(db_path=ctx.database)
        return {
            "status": str(result.get("status") or "TEST_MOCK"),
            "story_id": ctx.story_id,
            "run_id": ctx.run_id,
            "channel": ctx.channel_name,
            "work_dir": str(ctx.work_dir),
            "profiling": ctx.profiler.to_dict(),
        }

    return None


def stage_13_backup_publish(ctx: PipelineContext) -> dict[str, Any]:
    """Stage 13: Drive backup, code verdict, Telegram human review gate, YouTube publish, and commit."""
    from review import ReviewStatus

    with ctx.profiler.phase(CanonicalStage.BACKUP_PUBLISH):
        drive_url, drive_proof, early_exit = _handle_drive_backup(ctx)
        if early_exit is not None:
            return early_exit

        if ctx.generate_only:
            if not ctx.repository.finish_run(ctx.run_id, JobStatus.RENDERED, owner=ctx.owner):
                raise LeaseOwnershipError("Ownership perdido antes de finalizar el run")
            _marker(ctx.work_dir, ctx.run_id, active=False)
            logger.info("Run %s generado sin publicar (generate_only)", ctx.run_id)
            ctx.profiler.emit_telemetry(db_path=ctx.database)
            logger.info("\n" + ctx.profiler.format_table())
            return {
                "status": JobStatus.RENDERED.value,
                "story_id": ctx.story_id,
                "run_id": ctx.run_id,
                "channel": ctx.channel_name,
                "work_dir": str(ctx.work_dir),
                "drive_url": drive_url,
                "drive_file_id": drive_proof.file_id if drive_proof else None,
                "profiling": ctx.profiler.to_dict(),
                **_peak_rss_metric(),
            }

        ctx.require_heartbeat()
        verdict_payload = _evaluate_technical_verdict(ctx)

        try:
            review_job, current_review_status, early_exit = _handle_review_gate(
                ctx, drive_url, drive_proof, verdict_payload
            )
            if early_exit is not None:
                return early_exit
            approved_status_val = ReviewStatus.APPROVED.value
        except (ImportError, ModuleNotFoundError) as exc:
            return ctx.fail("review_core_unavailable", str(exc))
        except Exception as exc:
            logger.exception("Telegram review submission failed for story %s", ctx.story_id)
            return ctx.fail("review_delivery_failed", str(exc))

        if current_review_status != approved_status_val:
            term_status = (
                JobStatus.PENDING_REVIEW
                if current_review_status == ReviewStatus.PENDING_REVIEW.value
                else JobStatus.RENDERED
            )
            ctx.set_owned_status(term_status)
            if not ctx.repository.finish_run(ctx.run_id, JobStatus.RENDERED, owner=ctx.owner):
                raise LeaseOwnershipError("Ownership perdido antes de finalizar el run")
            _marker(ctx.work_dir, ctx.run_id, active=False)
            logger.info(
                "Short %s retenido para revisión humana por Telegram. Estado: %s",
                ctx.story_id,
                current_review_status,
            )
            ctx.profiler.emit_telemetry(db_path=ctx.database)
            logger.info("\n" + ctx.profiler.format_table())
            return {
                "status": current_review_status,
                "story_id": ctx.story_id,
                "run_id": ctx.run_id,
                "channel": ctx.channel_name,
                "work_dir": str(ctx.work_dir),
                "review_status": review_job.status,
                "drive_url": drive_url,
                "drive_file_id": drive_proof.file_id if drive_proof else None,
                "profiling": ctx.profiler.to_dict(),
            }

        result, early_exit = _handle_youtube_upload(ctx, review_job)
        if early_exit is not None:
            return early_exit

        outcome_result = _handle_upload_outcome(ctx, result)
        if outcome_result is not None:
            return outcome_result

        return _finalize_published_run(ctx, result)
