"""Handler for 'status' subcommand, API diagnostics, error triage, and QA checks."""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import shutil
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any

from src.api_health import check_all, format_status_report
from src.config import BASE_DIR, DEFAULT_DB_PATH, LOCK_FILE_PATH
from src.core.repository import connect, read_daemon_heartbeat

logger = logging.getLogger("cli.status")


def _is_daemon_running() -> str:
    """Verifica si el daemon está corriendo mediante pgrep y los lockfiles correspondientes."""
    import subprocess

    try:
        res = subprocess.run(
            ["pgrep", "-f", r"main\.py\s+(--)?(daemon|mass-produce)"],
            capture_output=True,
            text=True,
            timeout=5,
            shell=False,
        )
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
        "/tmp/youtube_automation.lock",
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


def _parse_since(value: str) -> str:
    """Translate a human window ('24h', '7d', '30m') into an ISO timestamp."""
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


def cli_status(db_path: str = DEFAULT_DB_PATH) -> dict[str, Any]:
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

                cursor.execute(
                    "SELECT story_id, title, error_msg, updated_at FROM stories WHERE status = 'FAILED' ORDER BY updated_at DESC LIMIT 5"
                )
                for row in cursor.fetchall():
                    recent_errors.append(
                        {
                            "story_id": row[0],
                            "title": row[1],
                            "error": row[2],
                            "timestamp": row[3],
                        }
                    )
        except Exception as e:
            logger.error(f"Error querying status database at {db_path}: {e}")

    try:
        total_space, used_space, free_space = shutil.disk_usage("/")
        disk_free_gb = round(free_space / (1024**3), 2)
    except Exception as e:
        logger.error(f"Error checking disk usage: {e}")
        disk_free_gb = 0.0

    processed_count = counts["COMPLETED"] + counts["FAILED"]
    daemon_status = _is_daemon_running()

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

    return {
        "queue": counts,
        "processed_count": processed_count,
        "disk_free_gb": disk_free_gb,
        "project_disk_min_free_gb": round(disk_floor_gb, 2),
        "daemon_status": daemon_status,
        "daemon_heartbeat_age_sec": heartbeat_age,
        "logs_mb": logs_mb,
        "health_logs": recent_errors,
    }


def print_status(db_path: str = DEFAULT_DB_PATH) -> None:
    """Print system status summary to stdout."""
    st = cli_status(db_path)
    print("=== YouTube Automation System Status ===")
    print(
        f"Queue: Pending={st['queue']['PENDING']}, Processing={st['queue']['PROCESSING']}, Completed={st['queue']['COMPLETED']}, Failed={st['queue']['FAILED']}"
    )
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


def cli_errors(
    db_path: str = DEFAULT_DB_PATH,
    *,
    since: str = "24h",
    limit: int = 20,
    run_id: str | None = None,
    component: str | None = None,
    level: str | None = None,
) -> dict[str, Any]:
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

    for event in events:
        try:
            event["details"] = json.loads(event.pop("details_json", "") or "{}")
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


def handle_status(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Display system health, queue counts, external API status, error logs, or video QA."""
    db_path = getattr(args, "db_path", DEFAULT_DB_PATH)

    if getattr(args, "apis", False) or getattr(args, "check_apis", False):
        ch = "horror" if getattr(args, "channel", "all") in ("all", None) else args.channel
        report = check_all(ch)
        print(format_status_report(report, ch))
        return 0

    if getattr(args, "check_pub", False) or getattr(args, "check_publication", False):
        from src.monitor import run_publication_check

        res = run_publication_check()
        print("Publication Check Result:")
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0

    if getattr(args, "errors", False):
        print_errors(
            db_path=db_path,
            since=getattr(args, "since", "24h"),
            limit=getattr(args, "limit", 20),
            component=getattr(args, "component", None),
            level=getattr(args, "level", None),
            as_json=getattr(args, "json", False),
        )
        return 0

    if getattr(args, "agent_review", None):
        from src.agents.video_qa import run_video_qa

        report = run_video_qa(args.agent_review, db_path=db_path)
        if getattr(args, "json", False):
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            icon = "✅" if report.get("overall_pass") else "⚠️"
            print(
                f"{icon} Video QA {report['run_id']}: pass={report.get('overall_pass')} hallazgos={len(report.get('findings', []))}"
            )
            for finding in report.get("findings", []):
                print(
                    f"  - [{finding.get('severity')}/{finding.get('category')}] "
                    f"{finding.get('description')} → {finding.get('suggested_fix', '-')}"
                )
            print(f"Bundle: {report.get('bundle_dir')}")
        return 0

    if getattr(args, "tube", False):
        if not getattr(args, "json", False):
            print_status(db_path=db_path)
            print("\n" + "=" * 60 + "\n")
        return cli_tube(args)

    if getattr(args, "json", False):
        st = cli_status(db_path=db_path)
        print(json.dumps(st, ensure_ascii=False, indent=2, default=str))
    else:
        print_status(db_path=db_path)
    return 0


def print_tube(
    snapshot: Any,
    channel: str | None = None,
    json_output: bool = False,
) -> None:
    """Render ANSI dashboard or structured JSON for El Tubo operational telemetry."""
    if json_output:
        print(json.dumps(snapshot.to_dict(), indent=2, ensure_ascii=False, default=str))
        return

    # ANSI styles
    BOLD = "\033[1m"
    RESET = "\033[0m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    CYAN = "\033[36m"

    status_color = {
        "HEALTHY": GREEN,
        "OK": GREEN,
        "SYNCED": GREEN,
        "DEGRADED": YELLOW,
        "WARNING": YELLOW,
        "GROWTH_WARNING": YELLOW,
        "BACKUP_STALE_WARNING": YELLOW,
        "CRITICAL": RED,
        "EXHAUSTED": RED,
        "CRITICAL_WAL_BLOAT": RED,
        "PENDING_MIGRATIONS": RED,
        "BROKEN": RED,
        "CORRUPTED": RED,
        "STOPPED": RED,
        "STALE": YELLOW,
    }

    def badge(st: str) -> str:
        c = status_color.get(str(st).upper(), RESET)
        return f"{c}{BOLD}[{st}]{RESET}"

    ch_label = f" — Canal: {channel}" if channel else ""
    print(f"\n{BOLD}{CYAN}=== EL TUBO — OBSERVABILIDAD DEL PIPELINE{ch_label} ==={RESET}")
    print(f"Timestamp: {snapshot.timestamp}  |  Estado Global: {badge(snapshot.system_status)}\n")

    # 1. System Gauges
    hr = snapshot.host_resources
    cpu_bar = f"{hr.cpu_percent:.1f}%"
    ram_bar = f"{hr.ram_rss_mib:.1f} MiB / 2048 MiB ({hr.ram_status})"
    disk_bar = f"{hr.disk_free_gib:.2f} GiB libres (min: 2.0 GiB) ({hr.disk_status})"
    print(f"{BOLD}📊 SECCIÓN 1: GAUGES DEL SISTEMA{RESET}")
    print(f"  • CPU:  {cpu_bar} ({badge(hr.overall_status)})")
    print(f"  • RAM:  {ram_bar}")
    print(f"  • DISK: {disk_bar}")
    print(f"  • Muestreo: {hr.sampling_duration_ms:.2f} ms\n")

    # 2. Daemon & Concurrency
    ds = snapshot.daemon_stoppages
    hb_str = f"{ds.heartbeat_age_seconds}s atrás" if ds.heartbeat_age_seconds is not None else "Sin latido"
    print(f"{BOLD}🔄 SECCIÓN 2: DAEMON Y CONCURRENCIA{RESET}")
    print(f"  • Liveness: {hb_str} ({badge(ds.daemon_liveness_status)})")
    print(f"  • Locks activos: {len(ds.active_locks)} (Expirados: {ds.expired_locks_count})")
    print(f"  • Canales pausados: {len(ds.paused_channels)}")
    for pc in ds.paused_channels:
        print(f"    - {pc['channel']}: {pc.get('reason', '-')}")
    print()

    # 3. Token Burn & USD Costs
    tb = snapshot.token_burn
    print(f"{BOLD}🔥 SECCIÓN 3: CONSUMO DE TOKENS (TOKEN BURN){RESET}")
    print(f"  • Ventana: {tb.window_hours}h  |  Total Llamadas: {tb.total_calls}  |  Saturaciones: {tb.total_saturations}")
    print(f"  • Tokens: {tb.total_tokens:,} (Prompt: {tb.total_prompt_tokens:,}, Compl: {tb.total_completion_tokens:,}, Cached: {tb.total_cached_tokens:,})")
    print(f"  • Costo Estimado: ${tb.total_cost_usd:.4f} USD")
    if tb.provider_breakdown:
        print("  • Desglose por Proveedor:")
        for prov, pdata in tb.provider_breakdown.items():
            print(f"    - {prov}: {pdata.get('total_tokens', 0):,} tokens (${pdata.get('total_cost_usd', 0.0):.4f}) [{pdata.get('calls', 0)} llamadas]")
    print()

    # 4. YouTube Quotas
    yt = snapshot.youtube_quotas
    print(f"{BOLD}📹 SECCIÓN 4: CUOTAS YOUTUBE DATA API V3{RESET}")
    print(f"  • Unidades Usadas: {yt.estimated_consumed_units:,} / {yt.daily_budget_units:,} ({badge(yt.quota_status)})")
    print(f"  • Unidades Restantes: {yt.remaining_quota_units:,} (~{yt.estimated_remaining_uploads} videos restantes)")
    print(f"  • Próximo reinicio (08:00 UTC): {yt.quota_cycle_reset_utc}")
    print(f"  • Borradores en cola: {yt.staged_drafts_count}  |  No listados: {yt.staged_unlisted_count}  |  No confirmados: {yt.unconfirmed_uploads_count}")
    if yt.channel_daily_uploads:
        print("  • Subidas en ciclo actual:")
        for ch_name, u_cnt in yt.channel_daily_uploads.items():
            print(f"    - {ch_name}: {u_cnt} videos")
    print()

    # 5. Security & Database Health
    dh = snapshot.database_health
    pl = snapshot.prompt_leaks
    ck = snapshot.cookie_health
    mh = snapshot.mcp_health
    print(f"{BOLD}🛡️ SECCIÓN 5: SEGURIDAD Y SALUD OPERACIONAL{RESET}")
    print(f"  • Base de datos SQLite: {dh.db_size_mib:.2f} MiB  |  WAL: {dh.wal_size_mib:.2f} MiB ({badge(dh.wal_status)})")
    print(f"  • Migraciones: v{dh.applied_migration_version} / v{dh.expected_migration_version} ({badge(dh.migration_status)})")
    print(f"  • Último Backup: {dh.last_backup_timestamp or 'Nunca'} ({badge(dh.backup_status)})")
    print(f"  • MCP Server: {badge(mh.overall_status)} ({mh.status_reason})")
    print(f"  • Cookies de Sesión: {len(ck.degraded_channels)} canales degradados (Warnings: {ck.recent_warnings_count}, Fallos: {ck.recent_failures_count})")
    print(f"  • Fugas de Prompt (Pre-TTS): {pl.total_leaks} detectadas (Alerta Cluster Activa: {pl.alert_cluster_active})")
    print()

    # 6. Incidents Timeline
    print(f"{BOLD}⚠️ SECCIÓN 6: LÍNEA DE TIEMPO DE INCIDENTES RECIENTES{RESET}")
    if not snapshot.recent_incidents:
        print("  (Sin incidentes en la ventana consultada)")
    else:
        for inc in snapshot.recent_incidents[:10]:
            print(f"  [{inc.get('ts')}] {inc.get('level', 'INFO'):<7} {inc.get('event_type')} ch={inc.get('channel') or '-'}: {str(inc.get('message', ''))[:120]}")
    print()


def cli_tube(args: argparse.Namespace) -> int:
    """Handle tube subcommand: query TubeCollector and render dashboard or JSON."""
    db_path = getattr(args, "db_path", DEFAULT_DB_PATH)
    channel = getattr(args, "channel", None)
    if channel in ("all", ""):
        channel = None
    window_hours = getattr(args, "window", 24) or 24
    json_mode = getattr(args, "json", False)

    from src.core.repository import QueueRepository
    from src.observability.tube import TubeCollector

    if getattr(args, "prune", False):
        deleted = QueueRepository(db_path).prune_token_burn_events(retention_days=30)
        if not json_mode:
            print(f"🧹 Purgados {deleted} registros de consumo de tokens (>30 días)")

    collector = TubeCollector(db_path=db_path)
    snapshot = collector.compile_snapshot(channel=channel, window_hours=window_hours)

    print_tube(snapshot, channel=channel, json_output=json_mode)
    return 0


def handle_tube(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """CLI dispatcher entry point for tube."""
    return cli_tube(args)

