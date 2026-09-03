"""Handler for 'profile' and 'benchmark' subcommands (Requirement R1)."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from src.config import DEFAULT_DB_PATH
from src.core.profiling import PipelineProfiler, run_benchmark_cycle

logger = logging.getLogger("cli.profile")


def handle_profile(
    args: argparse.Namespace, parser: argparse.ArgumentParser | None = None
) -> int:
    """Execute benchmarking runs or display historical stage profiling metrics."""
    raw_db_path = getattr(args, "db_path", None)
    if isinstance(raw_db_path, (str, Path)):
        db_path = str(raw_db_path)
    else:
        db_path = DEFAULT_DB_PATH

    if getattr(args, "history", False):
        return _display_profiling_history(
            db_path=str(db_path),
            since=getattr(args, "since", "24h"),
            channel=getattr(args, "channel", "all"),
            as_json=getattr(args, "json", False),
        )

    iterations = getattr(args, "iterations", 1)
    channel = getattr(args, "channel", "moku")
    if channel == "all":
        channel = "moku"
    lane_id = getattr(args, "lane", None)
    mock_mode = getattr(args, "mock", True)
    export_path = getattr(args, "export_json", None) or getattr(args, "output", None)
    stages = getattr(args, "stages", None)
    as_json = getattr(args, "json", False)

    logger.info(
        "Iniciando benchmarking de profiling: %d ciclo(s), canal=%s, mock=%s",
        iterations,
        channel,
        mock_mode,
    )

    summaries = run_benchmark_cycle(
        channel=channel,
        lane_id=lane_id,
        iterations=iterations,
        mock_mode=mock_mode,
        stages=stages,
        db_path=str(db_path),
    )

    if not summaries:
        print("[!] No se generaron resultados de profiling.")
        return 1

    if not isinstance(summaries, list):
        summaries = [summaries]

    last_summary = summaries[-1]
    if as_json:
        payload: dict[str, Any] = {
            "iterations": iterations,
            "channel": channel,
            "mock_mode": mock_mode,
            "summaries": [s.to_dict() for s in summaries],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(last_summary.format_table())

    if export_path and isinstance(export_path, (str, Path)):
        export_data = {
            "iterations": iterations,
            "channel": channel,
            "mock_mode": mock_mode,
            "summaries": [s.to_dict() for s in summaries],
        }
        p = Path(export_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(export_data, indent=2, ensure_ascii=False), encoding="utf-8")
        if not as_json:
            print(f"[+] Reporte exportado a {export_path}")

    return 0


def _display_profiling_history(
    db_path: str, since: str = "24h", channel: str = "all", as_json: bool = False
) -> int:
    """Query and display historical profiling events from SQLite."""
    try:
        from src.core.repository import connect

        with connect(db_path, read_only=True) as conn:
            query = """
                SELECT event_id, event_type, run_id, story_id, channel, details_json
                FROM system_events
                WHERE event_type IN ('PIPELINE_PROFILED', 'PROFILING_PIPELINE_SUMMARY')
            """
            params: list[Any] = []
            if channel and channel != "all":
                query += " AND channel = ?"
                params.append(channel)
            query += " ORDER BY event_id DESC LIMIT 20"
            rows = conn.execute(query, params).fetchall()
    except Exception as exc:
        logger.debug("Failed to query profiling history: %s", exc)
        rows = []

    if as_json:
        data: list[dict[str, Any]] = []
        for r in rows:
            row_dict = dict(r)
            if isinstance(row_dict.get("details_json"), str):
                try:
                    row_dict["details"] = json.loads(row_dict["details_json"])
                except Exception:
                    row_dict["details"] = row_dict["details_json"]
            data.append(row_dict)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    print(f"=== HISTÓRICO DE PROFILING ({len(rows)} ejecuciones recientes) ===")
    if not rows:
        print("  (Sin registros de profiling previos en system_events)")
        return 0

    for r in rows:
        row_dict = dict(r)
        details: dict[str, Any] = {}
        if row_dict.get("details_json"):
            try:
                details = json.loads(row_dict["details_json"])
            except Exception:
                pass
        dur = details.get("total_duration_sec", 0.0)
        peak_rss = details.get("peak_rss_mb", 0.0)
        phases = details.get("phases_count", len(details.get("phase_breakdown", [])))
        ts_val = row_dict.get("ts") or row_dict.get("created_at") or "N/A"
        print(
            f"[{ts_val}] Run: {row_dict.get('run_id') or 'N/A'} | "
            f"Canal: {row_dict.get('channel') or 'N/A'} | "
            f"Duración: {dur:.2f}s | "
            f"Peak RSS: {peak_rss:.1f}MB | "
            f"Fases: {phases}"
        )

    return 0
