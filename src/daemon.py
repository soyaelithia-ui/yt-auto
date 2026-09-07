"""Persistent scheduler entrypoints for the safe pipeline."""

from __future__ import annotations

import os
import random
import threading
import time
from typing import Any

from src.config import DEFAULT_DB_PATH
from src.core.domain import QuotaError, canonical_channel
from src.core.providers import backoff_with_jitter
from src.core.repository import (
    QueueRepository,
    read_daemon_heartbeat,
    touch_daemon_liveness,
)
from src.core.guard import ConsecutiveFailureBreaker, ensure_disk_available
from src.core.process_watch import reap_zombies
from src.core.scheduler import PersistentScheduler
from src.log import get_logger
from src.observability.alerts import send_operational_alert
from src.observability.context import clear_run_context
from src.observability.events import emit_event


logger = get_logger("daemon")
_SHUTDOWN_EVENT = threading.Event()
_SHUTDOWN_REQUESTED = False

_RENDER_SEMAPHORE = threading.Semaphore(1)
_SYNTHESIS_SEMAPHORE = threading.Semaphore(2)


def compute_simhash_64(text: str | None) -> int:
    """Computes a 64-bit SimHash fingerprint using token and bigram frequency weights."""
    import hashlib
    import re
    from collections import Counter

    if not text:
        return 0
    tokens = re.findall(r"\w+", str(text).lower())
    if not tokens:
        return 0

    features: list[str] = list(tokens)
    for i in range(len(tokens) - 1):
        features.append(f"{tokens[i]}_{tokens[i+1]}")

    counts = Counter(features)
    v = [0.0] * 64

    for feat, weight in counts.items():
        h_bytes = hashlib.md5(feat.encode("utf-8")).digest()[:8]
        h = int.from_bytes(h_bytes, byteorder="big")
        for i in range(64):
            bit = (h >> i) & 1
            v[i] += weight if bit else -weight

    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= 1 << i

    return fingerprint


def hamming_distance_64(h1: int | None, h2: int | None) -> int:
    """Computes Hamming distance between two 64-bit integers."""
    v1 = int(h1 or 0) & 0xFFFFFFFFFFFFFFFF
    v2 = int(h2 or 0) & 0xFFFFFFFFFFFFFFFF
    xor = v1 ^ v2
    return bin(xor).count("1")


def evaluate_script_simhash(
    candidate_text: str,
    history_hashes: list[int] | tuple[int, ...] | set[int] | Any = None,
    min_hamming_distance: int = 4,
    *,
    repository: Any = None,
    channel: str = "moku",
) -> bool:
    """Returns True if candidate text is sufficiently distinct (Hamming >= min_hamming_distance) against history."""
    candidate_hash = compute_simhash_64(candidate_text)
    if candidate_hash == 0:
        return True

    target_repo = repository or (history_hashes if hasattr(history_hashes, "has_near_duplicate") else None)
    if target_repo is not None and hasattr(target_repo, "has_near_duplicate"):
        return not target_repo.has_near_duplicate(
            channel, candidate_hash, max_distance=min_hamming_distance - 1
        )

    if isinstance(history_hashes, (list, tuple, set)):
        for hist_h in history_hashes:
            if hist_h is not None:
                dist = hamming_distance_64(candidate_hash, int(hist_h))
                if dist < min_hamming_distance:
                    return False
        return True

    return True


def _startup_incident_check(database: str, interval_seconds: int) -> None:
    """Detect an unclean previous stop (crash/OOM) and alert with its cause."""
    threshold = int(
        os.environ.get("YT_LIVENESS_STALE_SEC", str(max(600, 2 * interval_seconds)))
    )
    import time as _time

    heartbeat = read_daemon_heartbeat(database)
    if not heartbeat or (_time.time() - heartbeat) <= threshold:
        return  # fresh install or heartbeat still fresh

    repository = QueueRepository(database)
    try:
        orphans = [
            row
            for row in repository.recent_failed_runs(limit=10)
            if row.get("status") == "PROCESSING"
        ]
        last_failed = repository.recent_failed_runs(limit=1)
    except Exception:
        logger.debug("incident inspection failed", exc_info=True)
        return
    cause = "el daemon dejó de responder (posible OOM o corte de energía)"
    if orphans:
        first = orphans[0]
        cause = (
            f"run huérfano {first.get('run_id', '?')} en estado "
            f"{first.get('status')} (canal {first.get('channel', '?')})"
        )
        code = first.get("error_code")
        if code:
            cause += f" — último error: {code}"
    elif last_failed:
        row = last_failed[0]
        cause = (
            f"último run {row.get('run_id', '?')} terminó en {row.get('status')} "
            f"({row.get('error_code') or 'sin código'})"
        )
    detail = f"Reinicio tras parada no limpia ({_time.time() - heartbeat:.0f}s sin latido): {cause}."
    emit_event(
        "daemon_stopped",
        level="WARNING",
        message=detail,
        details={"stale_seconds": int(_time.time() - heartbeat)},
        db_path=database,
        component="daemon",
    )
    logger.warning("%s", detail)
    send_operational_alert("YTAuto reiniciado tras parada", detail)


def _preflight_disk_or_pause(
    database: str,
    channel_value: str,
) -> bool:
    """Disk guard pre-run: clean once; pause channel when still below floor.

    Returns True when the turn may proceed.
    """
    report = ensure_disk_available()
    if report.ok:
        return True
    tightest = report.tightest_path or "?"
    free_gb = report.checked.get(tightest, 0) / (1024**3)
    message = (
        f"Disco por debajo del mínimo ({free_gb:.2f} GB libres en {tightest}); "
        f"limpieza automática liberó {report.cleaned_bytes / (1024**2):.1f} MB. "
        "Canal pausado; libera espacio y ejecuta manage.py resume."
    )
    emit_event(
        "guard_triggered",
        level="ERROR",
        error_code="disk_floor_exceeded",
        message=message,
        details={"checked": report.checked, "cleaned_bytes": report.cleaned_bytes},
        db_path=database,
        component="resource_guard",
        channel=channel_value,
    )
    logger.error("%s", message)
    try:
        QueueRepository(database).pause(channel_value, reason="disk_floor_exceeded")
    except Exception:
        logger.debug("channel pause failed", exc_info=True)
    send_operational_alert(
        f"Canal {channel_value} pausado: disco bajo",
        message,
    )
    return False



def run_pipeline_once(
    channel: str = "moku",
    db_path: str | None = None,
    generate_only: bool = False,
    story_id: str | None = None,
    lane_id: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Compatibility entrypoint with an explicit canonical channel and bounded concurrency."""
    from src.pipeline import run_pipeline_once as safe_run
    from src.cleaner import clean_run_intermediates

    work_dir = None
    with _RENDER_SEMAPHORE:
        try:
            res = safe_run(
                channel=canonical_channel(channel or "moku").value,
                db_path=db_path,
                generate_only=generate_only,
                story_id=story_id,
                lane_id=lane_id,
                **kwargs,
            )
            if isinstance(res, dict):
                work_dir = res.get("work_dir")
            return res
        finally:
            if work_dir:
                try:
                    clean_run_intermediates(work_dir)
                except Exception:
                    pass


def run_lane_once(
    lane_id: str,
    channel: str,
    db_path: str | None = None,
    generate_only: bool = False,
    story_id: str | None = None,
) -> dict[str, Any]:
    """Run one production iteration of a specific lane."""
    from src.pipeline import run_pipeline_once as safe_run

    return safe_run(
        channel=canonical_channel(channel).value,
        db_path=db_path,
        generate_only=generate_only,
        story_id=story_id,
        lane_id=lane_id,
    )


def request_shutdown() -> None:
    global _SHUTDOWN_REQUESTED
    _SHUTDOWN_REQUESTED = True
    _SHUTDOWN_EVENT.set()


def reset_shutdown() -> None:
    global _SHUTDOWN_REQUESTED
    _SHUTDOWN_REQUESTED = False
    _SHUTDOWN_EVENT.clear()


def is_shutdown_requested() -> bool:
    return _SHUTDOWN_EVENT.is_set() or _SHUTDOWN_REQUESTED


def _start_telegram_callback_poller() -> None:
    """Start the review callback listener only in the production daemon."""
    if os.environ.get("ENABLE_TELEGRAM_CALLBACK_POLLING", "1") != "1":
        return
    from src.config import is_test_environment

    if is_test_environment():
        return
    from src.telegram.callbacks import poll_callbacks
    from review.telegram_bot import TelegramReviewBot

    bot = TelegramReviewBot()
    if not bot.token or not bot.chat_id:
        logger.warning("Telegram callback polling disabled: credentials are not configured")
        return
    threading.Thread(
        target=poll_callbacks,
        args=(bot, is_shutdown_requested),
        name="telegram-callback-poller",
        daemon=True,
    ).start()
    logger.info("Telegram callback polling enabled")


def _register_turn_failure(
    database: str,
    channel_value: str,
    breaker: ConsecutiveFailureBreaker,
    error_text: str | None,
) -> None:
    """Feed the consecutive-failure breaker; pause channel when it trips."""
    try:
        tripped = breaker.record_failure(channel_value)
    except Exception:
        logger.debug("breaker accounting failed", exc_info=True)
        return
    if not tripped:
        return
    count = breaker.counts.get(channel_value, 0)
    message = (
        f"{count} fallos consecutivos en canal {channel_value}. "
        f"Último error: {error_text or 'desconocido'}. Canal pausado automáticamente; "
        "revisa main.py --errors y ejecuta manage.py resume para reactivar."
    )
    emit_event(
        "guard_triggered",
        level="ERROR",
        error_code="consecutive_failures_pause",
        message=message,
        details={"consecutive_failures": count},
        db_path=database,
        channel=channel_value,
        component="resource_guard",
    )
    logger.error("%s", message)
    try:
        QueueRepository(database).pause(
            channel_value, reason="consecutive_failures"
        )
    except Exception:
        logger.debug("channel pause failed", exc_info=True)
    send_operational_alert(
        f"Canal {channel_value} pausado por fallos repetidos",
        message,
    )


def _responsive_sleep(seconds: float, tick: float = 1.0) -> bool:
    from src.config import is_test_environment
    if is_test_environment():
        time.sleep(0)
        return is_shutdown_requested()
    return _SHUTDOWN_EVENT.wait(timeout=max(0.0, seconds)) or _SHUTDOWN_REQUESTED


def _reap_zombies_safe() -> None:
    """Reap exited children in production only. Pytest hosts other children."""
    from src.config import is_test_environment

    if is_test_environment():
        return
    try:
        reap_zombies()
    except Exception:
        logger.debug("zombie reap skipped", exc_info=True)


def _turn_timeout_seconds() -> float:
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


def _watchdog_tick_seconds() -> float:
    try:
        return max(0.05, float(os.environ.get("DAEMON_WATCHDOG_TICK_SECONDS", "5")))
    except ValueError:
        return 5.0


def _await_future_responsive(
    future,
    *,
    timeout: float,
    database: str,
    tick: float = 5.0,
    touch_heartbeat: bool | None = None,
):
    """Wait for ``future`` in short slices: reap zombies and refresh liveness.

    Returns ``(result, timed_out)``. Never calls ``future.result()`` without a
    timeout, so a hung FFmpeg turn cannot pin the scheduler loop.
    """
    from concurrent.futures import wait, FIRST_COMPLETED

    from src.config import is_test_environment

    if touch_heartbeat is None:
        touch_heartbeat = not is_test_environment()
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        _reap_zombies_safe()
        if touch_heartbeat:
            try:
                touch_daemon_liveness(database)
            except Exception:
                logger.debug("daemon liveness touch failed", exc_info=True)
        if is_shutdown_requested():
            return None, True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None, True
        done, _pending = wait(
            {future}, timeout=min(tick, remaining), return_when=FIRST_COMPLETED
        )
        if future in done:
            return future.result(), False


def _timeout_result(pick: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "RETRYABLE_FAILED",
        "error": "turn timed out waiting for worker",
        "error_code": "timeout",
    }
    if pick is None:
        return payload
    payload["lane"] = getattr(pick, "lane_id", None)
    channel = getattr(pick, "channel", None)
    payload["channel"] = getattr(channel, "value", channel)
    return payload


def _collect_futures_responsive(
    futures: dict[Any, Any],
    *,
    timeout: float,
    database: str,
    tick: float = 5.0,
    touch_heartbeat: bool | None = None,
) -> list[dict[str, Any]]:
    """Drain a batch of lane futures without an unbounded ``result()`` wait."""
    from concurrent.futures import wait, FIRST_COMPLETED

    from src.config import is_test_environment
    from src.core.process_watch import terminate_hung_ffmpeg

    if touch_heartbeat is None:
        touch_heartbeat = not is_test_environment()
    results: list[dict[str, Any]] = []
    pending = set(futures)
    deadline = time.monotonic() + max(0.0, timeout)
    last_sweep_time = 0.0
    while pending:
        _reap_zombies_safe()
        if touch_heartbeat:
            try:
                touch_daemon_liveness(database)
            except Exception:
                logger.debug("daemon liveness touch failed", exc_info=True)
            if time.monotonic() - last_sweep_time >= 30.0:
                last_sweep_time = time.monotonic()
                _run_auto_publish_sweep()
        if is_shutdown_requested():
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if not is_test_environment():
                try:
                    terminate_hung_ffmpeg(
                        max_age_seconds=0,
                        parent_pid=os.getpid(),
                        grace_seconds=1.0,
                    )
                except Exception:
                    logger.debug("hung ffmpeg terminate failed", exc_info=True)
            for fut in pending:
                results.append(_timeout_result(futures.get(fut)))
            break
        done, pending = wait(
            pending, timeout=min(tick, remaining), return_when=FIRST_COMPLETED
        )
        for fut in done:
            pick = futures[fut]
            try:
                results.append(fut.result())
            except Exception as exc:
                logger.error(
                    "Lane %s falló de forma inesperada: %s",
                    getattr(pick, "lane_id", "?"),
                    exc,
                )
                results.append(
                    {
                        "status": "RETRYABLE_FAILED",
                        "lane": getattr(pick, "lane_id", None),
                        "error": str(exc),
                    }
                )
    return results


def _run_turn_responsive(fn, *, timeout: float, database: str, tick: float | None = None):
    """Run one pipeline turn; in production, watchdog the worker thread."""
    from src.config import is_test_environment

    if is_test_environment():
        return fn(), False

    from concurrent.futures import ThreadPoolExecutor
    from src.core.process_watch import terminate_hung_ffmpeg

    timed_out = False
    tick_s = _watchdog_tick_seconds() if tick is None else tick
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="turn")
    try:
        future = pool.submit(fn)
        result, timed_out = _await_future_responsive(
            future, timeout=timeout, database=database, tick=tick_s
        )
        if timed_out:
            try:
                terminate_hung_ffmpeg(
                    max_age_seconds=0, parent_pid=os.getpid(), grace_seconds=1.0
                )
            except Exception:
                logger.debug("hung ffmpeg terminate failed", exc_info=True)
            return _timeout_result(), True
        return result, False
    finally:
        pool.shutdown(wait=not timed_out, cancel_futures=True)


def _run_auto_publish_sweep() -> None:
    """Publish pending reviews whose approval window (AUTO_PUBLISH_TIMEOUT_HOURS, default 24h) has elapsed."""
    if os.environ.get("ENABLE_AUTO_PUBLISH_SWEEP") != "1":
        return
    try:
        from src.telegram import check_pending_approvals

        check_pending_approvals()
    except Exception as exc:  # pragma: no cover - operational guard
        logger.warning("auto-publish sweep failed: %s", exc, exc_info=True)


def start_daemon(
    interval_seconds: int = 1800,
    max_runs: int | None = None,
    db_path: str | None = None,
    channels: list[str] | None = None,
    mass_produce: bool = False,
    sequential: bool = False,
    video_mode: str | None = None,
) -> list[dict[str, Any]]:
    """Run persistent turns. When sequential=True, process turns back-to-back with 1s interval."""
    del mass_produce
    if sequential:
        interval_seconds = 1
    reset_shutdown()
    database = db_path or DEFAULT_DB_PATH
    scheduler = PersistentScheduler(database, interval_seconds=interval_seconds)
    scheduler.initialize()
    from src.config import is_test_environment as _ite

    if not _ite():
        _startup_incident_check(database, interval_seconds)
        try:
            pruned = QueueRepository(database).prune_system_events(
                retention_days=int(os.environ.get("YT_EVENTS_RETENTION_DAYS", "30"))
            )
            if pruned:
                logger.info("system_events prune: %d eventos eliminados", pruned)
        except Exception:
            logger.debug("system_events prune skipped", exc_info=True)
        try:
            from src.observability.bundle import clean_agent_review_bundles

            removed = clean_agent_review_bundles()
            if removed.get("removed_bundles"):
                logger.info("agent_review prune: %s", removed)
        except Exception:
            logger.debug("agent_review prune skipped", exc_info=True)
        # R6: reclaim failed-run dirs and orphaned temp debris on startup
        # (previously implemented but never wired into the daemon loop).
        if os.environ.get("DAEMON_STARTUP_CLEANUP", "1") == "1":
            try:
                from src.cleaner import (
                    clean_expired_failed_runs,
                    clean_untracked_temp_files,
                )

                expired = clean_expired_failed_runs()
                orphans = clean_untracked_temp_files()
                if expired["freed_bytes"] or orphans["freed_bytes"]:
                    logger.info(
                        "startup cleanup: %d run dirs (%d bytes), %d temp files (%d bytes)",
                        expired["deleted_dirs_count"],
                        expired["freed_bytes"],
                        orphans["deleted_files_count"],
                        orphans["freed_bytes"],
                    )
            except Exception:
                logger.debug("startup cleanup skipped", exc_info=True)
    breaker = ConsecutiveFailureBreaker()
    allowed = (
        {canonical_channel(value).value for value in channels}
        if channels
        else {"moku", "aelithia"}
    )
    results: list[dict[str, Any]] = []

    attempts = 0

    from src.config import is_test_environment
    if max_runs is None:
        _start_telegram_callback_poller()
    while not _SHUTDOWN_REQUESTED and (max_runs is None or attempts < max_runs):
        _reap_zombies_safe()
        if not is_test_environment():
            _run_auto_publish_sweep()
        try:
            touch_daemon_liveness(database)
        except Exception:
            logger.debug("daemon liveness touch failed", exc_info=True)
        now_time = int(time.time() + (attempts * (interval_seconds + 1) if is_test_environment() else 0))
        decision = scheduler.take_due_turn(now=now_time)
        if decision is None:
            if _responsive_sleep(min(30, max(1, scheduler.seconds_until_due()))):
                break
            continue
        if decision.channel.value not in allowed:
            if _responsive_sleep(scheduler.seconds_until_due()):
                break
            continue

        attempts += 1
        try:
            touch_daemon_liveness(database)
        except Exception:
            logger.debug("daemon liveness touch failed", exc_info=True)
        if not _ite() and not _preflight_disk_or_pause(database, decision.channel.value):
            results.append(
                {
                    "status": "GUARD_DISK_PAUSED",
                    "channel": decision.channel.value,
                    "error": "disk floor exceeded; channel paused",
                }
            )
            break
        try:
            extra = {}
            if video_mode is not None:
                extra["video_mode"] = video_mode
            result, timed_out = _run_turn_responsive(
                lambda: run_pipeline_once(
                    channel=decision.channel.value,
                    db_path=database,
                    **extra,
                ),
                timeout=_turn_timeout_seconds(),
                database=database,
            )
            if timed_out:
                result = dict(result or {})
                result.setdefault("channel", decision.channel.value)
                _register_turn_failure(
                    database, decision.channel.value, breaker, result.get("error")
                )
            else:
                status_value = str(result.get("status", ""))
                if status_value in {"PUBLISHED", "COMPLETED"}:
                    breaker.record_success(decision.channel.value)
                elif status_value in {"RETRYABLE_FAILED", "FAILED", "PERMANENT_FAILED"}:
                    _register_turn_failure(
                        database, decision.channel.value, breaker, result.get("error")
                    )
        except QuotaError as exc:
            delay = backoff_with_jitter(
                attempts,
                cap_seconds=float(interval_seconds),
                rng=random.Random(attempts),
            )
            result = {
                "status": "WAITING_LLM_QUOTA",
                "channel": decision.channel.value,
                "error": str(exc),
            }
            logger.warning("Provider quota deferred the current channel")
            if _responsive_sleep(min(delay, scheduler.seconds_until_due())):
                results.append(result)
                break
        except Exception as exc:
            result = {
                "status": "RETRYABLE_FAILED",
                "channel": decision.channel.value,
                "error": str(exc),
            }
            logger.exception("Scheduled pipeline iteration failed")
            emit_event(
                "run_failed",
                level="ERROR",
                error_code="turn_exception",
                message=str(exc),
                db_path=database,
                channel=decision.channel.value,
                component="daemon",
            )
            _register_turn_failure(database, decision.channel.value, breaker, str(exc))
        finally:
            clear_run_context()
        results.append(result)
        if max_runs is not None and attempts >= max_runs:
            break
        if _responsive_sleep(scheduler.seconds_until_due()):
            break
    return results


def _execute_lane_pick(
    database: str,
    pick: LanePick,
    breaker: ConsecutiveFailureBreaker,
    generate_only: bool = False,
) -> dict[str, Any]:
    """Run one lane iteration: claim → pipeline → cadence bookkeeping."""
    from src.config import is_test_environment
    from src.pipeline import run_pipeline_once as safe_run

    repository = QueueRepository(database)
    owner = f"lane-{pick.lane_id}"
    lease_seconds = max(900, int(os.environ.get("RENDER_TIMEOUT_SECONDS", "10800")) // 2)
    job: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    try:
        job = repository.claim_resumable(
            pick.lane_id, pick.channel.value, owner, lease_seconds=lease_seconds
        )
        mode = "resume"
        if job is None:
            job = repository.claim_for_lane(
                pick.lane_id, pick.channel.value, owner, lease_seconds=lease_seconds
            )
            mode = "fresh"
        if job is None and not is_test_environment():
            try:
                from src.scraper import ensure_queue_depth
                from src.core.lanes import resolve_lane_for_run

                lane_def = resolve_lane_for_run(pick.channel, pick.lane_id)
                logger.info(
                    "Lane %s sin historias pendientes; reponiendo con ensure_queue_depth...",
                    pick.lane_id,
                )
                ensure_queue_depth(lane_def, db_path=database)
                job = repository.claim_for_lane(
                    pick.lane_id, pick.channel.value, owner, lease_seconds=lease_seconds
                )
                mode = "fresh_replenished"
            except Exception as repl_exc:
                logger.warning(
                    "Fallo al reponer cola para lane %s: %s", pick.lane_id, repl_exc
                )
        if job is None:
            scheduler_commit_empty(pick)
            return {
                "status": "LANE_EMPTY",
                "lane": pick.lane_id,
                "channel": pick.channel.value,
            }
        logger.info(
            "Lane %s reclamó historia %s (%s)", pick.lane_id, job["story_id"], mode
        )
        with _RENDER_SEMAPHORE:
            result = safe_run(
                channel=pick.channel.value,
                db_path=database,
                generate_only=generate_only,
                story_id=job["story_id"],
                lane_id=pick.lane_id,
                run_id=job.get("run_id"),
                owner=owner,
                story=job,
            )
    except QuotaError as exc:
        result = {
            "status": "WAITING_LLM_QUOTA",
            "lane": pick.lane_id,
            "channel": pick.channel.value,
            "error": str(exc),
        }
    except Exception as exc:
        result = {
            "status": "RETRYABLE_FAILED",
            "lane": pick.lane_id,
            "channel": pick.channel.value,
            "error": str(exc),
        }
        emit_event(
            "run_failed",
            level="ERROR",
            error_code="lane_turn_exception",
            message=str(exc),
            db_path=database,
            channel=pick.channel.value,
            component="daemon",
        )
    finally:
        clear_run_context()
        if result and isinstance(result, dict) and result.get("work_dir"):
            try:
                from src.cleaner import clean_run_intermediates
                clean_run_intermediates(result["work_dir"])
            except Exception:
                pass

    if result is None:
        return {"status": "LANE_EMPTY", "lane": pick.lane_id, "channel": pick.channel.value}

    scheduler_commit_fire(pick, run_id=job["run_id"] if job else None)
    status_value = str(result.get("status", ""))
    if status_value in {"PUBLISHED", "COMPLETED"}:
        breaker.record_success(pick.channel.value)
    elif status_value in {"RETRYABLE_FAILED", "FAILED", "PERMANENT_FAILED"}:
        _register_turn_failure(database, pick.channel.value, breaker, result.get("error"))
    elif status_value in {"STORY_NOT_CLAIMABLE", "NO_PENDING_STORIES"} and job:
        try:
            repository.finish_lane_run(job["run_id"], JobStatus.RETRYABLE_FAILED, owner=owner)
        except Exception:
            pass
    return result


scheduler_commit_fire = None  # set by start_daemon_lanes; overridable in tests
scheduler_commit_empty = None  # set by start_daemon_lanes; overridable in tests


def start_daemon_lanes(
    interval_seconds: int = 60,
    max_picks: int | None = None,
    db_path: str | None = None,
    lanes_filter: list[str] | None = None,
    max_parallel: int | None = None,
    generate_only: bool = False,
    max_ticks: int | None = None,
) -> list[dict[str, Any]]:
    """Persistent multi-lane daemon: concurrent production by cadence ceiling.

    Replaces the legacy short/longform tmux grid: every tick the LaneScheduler
    picks due lanes (respecting per-lane ``min_gap_seconds`` ceilings), each
    pick runs concurrently in a thread pool, and a productive fire advances
    that lane's ceiling — never accumulating catch-up work. ``max_ticks``
    bounds idle ticks (tests and supervised one-shots); production omits it.
    """
    from concurrent.futures import ThreadPoolExecutor

    from src.config import is_test_environment
    from src.core.scheduler import LanePick, LaneScheduler

    global scheduler_commit_fire, scheduler_commit_empty
    reset_shutdown()
    database = db_path or DEFAULT_DB_PATH
    parallel = max(1, int(max_parallel or os.environ.get("YT_MAX_PARALLEL_LANES", "2")))
    lane_scheduler = LaneScheduler(database)
    lane_scheduler.initialize()
    active_lanes = {
        lane.id: lane
        for lane in lane_scheduler.lanes
        if lanes_filter is None or lane.id in lanes_filter
    }
    if max_picks is None:
        max_picks = len(active_lanes)
    results: list[dict[str, Any]] = []

    scheduler_commit_fire = lane_scheduler.commit_fire
    scheduler_commit_empty = lane_scheduler.commit_empty

    if not is_test_environment():
        _startup_incident_check(database, interval_seconds)
        try:
            from src.cleaner import (
                clean_expired_failed_runs,
                clean_untracked_temp_files,
            )
            clean_expired_failed_runs()
            clean_untracked_temp_files()
        except Exception:
            logger.debug("daemon lane startup cleanup skipped", exc_info=True)
    if max_parallel is None and not is_test_environment():
        _start_telegram_callback_poller()
    breaker = ConsecutiveFailureBreaker()
    attempts = 0
    ticks = 0
    with ThreadPoolExecutor(max_workers=parallel, thread_name_prefix="lane") as pool:
        while not _SHUTDOWN_REQUESTED:
            _reap_zombies_safe()
            if max_ticks is not None and ticks >= max_ticks:
                break
            ticks += 1
            if not is_test_environment():
                _run_auto_publish_sweep()
                if ticks % 360 == 0:
                    try:
                        from src.cleaner import (
                            clean_expired_failed_runs,
                            clean_untracked_temp_files,
                        )
                        clean_expired_failed_runs()
                        clean_untracked_temp_files()
                    except Exception:
                        logger.debug("periodic background cleanup skipped", exc_info=True)
                try:
                    touch_daemon_liveness(database)
                except Exception:
                    logger.debug("daemon liveness touch failed", exc_info=True)
            picks = lane_scheduler.take_due_lanes(
                max_picks=max_picks, lanes_filter=set(active_lanes)
            )
            if not picks:
                wait_time = min(
                    interval_seconds,
                    max(1, lane_scheduler.seconds_until_due(lanes_filter=set(active_lanes))),
                )
                if _responsive_sleep(wait_time):
                    break
                continue
            futures = {
                pool.submit(
                    _execute_lane_pick, database, pick, breaker, generate_only
                ): pick
                for pick in picks
            }
            results.extend(
                _collect_futures_responsive(
                    futures,
                    timeout=_turn_timeout_seconds(),
                    database=database,
                    tick=_watchdog_tick_seconds(),
                )
            )
            attempts += 1
            if _responsive_sleep(min(interval_seconds, 30)):
                break
    return results
