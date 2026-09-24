"""Persistent scheduler entrypoints for the safe pipeline."""

from __future__ import annotations

import os
import random
import socket
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

from src.core.render_guard import _LONG_RENDER_SEMAPHORE

_RENDER_SEMAPHORE = _LONG_RENDER_SEMAPHORE
_SYNTHESIS_SEMAPHORE = threading.Semaphore(2)


from src.core.repository import (
    compute_simhash_64,
    hamming_distance_64,
)


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


def _startup_incident_check(
    database: str, interval_seconds: int, channel: Optional[str] = None
) -> None:
    """Detect an unclean previous stop (crash/OOM) and alert with its cause."""
    threshold = int(
        os.environ.get("YT_LIVENESS_STALE_SEC", str(max(600, 2 * interval_seconds)))
    )
    import time as _time

    heartbeat = read_daemon_heartbeat(database)
    if not heartbeat or (_time.time() - heartbeat) <= threshold:
        return  # fresh install or heartbeat still fresh

    target_ch: Optional[str] = None
    if channel:
        from src.core.domain import canonical_channel

        try:
            can = canonical_channel(channel)
            target_ch = can.value if hasattr(can, "value") else str(can)
        except Exception:
            target_ch = str(channel)

    repository = QueueRepository(database)
    try:
        orphans = [
            row
            for row in repository.recent_failed_runs(limit=10)
            if row.get("status") == "PROCESSING"
            and (target_ch is None or row.get("channel") == target_ch)
        ]
        last_failed = [
            row
            for row in repository.recent_failed_runs(limit=1)
            if target_ch is None or row.get("channel") == target_ch
        ]
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


def _friendly_name(identifier: str) -> str:
    name_map = {
        "moku": "Expedientes de Terror",
        "horror": "Expedientes de Terror",
        "moku-scp-shorts": "Expedientes de Terror (Shorts)",
        "moku-horror-long": "Expedientes de Terror (Largos)",
        "horror-long": "Expedientes de Terror (Largos)",
        "horror-shorts": "Expedientes de Terror (Shorts)",
        "aelithia": "Dilemas Morales",
        "drama": "Dilemas Morales",
        "aelithia-aita-long": "Dilemas Morales (Largos)",
        "aelithia-drama-shorts": "Dilemas Morales (Shorts)",
        "drama-long": "Dilemas Morales (Largos)",
        "drama-shorts": "Dilemas Morales (Shorts)",
    }
    return name_map.get(str(identifier).lower(), str(identifier))


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
        f"Canal {_friendly_name(channel_value)} pausado: disco bajo",
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
    finally:
        if work_dir:
            try:
                clean_run_intermediates(work_dir)
            except Exception as exc:
                logger.debug("clean_run_intermediates failed for %s: %s", work_dir, exc)
    return res


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
    _release_telegram_poller_lock()


def reset_shutdown() -> None:
    global _SHUTDOWN_REQUESTED
    _SHUTDOWN_REQUESTED = False
    _SHUTDOWN_EVENT.clear()


def is_shutdown_requested() -> bool:
    return _SHUTDOWN_EVENT.is_set() or _SHUTDOWN_REQUESTED


_TELEGRAM_POLLER_LOCK_HANDLE: Any = None
_TELEGRAM_POLLER_STARTED: bool = False


def _acquire_telegram_poller_lock() -> bool:
    """Acquire a non-blocking process-wide singleton lock for Telegram callback poller."""
    global _TELEGRAM_POLLER_LOCK_HANDLE
    if _TELEGRAM_POLLER_LOCK_HANDLE is not None:
        return True
    import fcntl
    from pathlib import Path
    from src.core.lock import _get_default_lock_path

    base_dir = Path(os.environ.get("YT_LOCK_DIR", Path(_get_default_lock_path()).parent))
    base_dir.mkdir(parents=True, exist_ok=True)
    lock_file = base_dir / "telegram_callback_poller.lock"
    f = None
    try:
        f = open(lock_file, "a+", encoding="utf-8")
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        f.seek(0)
        f.truncate()
        f.write(f"{os.getpid()}\n")
        f.flush()
        _TELEGRAM_POLLER_LOCK_HANDLE = f
        return True
    except (IOError, OSError):
        if f is not None:
            try:
                f.close()
            except Exception:
                pass
        return False


def _release_telegram_poller_lock() -> None:
    """Release the Telegram callback poller singleton lock."""
    global _TELEGRAM_POLLER_LOCK_HANDLE, _TELEGRAM_POLLER_STARTED
    _TELEGRAM_POLLER_STARTED = False
    if _TELEGRAM_POLLER_LOCK_HANDLE is not None:
        import fcntl
        try:
            fcntl.flock(_TELEGRAM_POLLER_LOCK_HANDLE, fcntl.LOCK_UN)
            _TELEGRAM_POLLER_LOCK_HANDLE.close()
        except Exception as exc:
            logger.debug("Failed unlocking telegram poller: %s", exc)
        _TELEGRAM_POLLER_LOCK_HANDLE = None


import atexit as _atexit
_atexit.register(_release_telegram_poller_lock)


def _start_telegram_callback_poller() -> bool:
    """Start the review callback listener only in the production daemon."""
    global _TELEGRAM_POLLER_STARTED
    if _TELEGRAM_POLLER_STARTED:
        return True
    if os.environ.get("ENABLE_TELEGRAM_CALLBACK_POLLING", "1") != "1":
        return False
    from src.config import is_test_environment

    if is_test_environment():
        return False

    if not _acquire_telegram_poller_lock():
        logger.debug(
            "Telegram callback poller already active in another daemon process; skipping in this instance."
        )
        return False

    from src.telegram.callbacks import poll_callbacks
    from review.telegram_bot import TelegramReviewBot

    bot = TelegramReviewBot()
    if not bot.token or not bot.chat_id:
        logger.warning("Telegram callback polling disabled: credentials are not configured")
        return False
    threading.Thread(
        target=poll_callbacks,
        args=(bot, is_shutdown_requested),
        name="telegram-callback-poller",
        daemon=True,
    ).start()
    _TELEGRAM_POLLER_STARTED = True
    logger.info("Telegram callback polling enabled")
    return True


def _register_turn_failure(
    database: str,
    channel_value: str,
    breaker: ConsecutiveFailureBreaker,
    error_text: str | None,
    lane_id: str | None = None,
) -> None:
    """Feed the consecutive-failure breaker; pause lane or channel when it trips."""
    breaker_key = lane_id or channel_value
    try:
        tripped = breaker.record_failure(breaker_key)
    except Exception:
        logger.debug("breaker accounting failed", exc_info=True)
        return
    if not tripped:
        return
    count = breaker.counts.get(breaker_key, 0)
    target_type = f"carril {lane_id}" if lane_id else f"canal {channel_value}"
    message = (
        f"{count} fallos consecutivos en {target_type}. "
        f"Último error: {error_text or 'desconocido'}. {target_type.capitalize()} pausado automáticamente; "
        "revisa main.py --errors y ejecuta main.py queue resume para reactivar."
    )
    emit_event(
        "guard_triggered",
        level="ERROR",
        error_code="consecutive_failures_pause",
        message=message,
        details={"consecutive_failures": count, "lane_id": lane_id},
        db_path=database,
        channel=channel_value,
        component="resource_guard",
    )
    logger.error("%s", message)
    if lane_id:
        try:
            QueueRepository(database).set_lane_paused(
                lane_id, True, reason="consecutive_failures"
            )
        except Exception:
            logger.debug("lane pause failed", exc_info=True)
        send_operational_alert(
            f"Carril {_friendly_name(lane_id)} pausado por fallos repetidos",
            message,
        )
    else:
        try:
            QueueRepository(database).pause(
                channel_value, reason="consecutive_failures"
            )
        except Exception:
            logger.debug("channel pause failed", exc_info=True)
        send_operational_alert(
            f"Canal {_friendly_name(channel_value)} pausado por fallos repetidos",
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
    channel: Optional[str] = None,
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
                _run_auto_publish_sweep(channel=channel)
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


def _run_auto_publish_sweep(channel: Optional[str] = None) -> None:
    """Publish pending reviews whose approval window (AUTO_PUBLISH_TIMEOUT_HOURS, default 24h) has elapsed."""
    if os.environ.get("ENABLE_AUTO_PUBLISH_SWEEP") != "1":
        return
    try:
        from src.telegram.approval import check_pending_approvals

        check_pending_approvals(channel=channel)
    except Exception as exc:  # pragma: no cover - operational guard
        logger.warning("auto-publish sweep failed: %s", exc, exc_info=True)


def _run_24h_maintenance_sweep(
    db_path: Optional[str] = None,
    channel: str = "all",
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Execute automated 24-hour analytics synchronization and underperforming video pruning."""
    database = db_path or DEFAULT_DB_PATH
    now_ts = int(time.time())
    try:
        from src.core.repository.migrations import connect, migrate_database
        migrate_database(database)

        with connect(database) as conn:
            row = conn.execute("SELECT last_24h_sweep_at FROM scheduler_state WHERE scheduler_id = 1").fetchone()
            last_sweep = row["last_24h_sweep_at"] if row else None

        if not force and last_sweep is not None and (now_ts - int(last_sweep)) < 86400:
            return {"ok": True, "skipped": True, "reason": "less_than_24h_since_last_sweep"}

        from src.analytics.link_collector import collect_channel_links
        from src.analytics.scoring import sync_and_score_channel_publications
        from src.analytics.pruner import execute_autonomous_prune
        from src.core.channel_profile import ChannelProfileRegistry

        channels_to_process = (
            list(ChannelProfileRegistry.list_active_channel_ids())
            if channel is None or channel == "all"
            else [channel]
        )
        if not channels_to_process:
            channels_to_process = ["moku", "aelithia"]

        collection_results = {}
        scoring_results = {}
        prune_results = {}

        for ch in channels_to_process:
            col_res = collect_channel_links(ch, db_path=database, dry_run=dry_run)
            collection_results[ch] = col_res

            score_res = sync_and_score_channel_publications(ch, db_path=database, dry_run=dry_run)
            scoring_results[ch] = score_res

            prune_res = execute_autonomous_prune(ch, db_path=database, dry_run=dry_run)
            prune_results[ch] = {
                "evaluated": prune_res.evaluated_count,
                "pruned": prune_res.pruned_count,
                "failed": prune_res.failed_count,
            }

        with connect(database) as conn:
            conn.execute(
                "UPDATE scheduler_state SET last_24h_sweep_at = ?, updated_at = CURRENT_TIMESTAMP WHERE scheduler_id = 1",
                (now_ts,),
            )
            conn.commit()

        logger.info("[24H-SWEEP] Completed maintenance sweep for channels: %s", channels_to_process)
        return {
            "ok": True,
            "timestamp": now_ts,
            "channels": channels_to_process,
            "collection": collection_results,
            "scoring": scoring_results,
            "pruning": prune_results,
            "dry_run": dry_run,
        }
    except Exception as exc:
        logger.warning("[24H-SWEEP] Maintenance sweep encountered error: %s", exc, exc_info=True)
        return {"ok": False, "error": str(exc)}


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

    ch_arg: str | None = channels[0] if (channels and len(channels) == 1) else None

    if not _ite():
        _startup_incident_check(database, interval_seconds, channel=ch_arg)
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
                    clean_tts_cache,
                )

                expired = clean_expired_failed_runs()
                orphans = clean_untracked_temp_files()
                clean_tts_cache(max_size_bytes=500 * 1024 * 1024)
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
    from src.core.channel_profile import ChannelProfileRegistry

    allowed = (
        {canonical_channel(value).value for value in channels}
        if channels
        else set(ChannelProfileRegistry.list_active_channel_ids())
    )
    results: list[dict[str, Any]] = []

    attempts = 0

    from src.config import is_test_environment
    if max_runs is None:
        _start_telegram_callback_poller()
    while not _SHUTDOWN_REQUESTED and (max_runs is None or attempts < max_runs):
        _reap_zombies_safe()
        if not is_test_environment():
            _run_auto_publish_sweep(channel=ch_arg)
            if max_runs is None and not _TELEGRAM_POLLER_STARTED:
                _start_telegram_callback_poller()
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
            continue
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
                err_detail = result.get("error") or result.get("reason") or result.get("error_msg")
                _register_turn_failure(
                    database, decision.channel.value, breaker, err_detail
                )
            else:
                status_value = str(result.get("status", ""))
                if status_value in {"PUBLISHED", "COMPLETED"}:
                    breaker.record_success(decision.channel.value)
                elif status_value in {"RETRYABLE_FAILED", "FAILED", "PERMANENT_FAILED"}:
                    err_detail = result.get("error") or result.get("reason") or result.get("error_msg")
                    _register_turn_failure(
                        database, decision.channel.value, breaker, err_detail
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
    owner = f"lane-{pick.lane_id}:{socket.gethostname()}:{os.getpid()}"
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
        if breaker.counts.get(pick.channel.value, 0) >= breaker.threshold:
            breaker.reset(pick.channel.value)
        logger.info(
            "Lane %s reclamó historia %s (%s)", pick.lane_id, job["story_id"], mode
        )
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
            except Exception as exc:
                logger.debug("Failed cleaning run intermediates: %s", exc)

    if result is None:
        return {"status": "LANE_EMPTY", "lane": pick.lane_id, "channel": pick.channel.value}

    status_value = str(result.get("status", ""))
    if status_value in {"PUBLISHED", "COMPLETED", "RENDERED", "PENDING_REVIEW", "UPLOAD_UNCONFIRMED", "WAITING_YOUTUBE_LIMIT"}:
        scheduler_commit_fire(pick, run_id=job["run_id"] if job else None)
        breaker.record_success(pick.channel.value)
        breaker.record_success(pick.lane_id)
    else:
        scheduler_commit_empty(pick)
        if status_value in {"RETRYABLE_FAILED", "FAILED", "PERMANENT_FAILED", "WAITING_LLM_QUOTA"}:
            err_detail = result.get("error") or result.get("reason") or result.get("error_msg")
            _register_turn_failure(database, pick.channel.value, breaker, err_detail, lane_id=pick.lane_id)
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
    parallel = max(1, int(max_parallel or os.environ.get("YT_MAX_PARALLEL_LANES", "3")))
    if max_parallel is None and max_picks is not None:
        parallel = max(parallel, max_picks)
    lane_scheduler = LaneScheduler(database)
    lane_scheduler.initialize(apply_offsets=not is_test_environment())
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

    channel_set = {lane.channel for lane in active_lanes.values()}
    target_channel = list(channel_set)[0] if len(channel_set) == 1 else None

    if not is_test_environment():
        _startup_incident_check(database, interval_seconds, channel=target_channel)
        try:
            from src.core.lease_reaper import LeaseReaper
            LeaseReaper(db_path=database).reap_once(startup=True, channel=target_channel)
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
            logger.debug("daemon lane startup cleanup skipped", exc_info=True)
    if max_parallel is None and not is_test_environment():
        _start_telegram_callback_poller()
    breaker = ConsecutiveFailureBreaker()
    attempts = 0
    ticks = 0
    with ThreadPoolExecutor(max_workers=parallel, thread_name_prefix="lane") as pool:
        active_jobs: dict[Any, tuple[LanePick, float]] = {}
        from concurrent.futures import wait, FIRST_COMPLETED

        while not _SHUTDOWN_REQUESTED:
            _reap_zombies_safe()
            try:
                from src.core.lease_reaper import LeaseReaper
                LeaseReaper(db_path=database).reap_once(channel=target_channel)
            except Exception:
                pass
            if not is_test_environment():
                _run_auto_publish_sweep(channel=target_channel)
                if max_parallel is None and not _TELEGRAM_POLLER_STARTED:
                    _start_telegram_callback_poller()
                if ticks % 360 == 0:
                    try:
                        from src.cleaner import (
                            clean_expired_failed_runs,
                            clean_untracked_temp_files,
                            clean_tts_cache,
                        )
                        clean_expired_failed_runs()
                        clean_untracked_temp_files()
                        clean_tts_cache(max_size_bytes=500 * 1024 * 1024)
                    except Exception:
                        logger.debug("periodic background cleanup skipped", exc_info=True)
                if ticks % 60 == 0:
                    try:
                        _run_24h_maintenance_sweep(database, channel=target_channel)
                    except Exception:
                        logger.debug("periodic 24h maintenance sweep skipped", exc_info=True)
                try:
                    touch_daemon_liveness(database)
                except Exception:
                    logger.debug("daemon liveness touch failed", exc_info=True)

            # 1. Drain completed futures
            done_futs = [f for f in active_jobs if f.done()]
            for fut in done_futs:
                pick, _ = active_jobs.pop(fut)
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

            # 2. Watchdog: check for timed-out jobs
            turn_timeout = _turn_timeout_seconds()
            now_mono = time.monotonic()
            timed_out = [
                f for f, (p, s_time) in active_jobs.items()
                if now_mono - s_time >= turn_timeout
            ]
            for fut in timed_out:
                pick, _ = active_jobs.pop(fut)
                fut.cancel()
                if not is_test_environment():
                    try:
                        from src.core.process_watch import terminate_hung_ffmpeg
                        terminate_hung_ffmpeg(
                            max_age_seconds=0,
                            parent_pid=os.getpid(),
                            grace_seconds=1.0,
                        )
                    except Exception:
                        logger.debug("hung ffmpeg terminate failed", exc_info=True)
                results.append(_timeout_result(pick))

            # 3. Check tick bound
            if max_ticks is not None and ticks >= max_ticks:
                break
            ticks += 1

            # 4. Asynchronous dispatch: query due lanes and submit into available slots
            running_lane_ids = {p.lane_id for p, _ in active_jobs.values()}
            allowed_lanes = set(active_lanes) - running_lane_ids
            capacity = min(parallel, max_picks) if max_picks is not None else parallel
            available_slots = max(0, capacity - len(active_jobs))

            if available_slots > 0 and allowed_lanes:
                picks = lane_scheduler.take_due_lanes(
                    max_picks=available_slots,
                    lanes_filter=allowed_lanes,
                    exclude_lanes=running_lane_ids,
                )
                for pick in picks:
                    fut = pool.submit(
                        _execute_lane_pick, database, pick, breaker, generate_only
                    )
                    active_jobs[fut] = (pick, time.monotonic())
                    attempts += 1

            # 5. Responsive wait: wake on task completion or tick timeout
            if active_jobs:
                wait_step = min(5.0, _watchdog_tick_seconds())
                wait(active_jobs.keys(), timeout=wait_step, return_when=FIRST_COMPLETED)
            else:
                wait_time = min(
                    interval_seconds,
                    max(1, lane_scheduler.seconds_until_due(lanes_filter=set(active_lanes))),
                )
                if _responsive_sleep(wait_time):
                    break

        if active_jobs:
            results.extend(
                _collect_futures_responsive(
                    {f: p for f, (p, _) in active_jobs.items()},
                    timeout=_turn_timeout_seconds(),
                    database=database,
                    tick=_watchdog_tick_seconds(),
                    channel=target_channel,
                )
            )
            active_jobs.clear()

    return results


run_daemon_loop = start_daemon_lanes
