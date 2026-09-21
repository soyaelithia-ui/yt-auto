#!/usr/bin/env python3
"""Cadence monitor for shorts (every 5m) and longform videos (every 30m).

Audits data/shorts_queue.db for recent completions, failures, in-flight jobs,
and measures compliance with the target publication rhythm.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_DIR / "data" / "shorts_queue.db"

# Cadence targets in seconds
SHORT_CADENCE_TARGET_SEC = 300   # 5 minutes
LONG_CADENCE_TARGET_SEC = 1800   # 30 minutes

# Tolerance window before warning (seconds)
SHORT_TOLERANCE_SEC = 420        # 7 minutes
LONG_TOLERANCE_SEC = 2400        # 40 minutes


def parse_iso(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    try:
        # Handle ISO strings like 2026-09-15T02:38:21+00:00 or 2026-09-15T02:38:21Z
        clean = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(clean)
    except Exception:
        return None


def get_cadence_metrics() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    now_epoch = time.time()

    if not DB_PATH.exists():
        return {
            "error": f"Base de datos no encontrada en {DB_PATH}",
            "timestamp": now.isoformat(),
        }

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    c = conn.cursor()

    # 1. Daemon Liveness
    daemon_healthy = False
    daemon_hb_diff = None
    row = c.execute("SELECT heartbeat_at FROM daemon_liveness WHERE id=1").fetchone()
    if row and row[0]:
        daemon_hb_diff = round(now_epoch - row[0], 1)
        daemon_healthy = daemon_hb_diff <= 120

    # 2. Last Completed Shorts
    shorts_query = """
        SELECT run_id, lane_id, channel, status, started_at, finished_at
        FROM runs
        WHERE lane_id LIKE '%short%' AND status IN ('PUBLISHED', 'DRIVE_BACKED_UP', 'COMPLETED', 'WAITING_YOUTUBE_LIMIT')
        ORDER BY finished_at DESC LIMIT 5
    """
    recent_shorts = []
    for r in c.execute(shorts_query).fetchall():
        fin = parse_iso(r[5])
        age_sec = (now - fin).total_seconds() if fin else None
        recent_shorts.append({
            "run_id": r[0],
            "lane_id": r[1],
            "channel": r[2],
            "status": r[3],
            "finished_at": r[5],
            "age_seconds": round(age_sec, 1) if age_sec is not None else None,
        })

    last_short = recent_shorts[0] if recent_shorts else None
    short_cadence_status = "UNKNOWN"
    if last_short and last_short["age_seconds"] is not None:
        if last_short["age_seconds"] <= SHORT_TOLERANCE_SEC:
            short_cadence_status = "ON_TRACK"
        else:
            short_cadence_status = "DELAYED"
    else:
        short_cadence_status = "NO_COMPLETIONS_FOUND"

    # 3. Last Completed Longform
    longs_query = """
        SELECT run_id, lane_id, channel, status, started_at, finished_at
        FROM runs
        WHERE lane_id LIKE '%long%' AND status IN ('PUBLISHED', 'DRIVE_BACKED_UP', 'COMPLETED', 'WAITING_YOUTUBE_LIMIT')
        ORDER BY finished_at DESC LIMIT 5
    """
    recent_longs = []
    for r in c.execute(longs_query).fetchall():
        fin = parse_iso(r[5])
        age_sec = (now - fin).total_seconds() if fin else None
        recent_longs.append({
            "run_id": r[0],
            "lane_id": r[1],
            "channel": r[2],
            "status": r[3],
            "finished_at": r[5],
            "age_seconds": round(age_sec, 1) if age_sec is not None else None,
        })

    last_long = recent_longs[0] if recent_longs else None
    long_cadence_status = "UNKNOWN"
    if last_long and last_long["age_seconds"] is not None:
        if last_long["age_seconds"] <= LONG_TOLERANCE_SEC:
            long_cadence_status = "ON_TRACK"
        else:
            long_cadence_status = "DELAYED"
    else:
        long_cadence_status = "NO_COMPLETIONS_YET"

    # 4. In-flight Runs
    inflight_query = """
        SELECT run_id, lane_id, channel, status, started_at
        FROM runs
        WHERE finished_at IS NULL AND status IN ('PROCESSING', 'RENDERED', 'DRIVE_BACKED_UP')
        ORDER BY started_at ASC
    """
    inflight = []
    for r in c.execute(inflight_query).fetchall():
        st = parse_iso(r[4])
        running_sec = (now - st).total_seconds() if st else None
        inflight.append({
            "run_id": r[0],
            "lane_id": r[1],
            "channel": r[2],
            "status": r[3],
            "started_at": r[4],
            "running_seconds": round(running_sec, 1) if running_sec is not None else None,
        })

    # 5. Recent Failures (last 30 minutes)
    failures_query = """
        SELECT run_id, lane_id, channel, status, started_at, finished_at, error_detail
        FROM runs
        WHERE status LIKE '%FAIL%'
        ORDER BY started_at DESC LIMIT 5
    """
    recent_failures = []
    for r in c.execute(failures_query).fetchall():
        st = parse_iso(r[4])
        age_sec = (now - st).total_seconds() if st else None
        recent_failures.append({
            "run_id": r[0],
            "lane_id": r[1],
            "channel": r[2],
            "status": r[3],
            "started_at": r[4],
            "finished_at": r[5],
            "age_seconds": round(age_sec, 1) if age_sec is not None else None,
            "error_detail": r[6],
        })

    conn.close()

    return {
        "timestamp_utc": now.isoformat(),
        "daemon": {
            "healthy": daemon_healthy,
            "last_heartbeat_seconds_ago": daemon_hb_diff,
        },
        "shorts": {
            "target_cadence_minutes": 5,
            "status": short_cadence_status,
            "last_completed": last_short,
            "history_count": len(recent_shorts),
        },
        "long_videos": {
            "target_cadence_minutes": 30,
            "status": long_cadence_status,
            "last_completed": last_long,
            "history_count": len(recent_longs),
        },
        "in_flight": inflight,
        "recent_failures": recent_failures,
    }


def print_report(metrics: dict[str, Any]) -> None:
    print("=" * 70)
    print("  AUDITORÍA DE CADENCIA DE GENERACIÓN (SHORTS 5M / LARGOS 30M)")
    print("=" * 70)
    print(f"Timestamp UTC: {metrics.get('timestamp_utc')}")
    
    daemon = metrics.get("daemon", {})
    dh = "OK" if daemon.get("healthy") else "CRÍTICO/INACTIVO"
    print(f"Daemon Liveness: {dh} (último latido hace {daemon.get('last_heartbeat_seconds_ago')}s)")
    print("-" * 70)

    shorts = metrics.get("shorts", {})
    last_s = shorts.get("last_completed")
    print(f"SHORTS (Meta: cada 5m): Estado = [{shorts.get('status')}]")
    if last_s:
        print(f"  Último Short completado: {last_s['run_id'][:12]} ({last_s['lane_id']})")
        print(f"  Finalizado hace: {last_s['age_seconds']}s (~{last_s['age_seconds']/60:.1f} min)")
        print(f"  Timestamp: {last_s['finished_at']}")
    else:
        print("  Ningún short completado registrado.")

    print("-" * 70)
    longs = metrics.get("long_videos", {})
    last_l = longs.get("last_completed")
    print(f"VIDEOS LARGOS (Meta: cada 30m): Estado = [{longs.get('status')}]")
    if last_l:
        print(f"  Último Video Largo: {last_l['run_id'][:12]} ({last_l['lane_id']})")
        print(f"  Finalizado hace: {last_l['age_seconds']}s (~{last_l['age_seconds']/60:.1f} min)")
        print(f"  Timestamp: {last_l['finished_at']}")
    else:
        print("  Ningún video largo completado previamente en esta sesión.")

    inflight = metrics.get("in_flight", [])
    print("-" * 70)
    print(f"PROCESOS EN CURSO (IN-FLIGHT): {len(inflight)}")
    for inf in inflight:
        print(f"  - [{inf['lane_id']}] Run {inf['run_id'][:12]} iniciado hace {inf['running_seconds']}s (~{inf['running_seconds']/60:.1f} min)")

    failures = metrics.get("recent_failures", [])
    if failures:
        print("-" * 70)
        print(f"FALLOS RECIENTES DETECTADOS ({len(failures)}):")
        for f in failures[:3]:
            print(f"  - [{f['lane_id']}] {f['run_id'][:12]}: {f['error_detail']}")
    print("=" * 70)


if __name__ == "__main__":
    metrics = get_cadence_metrics()
    if "--json" in sys.argv or "-j" in sys.argv:
        print(json.dumps(metrics, indent=2))
    else:
        print_report(metrics)
