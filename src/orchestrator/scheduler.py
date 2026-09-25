"""Autonomous Multi-Lane Daemon Orchestrator Lifecycle Engine.

Decouples multi-lane scheduling, worker thread pool execution, background
sweeps, zombie child process reaping, and responsive shutdown handling
adhering strictly to AGENTS.md Section 5 resource constraints.
"""

from __future__ import annotations

import concurrent.futures
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import os
import socket
import threading
import time
from typing import Any, Final, Optional

from src.config import DEFAULT_DB_PATH, is_test_environment
from src.core.contracts.daemon import (
    ConcurrencyPolicy,
    LaneDaemonConfig,
    TurnResult,
)
from src.core.domain import QuotaError
from src.core.guard import ConsecutiveFailureBreaker, ensure_disk_available
from src.core.repository import (
    QueueRepository,
    connect,
    touch_daemon_liveness,
)
from src.core.scheduler import LanePick, LaneScheduler
from src.log import get_logger

logger = get_logger("orchestrator.scheduler")


class LaneDaemonOrchestrator:
    """Manages continuous multi-lane execution across independent cadences."""

    def __init__(self, config: LaneDaemonConfig) -> None:
        self.config: Final[LaneDaemonConfig] = config
        self._shutdown_event = threading.Event()
        self._shutdown_requested = False
        self.breaker = ConsecutiveFailureBreaker()

        self.lane_scheduler = LaneScheduler(self.config.db_path)
        self.active_lanes = {
            lane.id: lane
            for lane in self.lane_scheduler.lanes
            if self.config.lanes_filter is None or lane.id in self.config.lanes_filter
        }
        channel_set = {lane.channel for lane in self.active_lanes.values()}
        self.target_channel: Optional[str] = (
            list(channel_set)[0].value if len(channel_set) == 1 else None
        )

        parallel = max(
            1,
            int(self.config.max_parallel or os.environ.get("YT_MAX_PARALLEL_LANES", "3")),
        )
        if self.config.max_picks is not None and (self.config.max_parallel is None or self.config.max_parallel < self.config.max_picks):
            parallel = max(parallel, self.config.max_picks)
        self.max_parallel = parallel
        self.capacity = (
            min(self.max_parallel, self.config.max_picks)
            if self.config.max_picks is not None
            else self.max_parallel
        )

        self.scheduler_commit_fire = self.commit_fire
        self.scheduler_commit_empty = self.commit_empty
        self._last_auto_publish_sweep = 0.0
        self._last_24h_sweep = 0.0
        self._ticks = 0

    def commit_fire(self, pick: LanePick, *, run_id: Optional[str] = None) -> None:
        """Advance the cadence ceiling following a productive turn."""
        self.lane_scheduler.commit_fire(pick, run_id=run_id)

    def commit_empty(self, pick: LanePick) -> None:
        """Apply an adaptive linear backoff without advancing cadence ceiling."""
        self.lane_scheduler.commit_empty(pick)

    def request_shutdown(self) -> None:
        """Signal orchestrator to cease dispatching and gracefully drain jobs."""
        self._shutdown_requested = True
        self._shutdown_event.set()
        try:
            import src.daemon as daemon_mod

            if not daemon_mod.is_shutdown_requested():
                daemon_mod.request_shutdown()
        except (ImportError, AttributeError):
            pass

    def reset_shutdown(self) -> None:
        """Reset internal shutdown flags to allow new execution cycles."""
        self._shutdown_requested = False
        self._shutdown_event.clear()

    def is_shutdown_requested(self) -> bool:
        """Check whether termination was requested by signal or caller."""
        try:
            import src.daemon as daemon_mod

            if daemon_mod._SHUTDOWN_REQUESTED or daemon_mod._SHUTDOWN_EVENT.is_set():
                return True
        except (ImportError, AttributeError):
            pass
        return self._shutdown_event.is_set() or self._shutdown_requested

    def initialize(self) -> None:
        """Execute preflight checks, database migrations, and stale lease recovery."""
        if not self.is_shutdown_requested():
            self.reset_shutdown()
        ensure_disk_available(self.config.db_path)
        self.lane_scheduler.initialize(apply_offsets=self.config.apply_offsets)

        try:
            from src.core.lease_reaper import LeaseReaper

            LeaseReaper(db_path=self.config.db_path).reap_once(
                startup=True, channel=self.target_channel
            )
        except Exception:
            logger.warning("Startup lease reap failed", exc_info=True)

        try:
            from src.cleaner import (
                clean_expired_failed_runs,
                clean_untracked_temp_files,
            )

            clean_expired_failed_runs()
            clean_untracked_temp_files()
        except Exception:
            logger.debug("Startup debris cleanup skipped", exc_info=True)

    def _reap_zombies_safe(self) -> int:
        """Safely reap terminated child processes without blocking."""
        reaped = 0
        try:
            while True:
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if pid <= 0:
                    break
                reaped += 1
        except (ChildProcessError, OSError):
            pass
        return reaped

    def _turn_timeout_seconds(self) -> float:
        """Retrieve bounded timeout duration for an individual lane turn."""
        try:
            import src.daemon as daemon_mod

            if hasattr(daemon_mod, "_turn_timeout_seconds"):
                return daemon_mod._turn_timeout_seconds()
        except (ImportError, AttributeError):
            pass
        raw = os.environ.get("DAEMON_TURN_TIMEOUT_SECONDS")
        if raw:
            try:
                return max(0.05, float(raw))
            except ValueError:
                pass
        try:
            return float(os.environ.get("RENDER_TIMEOUT_SECONDS", "10800"))
        except ValueError:
            return 10800.0

    def _watchdog_tick_seconds(self) -> float:
        """Retrieve slice duration for responsive future waits."""
        try:
            import src.daemon as daemon_mod

            if hasattr(daemon_mod, "_watchdog_tick_seconds"):
                return daemon_mod._watchdog_tick_seconds()
        except (ImportError, AttributeError):
            pass
        try:
            return max(0.05, float(os.environ.get("DAEMON_WATCHDOG_TICK_SECONDS", "5")))
        except ValueError:
            return 5.0

    def _execute_lane_pick(
        self,
        database: str,
        pick: LanePick,
        breaker: ConsecutiveFailureBreaker,
        generate_only: bool = False,
    ) -> TurnResult:
        """Execute one lane iteration: claim story, run pipeline, handle errors."""
        repository = QueueRepository(database)
        owner = f"lane-{pick.lane_id}:{socket.gethostname()}:{os.getpid()}:{threading.get_ident()}"
        lease_seconds = max(900, int(os.environ.get("RENDER_TIMEOUT_SECONDS", "10800")) // 2)
        ch_val = pick.channel.value if hasattr(pick.channel, "value") else str(pick.channel)
        job: Optional[dict[str, Any]] = None
        result: Optional[TurnResult] = None

        try:
            job = repository.claim_resumable(
                pick.lane_id, ch_val, owner, lease_seconds=lease_seconds
            )
            if job is None:
                job = repository.claim_for_lane(
                    pick.lane_id, ch_val, owner, lease_seconds=lease_seconds
                )
            if job is None and not is_test_environment():
                try:
                    from src.core.lanes import resolve_lane_for_run
                    from src.scraper import ensure_queue_depth

                    lane_def = resolve_lane_for_run(pick.channel, pick.lane_id)
                    ensure_queue_depth(lane_def, db_path=database)
                    job = repository.claim_for_lane(
                        pick.lane_id, ch_val, owner, lease_seconds=lease_seconds
                    )
                except Exception as repl_exc:
                    logger.warning("Replenish failed for %s: %s", pick.lane_id, repl_exc)

            if job is None:
                return {"status": "LANE_EMPTY", "lane": pick.lane_id, "channel": ch_val}

            from src.pipeline import run_pipeline_once as safe_run

            res_raw = safe_run(
                channel=ch_val,
                db_path=database,
                generate_only=generate_only,
                story_id=job["story_id"],
                lane_id=pick.lane_id,
                run_id=job.get("run_id"),
                owner=owner,
                story=job,
            )
            result = dict(res_raw) if isinstance(res_raw, dict) else {"status": "COMPLETED"}
            result.setdefault("lane", pick.lane_id)
            result.setdefault("channel", ch_val)
            result.setdefault("run_id", job.get("run_id"))
        except QuotaError as exc:
            result = {
                "status": "WAITING_LLM_QUOTA",
                "lane": pick.lane_id,
                "channel": ch_val,
                "error": str(exc),
            }
        except Exception as exc:
            result = {
                "status": "RETRYABLE_FAILED",
                "lane": pick.lane_id,
                "channel": ch_val,
                "error": str(exc),
                "error_code": "lane_turn_exception",
            }
        finally:
            if result and result.get("work_dir"):
                try:
                    from src.cleaner import clean_run_intermediates

                    clean_run_intermediates(result["work_dir"])
                except Exception:
                    pass
        return result or {"status": "LANE_EMPTY", "lane": pick.lane_id, "channel": ch_val}

    def _drain_completed_futures(
        self, active_jobs: dict[Any, tuple[LanePick, float]]
    ) -> list[TurnResult]:
        """Collect finished futures, update cadence/breaker, and clean leases."""
        done_futs = [f for f in active_jobs if f.done()]
        results: list[TurnResult] = []
        for fut in done_futs:
            pick, _ = active_jobs.pop(fut)
            ch_val = pick.channel.value if hasattr(pick.channel, "value") else str(pick.channel)
            try:
                res = fut.result()
                if not isinstance(res, dict):
                    res = {"status": "COMPLETED", "lane": pick.lane_id, "channel": ch_val}
            except Exception as exc:
                logger.error("Lane %s execution failed: %s", pick.lane_id, exc)
                res = {
                    "status": "RETRYABLE_FAILED",
                    "lane": pick.lane_id,
                    "channel": ch_val,
                    "error": str(exc),
                    "error_code": "lane_turn_exception",
                }

            status_val = str(res.get("status", ""))
            productive = status_val in {
                "PUBLISHED",
                "COMPLETED",
                "RENDERED",
                "PENDING_REVIEW",
                "UPLOAD_UNCONFIRMED",
                "WAITING_YOUTUBE_LIMIT",
            }
            if productive:
                self.commit_fire(pick, run_id=res.get("run_id"))
                self.breaker.record_success(ch_val)
                self.breaker.record_success(pick.lane_id)
            else:
                self.commit_empty(pick)
                if status_val in {
                    "RETRYABLE_FAILED",
                    "FAILED",
                    "PERMANENT_FAILED",
                    "WAITING_LLM_QUOTA",
                }:
                    self.breaker.record_failure(pick.lane_id)

            try:
                with connect(self.config.db_path) as conn:
                    conn.execute(
                        "DELETE FROM lane_leases WHERE lane_id = ?",
                        (pick.lane_id,),
                    )
                    conn.commit()
            except Exception:
                pass

            results.append(res)
        return results

    def _watchdog_check(
        self, active_jobs: dict[Any, tuple[LanePick, float]]
    ) -> list[TurnResult]:
        """Cancel futures exceeding turn timeout and terminate orphaned ffmpeg."""
        now_mono = time.monotonic()
        timeout = self._turn_timeout_seconds()
        timed_out = [
            f for f, (_, s_time) in active_jobs.items() if now_mono - s_time >= timeout
        ]
        results: list[TurnResult] = []
        for fut in timed_out:
            pick, _ = active_jobs.pop(fut)
            fut.cancel()
            try:
                from src.core.process_watch import terminate_hung_ffmpeg

                terminate_hung_ffmpeg(
                    max_age_seconds=0, parent_pid=os.getpid(), grace_seconds=1.0
                )
            except Exception:
                logger.debug("hung ffmpeg terminate failed", exc_info=True)

            ch_val = pick.channel.value if hasattr(pick.channel, "value") else str(pick.channel)
            res: TurnResult = {
                "status": "RETRYABLE_FAILED",
                "lane": pick.lane_id,
                "channel": ch_val,
                "error": "turn timed out waiting for worker",
                "error_code": "timeout",
            }
            self.commit_empty(pick)
            self.breaker.record_failure(pick.lane_id)
            try:
                with connect(self.config.db_path) as conn:
                    conn.execute("DELETE FROM lane_leases WHERE lane_id = ?", (pick.lane_id,))
                    conn.commit()
            except Exception:
                pass
            results.append(res)
        return results

    def _dispatch_due_lanes(
        self,
        pool: ThreadPoolExecutor,
        active_jobs: dict[Any, tuple[LanePick, float]],
    ) -> int:
        """Query due lanes excluding active jobs and submit up to available capacity."""
        running_lane_ids = {p.lane_id for p, _ in active_jobs.values()}
        allowed_lanes = set(self.active_lanes.keys()) - running_lane_ids
        available_slots = max(0, self.capacity - len(active_jobs))
        if available_slots <= 0 or not allowed_lanes:
            return 0

        picks = self.lane_scheduler.take_due_lanes(
            max_picks=available_slots,
            lanes_filter=allowed_lanes,
            exclude_lanes=running_lane_ids,
        )
        for pick in picks:
            fut = pool.submit(
                self._execute_lane_pick,
                self.config.db_path,
                pick,
                self.breaker,
                self.config.generate_only,
            )
            active_jobs[fut] = (pick, time.monotonic())
        return len(picks)

    def _run_sweeps_if_due(self, ticks: int) -> None:
        """Execute 30s review sweeps and periodic 24-hour maintenance sweeps."""
        if not self.config.enable_sweeps:
            return
        now_mono = time.monotonic()
        if now_mono - self._last_auto_publish_sweep >= 30.0:
            self._last_auto_publish_sweep = now_mono
            try:
                from src.daemon import _run_auto_publish_sweep

                _run_auto_publish_sweep(channel=self.target_channel)
            except Exception:
                logger.debug("auto-publish sweep skipped", exc_info=True)

        now_wall = time.time()
        if now_wall - self._last_24h_sweep >= 86400.0 or (ticks > 0 and ticks % 60 == 0):
            self._last_24h_sweep = now_wall
            try:
                from src.daemon import _run_24h_maintenance_sweep

                _run_24h_maintenance_sweep(
                    self.config.db_path, channel=self.target_channel or "all"
                )
            except Exception:
                logger.debug("24h maintenance sweep skipped", exc_info=True)

        try:
            import src.core.repository as _repo

            _repo.touch_daemon_liveness(self.config.db_path)
        except Exception:
            logger.debug("touch_daemon_liveness failed", exc_info=True)

    def _responsive_sleep(self, seconds: float, tick: float = 1.0) -> bool:
        """Sleep sliced into 1.0s chunks, exiting immediately if shutdown requested."""
        if is_test_environment():
            time.sleep(0)
            return self.is_shutdown_requested()
        if seconds <= 0:
            return self.is_shutdown_requested()
        end_time = time.monotonic() + seconds
        while time.monotonic() < end_time:
            if self.is_shutdown_requested():
                return True
            remaining = end_time - time.monotonic()
            wait_dur = min(tick, remaining)
            if wait_dur > 0 and self._shutdown_event.wait(timeout=wait_dur):
                return True
        return self.is_shutdown_requested()

    def tick(
        self,
        pool: ThreadPoolExecutor,
        active_jobs: dict[Any, tuple[LanePick, float]],
    ) -> list[TurnResult]:
        """Execute a single evaluation cycle of the multi-lane orchestration engine."""
        self._reap_zombies_safe()
        try:
            from src.core.lease_reaper import LeaseReaper

            LeaseReaper(db_path=self.config.db_path).reap_once(channel=self.target_channel)
        except Exception:
            pass

        self._run_sweeps_if_due(self._ticks)
        results = self._drain_completed_futures(active_jobs)
        results.extend(self._watchdog_check(active_jobs))
        self._dispatch_due_lanes(pool, active_jobs)
        return results

    def run_loop(self) -> list[TurnResult]:
        """Run the main continuous multi-lane scheduling loop until shutdown."""
        self.initialize()
        if self.is_shutdown_requested():
            return []
        results: list[TurnResult] = []
        active_jobs: dict[Any, tuple[LanePick, float]] = {}

        with ThreadPoolExecutor(
            max_workers=self.max_parallel, thread_name_prefix="lane"
        ) as pool:
            while not self.is_shutdown_requested():
                results.extend(self.tick(pool, active_jobs))
                self._ticks += 1
                if self.config.max_ticks is not None and self._ticks >= self.config.max_ticks:
                    break

                if active_jobs:
                    wait_step = min(5.0, self._watchdog_tick_seconds())
                    wait(active_jobs.keys(), timeout=wait_step, return_when=FIRST_COMPLETED)
                else:
                    wait_time = min(
                        self.config.interval_seconds,
                        max(
                            1,
                            self.lane_scheduler.seconds_until_due(
                                lanes_filter=set(self.active_lanes.keys())
                            ),
                        ),
                    )
                    if self._responsive_sleep(wait_time):
                        break

            # Graceful cleanup of any remaining active jobs
            if active_jobs:
                timeout = self._turn_timeout_seconds()
                end_time = time.monotonic() + timeout
                while active_jobs and time.monotonic() < end_time:
                    results.extend(self._drain_completed_futures(active_jobs))
                    if not active_jobs:
                        break
                    wait(
                        active_jobs.keys(),
                        timeout=min(1.0, max(0.1, end_time - time.monotonic())),
                        return_when=FIRST_COMPLETED,
                    )
                # Cancel any residual uncompleted jobs
                for fut, (pick, _) in list(active_jobs.items()):
                    fut.cancel()
                    ch_val = (
                        pick.channel.value
                        if hasattr(pick.channel, "value")
                        else str(pick.channel)
                    )
                    results.append(
                        {
                            "status": "RETRYABLE_FAILED",
                            "lane": pick.lane_id,
                            "channel": ch_val,
                            "error": "Shutdown cancelled unfinished worker",
                            "error_code": "shutdown_cancelled",
                        }
                    )
                active_jobs.clear()

        return results
