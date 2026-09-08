"""
Pipeline orchestration service for YouTube Automation.
Centralizes single-channel runs, multi-channel batch execution, on-demand topic ingestion,
Telegram canary runs, and daemon lifecycle management.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.branding import resolve_channel_key
from src.channel_manager import get_active_channels
from src.config import DEFAULT_DB_PATH, SETTINGS, validate_runtime_config
from src.core.domain import JobStatus
from src.core.lock import ChannelLock, ChannelLockError
from src.core.repository import QueueRepository, connect
from src.daemon import run_pipeline_once, start_daemon_lanes
from src.sanitizer import sanitize_filename
from src.telegram.notifier import TelegramNotifier
from src.templates.narratives import build_longform_narrative, build_short_narrative

logger = logging.getLogger(__name__)

_DEFAULT_RUN_PIPELINE_ONCE = run_pipeline_once
_DEFAULT_START_DAEMON = start_daemon_lanes


def _get_run_pipeline_func() -> Any:
    mod = sys.modules.get(__name__)
    if mod and hasattr(mod, "run_pipeline_once") and getattr(mod, "run_pipeline_once") is not _DEFAULT_RUN_PIPELINE_ONCE:
        return getattr(mod, "run_pipeline_once")
    main_mod = sys.modules.get("main")
    if main_mod and hasattr(main_mod, "run_pipeline_once") and getattr(main_mod, "run_pipeline_once") is not _DEFAULT_RUN_PIPELINE_ONCE:
        return getattr(main_mod, "run_pipeline_once")
    return _DEFAULT_RUN_PIPELINE_ONCE


def _get_start_daemon_func() -> Any:
    mod = sys.modules.get(__name__)
    if mod and hasattr(mod, "start_daemon_lanes") and getattr(mod, "start_daemon_lanes") is not _DEFAULT_START_DAEMON:
        return getattr(mod, "start_daemon_lanes")
    main_mod = sys.modules.get("main")
    if main_mod and hasattr(main_mod, "start_daemon_lanes") and getattr(main_mod, "start_daemon_lanes") is not _DEFAULT_START_DAEMON:
        return getattr(main_mod, "start_daemon_lanes")
    return _DEFAULT_START_DAEMON


@dataclass
class PipelineRunResult:
    channel: str
    status: str
    story_id: Optional[str] = None
    work_dir: Optional[str] = None
    run_id: Optional[str] = None
    error: Optional[str] = None
    telegram_delivery: Optional[dict[str, Any]] = None
    raw_result: dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchRunResult:
    results: dict[str, PipelineRunResult]
    overall_status: str
    failed_channels: list[str]
    success_count: int
    failure_count: int


@dataclass
class CanaryRunResult:
    channel: str
    status: str
    work_dir: Optional[str] = None
    video_file: Optional[str] = None
    telegram_ok: bool = False
    telegram_detail: Optional[str] = None
    error: Optional[str] = None


class PipelineOrchestrator:
    """
    High-level orchestrator service coordinating channel locking, topic narrative synthesis,
    queue manipulation, pipeline iteration, and notification dispatch.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH

    def _prepare_topic_story(
        self,
        channel: str,
        topic: str,
        lane_id: str | None = None,
    ) -> str:
        """Synthesize topic narrative, insert/reset in repository, and return claimed story ID."""
        from src.core.lanes import resolve_lane_for_run
        from src.templates.narratives import build_narrative

        repo = QueueRepository(self.db_path)
        repo.initialize()

        import re
        import unicodedata

        clean_slug = unicodedata.normalize("NFKD", topic.lower()).encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", clean_slug)[:32]
        story_to_claim = f"auto-{channel}-{slug}"

        lane = resolve_lane_for_run(channel, lane_id)
        is_long = lane.orientation == "horizontal"
        topic_content = build_narrative(
            topic,
            channel=channel,
            length="long" if is_long else "short",
            target_minutes=lane.duration_target_sec / 60.0,
        )

        with connect(self.db_path) as conn:
            existing = conn.execute(
                "SELECT story_id FROM stories WHERE story_id = ?",
                (story_to_claim,),
            ).fetchone()

            if not existing:
                repo.enqueue(
                    story_to_claim,
                    topic,
                    topic_content,
                    f"https://local.automation/{channel}/{story_to_claim}",
                    channel,
                    lane_id=lane.id,
                )
            else:
                conn.execute(
                    "UPDATE stories SET status = ?, content = ?, youtube_video_id = NULL, next_attempt_at = NULL, lane_id = ? WHERE story_id = ?",
                    (JobStatus.PENDING.value, topic_content, lane.id, story_to_claim),
                )
                # Release only THIS story's stale lease so the topic run can
                # reclaim it; never wipe the whole channel's leases.
                conn.execute("DELETE FROM leases WHERE job_id = ?", (story_to_claim,))
                conn.execute("DELETE FROM lane_leases WHERE job_id = ?", (story_to_claim,))
                conn.commit()

        return story_to_claim

    def run_channel(
        self,
        channel: str,
        dry_run: bool = False,
        topic: Optional[str] = None,
        story_id: Optional[str] = None,
        lane_id: str | None = None,
        generate_only: bool = False,
        dispatch_telegram: bool = False,
        skip_lock: bool = False,
    ) -> PipelineRunResult:
        """
        Execute a pipeline run for a single channel under exclusive lock.
        Handles topic synthesis, queue claiming, execution, and optional Telegram dispatch.
        The format is decided by the lane (config/lanes.json), never by a flag.

        When ``skip_lock`` is True the caller must already hold the channel
        lock (e.g. the CLI "all" branch acquires it per-channel); acquiring
        again here would self-collide on a separate file descriptor.
        """
        channel_key = resolve_channel_key(channel)
        story_to_claim = story_id

        try:
            lock_ctx = (
                contextlib.nullcontext()
                if skip_lock
                else ChannelLock(channel_key)
            )
            with lock_ctx:
                if topic:
                    story_to_claim = self._prepare_topic_story(
                        channel=channel_key,
                        topic=topic,
                        lane_id=lane_id,
                    )

                if dry_run:
                    return PipelineRunResult(
                        channel=channel_key,
                        status="DRY_RUN",
                        story_id=story_to_claim,
                        raw_result={"status": "DRY_RUN"},
                    )

                runner = _get_run_pipeline_func()
                res = runner(
                    channel=channel_key,
                    db_path=self.db_path,
                    generate_only=generate_only,
                    story_id=story_to_claim,
                    lane_id=lane_id,
                )

                delivery_dict: Optional[dict[str, Any]] = None
                if dispatch_telegram:
                    work_d = res.get("work_dir", "") or (
                        str(SETTINGS.work_root / str(res["run_id"]))
                        if res.get("run_id")
                        else ""
                    )
                    video_file = os.path.join(work_d, "video.mp4") if work_d else ""
                    if os.path.exists(video_file):
                        notifier = TelegramNotifier()
                        delivery = notifier.send_video_preview(video_file, metadata=res, drive_url=res.get("drive_url"))
                        delivery_dict = {
                            "ok": delivery.ok,
                            "message_id": delivery.message_id,
                            "detail": delivery.detail,
                            "error": delivery.error,
                        }

                return PipelineRunResult(
                    channel=channel_key,
                    status=res.get("status", "UNKNOWN"),
                    story_id=res.get("story_id") or story_to_claim,
                    work_dir=res.get("work_dir"),
                    run_id=res.get("run_id"),
                    error=res.get("error"),
                    telegram_delivery=delivery_dict,
                    raw_result=res,
                )

        except Exception as err:
            logger.exception("Pipeline run failed for channel [%s]: %s", channel_key, err)
            return PipelineRunResult(
                channel=channel_key,
                status="FAILED",
                story_id=story_to_claim,
                error=str(err),
                raw_result={"status": "FAILED", "error": str(err)},
            )

    def run_all_channels(
        self,
        channels: Optional[list[str]] = None,
        dry_run: bool = False,
        generate_only: bool = False,
        dispatch_telegram: bool = False,
    ) -> BatchRunResult:
        """
        Execute pipeline sequentially across designated active channels with per-channel fault isolation.
        """
        target_channels = channels or get_active_channels()
        results: dict[str, PipelineRunResult] = {}
        failed_channels: list[str] = []
        success_count = 0
        failure_count = 0

        for ch in target_channels:
            res = self.run_channel(
                channel=ch,
                dry_run=dry_run,
                generate_only=generate_only,
                dispatch_telegram=dispatch_telegram,
            )
            results[ch] = res

            if res.status in ("SUCCESS", "DRY_RUN", "NO_STORIES", "NO_PENDING"):
                success_count += 1
            else:
                failure_count += 1
                failed_channels.append(ch)

        if failure_count == 0:
            overall_status = "SUCCESS"
        elif success_count > 0:
            overall_status = "PARTIAL_FAILURE"
        else:
            overall_status = "FAILED"

        return BatchRunResult(
            results=results,
            overall_status=overall_status,
            failed_channels=failed_channels,
            success_count=success_count,
            failure_count=failure_count,
        )

    def run_telegram_canary(
        self,
        channel: str = "moku",
        story_id: Optional[str] = None,
    ) -> CanaryRunResult:
        """
        Execute end-to-end pipeline test producing preview video delivered solely to Telegram.
        Guarantees generate_only=True and prevents production publishing.
        """
        ch = resolve_channel_key(channel)
        try:
            with ChannelLock(ch):
                runner = _get_run_pipeline_func()
                res = runner(
                    channel=ch,
                    db_path=self.db_path,
                    generate_only=True,
                    story_id=story_id,
                )

                work_d = res.get("work_dir", "")
                if not work_d and res.get("run_id"):
                    work_d = str(SETTINGS.work_root / str(res["run_id"]))

                video_file = os.path.join(work_d, "video.mp4") if work_d else ""
                if os.path.exists(video_file):
                    notifier = TelegramNotifier()
                    preview_delivery = notifier.send_video_preview(video_file, metadata=res, drive_url=res.get("drive_url"))
                    return CanaryRunResult(
                        channel=ch,
                        status=res.get("status", "SUCCESS"),
                        work_dir=work_d,
                        video_file=video_file,
                        telegram_ok=preview_delivery.ok,
                        telegram_detail=preview_delivery.detail,
                        error=preview_delivery.error,
                    )
                else:
                    return CanaryRunResult(
                        channel=ch,
                        status=res.get("status", "FAILED"),
                        work_dir=work_d,
                        video_file=video_file,
                        telegram_ok=False,
                        error=f"Rendered video file not found at: {video_file}",
                    )

        except Exception as canary_err:
            logger.exception("E2E Telegram Canary failed for channel [%s]: %s", ch, canary_err)
            return CanaryRunResult(
                channel=ch,
                status="FAILED",
                telegram_ok=False,
                error=str(canary_err),
            )

    def run_daemon(
        self,
        interval: int = 60,
        channel: str = "all",
        lanes_filter: Optional[list[str]] = None,
    ) -> None:
        """
        Validate environment and start the continuous multi-lane daemon.

        Cadence is governed per lane by ``config/lanes.json`` ceilings; the
        legacy turn-based ``start_daemon`` loop is no longer scheduled.
        ``channel`` narrows to that channel's lanes; ``lanes_filter`` narrows
        further to explicit lane ids.
        """
        if os.environ.get("TEST_MODE") != "1":
            validate_runtime_config(
                require_drive=True,
                require_publish=True,
                require_review=True,
            )

        with ChannelLock(channel):
            allowed: list[str] | None = list(lanes_filter) if lanes_filter else None
            if channel != "all":
                key = resolve_channel_key(channel)
                from src.core.lanes import lanes_for_channel

                channel_lanes = [lane.id for lane in lanes_for_channel(key)]
                if not channel_lanes:
                    raise ValueError(f"Sin carriles configurados para el canal {key}")
                allowed = (
                    [lane for lane in channel_lanes if allowed is None or lane in allowed]
                    if allowed
                    else channel_lanes
                )
                if not allowed:
                    raise ValueError(
                        f"Ninguno de los carriles {lanes_filter} pertenece al canal {key}"
                    )

            daemon_runner = _get_start_daemon_func()
            daemon_runner(
                interval_seconds=interval,
                db_path=self.db_path,
                lanes_filter=allowed,
            )
