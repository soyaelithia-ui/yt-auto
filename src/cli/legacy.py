import os
import fcntl
import sqlite3
import shutil
from typing import Dict, Any, List
from src.config import DEFAULT_DB_PATH, LOCK_FILE_PATH
from src.log import get_logger

logger = get_logger("cli")


def _is_daemon_running() -> str:
    """Verifica si el daemon está corriendo mediante pgrep y los lockfiles correspondientes."""
    import subprocess
    try:
        res = subprocess.run(["pgrep", "-f", "main.py.*--(daemon|mass-produce)"], capture_output=True, text=True, timeout=5, shell=False)
        if res.stdout.strip():
            return "RUNNING"
    except (subprocess.SubprocessError, OSError) as exc:
        logger.debug("La verificación pgrep en _is_daemon_running falló: %s", exc)

    base_lock = LOCK_FILE_PATH
    lock_files = [
        base_lock,
        f"{base_lock}.all",
        f"{base_lock}.global",
        f"{base_lock}.terror",
        f"{base_lock}.soy_el_malo",
        "/tmp/youtube_automation.lock"
    ]
    for lock_file in lock_files:
        if not os.path.exists(lock_file):
            continue
        try:
            f = open(lock_file, "r")
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f, fcntl.LOCK_UN)
            finally:
                f.close()
        except (IOError, OSError):
            return "RUNNING"
    return "STOPPED"


from src.core.repository import connect

def cli_status(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Return system health, queue counts, processed counts, disk usage, and health logs."""
    counts = {"PENDING": 0, "PROCESSING": 0, "COMPLETED": 0, "FAILED": 0}
    recent_errors = []
    
    if os.path.exists(db_path):
        try:
            with connect(db_path, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT status, COUNT(*) FROM stories GROUP BY status")
                for status, cnt in cursor.fetchall():
                    if status in counts:
                        counts[status] = cnt

                cursor.execute("SELECT story_id, title, error_msg, updated_at FROM stories WHERE status = 'FAILED' ORDER BY updated_at DESC LIMIT 5")
                for row in cursor.fetchall():
                    recent_errors.append({
                        "story_id": row[0],
                        "title": row[1],
                        "error": row[2],
                        "timestamp": row[3]
                    })
        except Exception as e:
            logger.error(f"Error querying status database at {db_path}: {e}")

    try:
        total_space, used_space, free_space = shutil.disk_usage("/")
        disk_free_gb = round(free_space / (1024 ** 3), 2)
    except Exception as e:
        logger.error(f"Error checking disk usage: {e}")
        disk_free_gb = 0.0

    processed_count = counts["COMPLETED"] + counts["FAILED"]
    daemon_status = _is_daemon_running()

    # Observability: project-disk floor, daemon heartbeat age, log footprint.
    from src.config import BASE_DIR
    from src.core.repository import read_daemon_heartbeat

    import time as _time

    disk_floor_gb = 0.0
    for name in ("data", "work", "logs"):
        try:
            free = shutil.disk_usage(BASE_DIR / name).free
            disk_floor_gb = (
                free / (1024**3) if disk_floor_gb == 0.0 else min(disk_floor_gb, free / (1024**3))
            )
        except Exception:
            continue
    heartbeat_age: int | None = None
    try:
        beat = read_daemon_heartbeat(db_path)
        if beat:
            heartbeat_age = max(0, int(_time.time()) - int(beat))
    except Exception:
        heartbeat_age = None
    logs_mb = 0.0
    logs_dir = BASE_DIR / "logs"
    if logs_dir.is_dir():
        try:
            logs_mb = round(
                sum(f.stat().st_size for f in logs_dir.glob("*.log*") if f.is_file())
                / (1024**2),
                1,
            )
        except Exception:
            logs_mb = 0.0

    status_summary = {
        "queue": counts,
        "processed_count": processed_count,
        "disk_free_gb": disk_free_gb,
        "project_disk_min_free_gb": round(disk_floor_gb, 2),
        "daemon_status": daemon_status,
        "daemon_heartbeat_age_sec": heartbeat_age,
        "logs_mb": logs_mb,
        "health_logs": recent_errors
    }
    return status_summary


def list_queue(db_path: str = DEFAULT_DB_PATH, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve list of stories from the SQLite database queue."""
    stories = []
    if os.path.exists(db_path):
        try:
            with connect(db_path, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT story_id, title, status, created_at, updated_at, error_msg FROM stories ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
                for row in cursor.fetchall():
                    stories.append(dict(row))
        except Exception as e:
            logger.error(f"Error querying queue from {db_path}: {e}")

    return stories


def print_status(db_path: str = DEFAULT_DB_PATH) -> None:
    """Print system status summary to stdout."""
    st = cli_status(db_path)
    print("=== YouTube Automation System Status ===")
    print(f"Queue: Pending={st['queue']['PENDING']}, Processing={st['queue']['PROCESSING']}, Completed={st['queue']['COMPLETED']}, Failed={st['queue']['FAILED']}")
    print(f"Total Processed: {st['processed_count']}")
    print(f"VPS Disk Free: {st['disk_free_gb']} GB")
    print(f"Project Disk Min Free: {st.get('project_disk_min_free_gb', '?')} GB")
    heartbeat_age = st.get("daemon_heartbeat_age_sec")
    print(
        f"Daemon Health: {st['daemon_status']}"
        + (f" (último latido hace {heartbeat_age}s)" if heartbeat_age is not None else "")
    )
    print(f"Logs footprint: {st.get('logs_mb', 0)} MB")
    if st["health_logs"]:
        print("\n--- Recent Failures ---")
        for err in st["health_logs"]:
            print(f"[{err['timestamp']}] {err['story_id']} ('{err['title']}'): {err['error']}")


def print_queue(db_path: str = DEFAULT_DB_PATH, limit: int = 50) -> None:
    """Print queue table to stdout."""
    queue = list_queue(db_path, limit=limit)
    print("=== YouTube Automation Story Queue ===")
    if not queue:
        print("Queue is empty.")
        return
    print(f"{'STORY ID':<20} | {'STATUS':<10} | {'CREATED AT':<20} | TITLE")
    print("-" * 75)
    for s in queue:
        title_disp = (s['title'][:30] + '...') if len(s['title']) > 30 else s['title']
        print(f"{s['story_id']:<20} | {s['status']:<10} | {str(s.get('created_at', '')):<20} | {title_disp}")
        if s.get('error_msg'):
            print(f"  └ Error: {s['error_msg']}")


def _parse_since(value: str) -> str:
    """Translate a human window ('24h', '7d', '30m') into an ISO timestamp."""
    from datetime import datetime, timedelta, timezone

    raw = (value or "").strip().lower()
    multiplier = {"m": 60, "h": 3600, "d": 86400}
    seconds = 86400
    if raw:
        unit = raw[-1]
        if unit in multiplier:
            try:
                seconds = int(float(raw[:-1]) * multiplier[unit])
            except ValueError:
                seconds = 86400
        else:
            try:
                seconds = int(float(raw))
            except ValueError:
                seconds = 86400
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(0, seconds))
    return cutoff.isoformat(timespec="seconds")


def cli_errors(
    db_path: str = DEFAULT_DB_PATH,
    *,
    since: str = "24h",
    limit: int = 20,
    run_id: str | None = None,
    component: str | None = None,
    level: str | None = None,
) -> Dict[str, Any]:
    """Collect observability events + failed runs for triage."""
    from src.core.repository import QueueRepository

    repository = QueueRepository(db_path)
    events = repository.query_system_events(
        level=level,
        run_id=run_id,
        component=component,
        since_ts=None if run_id else _parse_since(since),
        limit=limit,
    )
    failed_runs = [] if run_id else repository.recent_failed_runs(limit=min(limit, 10))

    # Enrich JSON details for display
    for event in events:
        try:
            import json as _json

            event["details"] = _json.loads(event.pop("details_json", "") or "{}")
        except Exception:
            event["details"] = {}
    return {
        "events": events,
        "failed_runs": failed_runs,
        "since": None if run_id else _parse_since(since),
    }


def print_errors(
    db_path: str = DEFAULT_DB_PATH,
    *,
    since: str = "24h",
    limit: int = 20,
    run_id: str | None = None,
    component: str | None = None,
    level: str | None = None,
    as_json: bool = False,
) -> None:
    """Print the error triage report (human table or --json)."""
    import json

    report = cli_errors(
        db_path,
        since=since,
        limit=limit,
        run_id=run_id,
        component=component,
        level=level,
    )
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return
    print("=== YTAuto Error Triage ===")
    if report["failed_runs"]:
        print("\n--- Runs sin terminar limpio (recientes) ---")
        for row in report["failed_runs"]:
            print(
                f"[{row.get('started_at')}] {row.get('run_id', '?')[:12]} "
                f"canal={row.get('channel')} estado={row.get('status')} "
                f"código={row.get('error_code') or '-'}"
            )
    print("\n--- Eventos del tubo ---")
    if not report["events"]:
        print("(sin eventos en la ventana consultada)")
        return
    for event in report["events"]:
        print(
            f"[{event['ts']}] {event['level']:<7} {event['event_type']} "
            f"run={str(event.get('run_id') or '-')[:12]} "
            f"comp={event.get('component') or '-'} "
            f"código={event.get('error_code') or '-'}"
        )
        message = event.get("message")
        if message:
            print(f"    └ {str(message)[:220]}")
