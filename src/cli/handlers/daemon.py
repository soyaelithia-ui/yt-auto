"""Handler for 'daemon' subcommand and persistent multi-channel scheduler."""
from __future__ import annotations

import argparse
import sys

from src.config import DEFAULT_DB_PATH


def _get_locks():
    main_mod = sys.modules.get("main")
    if main_mod is not None:
        acq = getattr(main_mod, "acquire_lock", None)
        rel = getattr(main_mod, "release_lock", None)
        if acq is not None and rel is not None:
            return acq, rel
    from src.core.lock import acquire_lock, release_lock

    return acquire_lock, release_lock


def _get_orchestrator_cls():
    import src.orchestrator as orch_mod

    return orch_mod.PipelineOrchestrator


def handle_daemon(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Start the persistent multi-lane production daemon."""
    channel = getattr(args, "channel", "all") or "all"
    acquire_lock, release_lock = _get_locks()
    PipelineOrchestrator = _get_orchestrator_cls()

    acquire_lock(channel)
    try:
        interval = getattr(args, "interval", 60)
        lanes_raw = getattr(args, "lanes", None)
        lanes_filter = (
            [lane.strip() for lane in str(lanes_raw).split(",") if lane.strip()]
            if lanes_raw
            else None
        )
        print(
            f"Starting multi-lane daemon (poll={interval}s, channel={channel}, "
            f"lanes={lanes_filter or 'todos'}); cadence per lane from config/lanes.json..."
        )
        db_path = getattr(args, "db_path", DEFAULT_DB_PATH)
        orchestrator = PipelineOrchestrator(db_path=db_path)
        orchestrator.run_daemon(
            interval=interval,
            channel=channel,
            lanes_filter=lanes_filter,
        )
        return 0
    finally:
        release_lock(channel)
