"""
src/cli/handlers/analytics.py - CLI Handlers for 24h maintenance sweep and underperforming prune.
"""
from __future__ import annotations

import argparse
import json

from src.analytics.pruner import execute_autonomous_prune
from src.analytics.scoring import get_top_performing_music_tracks, sync_and_score_channel_publications
from src.config import DEFAULT_DB_PATH
from src.daemon import _run_24h_maintenance_sweep
from src.log import get_logger

logger = get_logger("cli.analytics")


def handle_sweep_24h(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """CLI handler for 24h maintenance sweep."""
    channel = getattr(args, "channel", "all") or "all"
    db_path = getattr(args, "db_path", DEFAULT_DB_PATH) or DEFAULT_DB_PATH
    dry_run = not getattr(args, "live", False)
    force = getattr(args, "force", False)

    print(f"Executing 24h maintenance sweep (channel={channel}, dry_run={dry_run}, force={force})...")
    res = _run_24h_maintenance_sweep(db_path=db_path, channel=channel, dry_run=dry_run, force=force)
    print(json.dumps(res, indent=2, default=str))
    return 0 if res.get("ok") else 1


def handle_prune_underperforming(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """CLI handler for underperforming video pruning."""
    channel = getattr(args, "channel", "moku") or "moku"
    db_path = getattr(args, "db_path", DEFAULT_DB_PATH) or DEFAULT_DB_PATH
    dry_run = not getattr(args, "live", False)
    min_score = float(getattr(args, "min_score", 25.0))
    grace_hours = float(getattr(args, "grace_hours", 24.0))
    max_delete = int(getattr(args, "max_delete", 2))
    force = getattr(args, "force", False)

    print(
        f"Evaluating underperforming videos for prune (channel={channel}, min_score={min_score}, "
        f"grace_hours={grace_hours}, max_delete={max_delete}, dry_run={dry_run})..."
    )
    report = execute_autonomous_prune(
        channel=channel,
        db_path=db_path,
        dry_run=dry_run,
        force=force,
        min_score=min_score,
        grace_hours=grace_hours,
        max_delete=max_delete,
    )
    print(
        f"Prune Report: evaluated={report.evaluated_count}, pruned={report.pruned_count}, "
        f"skipped={report.skipped_count}, failed={report.failed_count}"
    )
    for it in report.items:
        print(f"  • {it.get('video_id', '?')}: {it.get('title', 'Untitled')} [{it.get('status', '?')}]")
    return 0 if report.failed_count == 0 else 1
