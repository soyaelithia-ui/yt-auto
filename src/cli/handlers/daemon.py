"""Handler for 'daemon' subcommand and persistent multi-lane scheduler."""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Set

from src.config import DEFAULT_DB_PATH
from src.core.contracts.daemon import LaneDaemonConfig
from src.orchestrator.scheduler import LaneDaemonOrchestrator


def _get_locks():
    main_mod = sys.modules.get("main")
    if main_mod is not None:
        acq = getattr(main_mod, "acquire_lock", None)
        rel = getattr(main_mod, "release_lock", None)
        if acq is not None and rel is not None:
            return acq, rel
    from src.core.lock import acquire_lock, release_lock

    return acquire_lock, release_lock


def handle_daemon(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Start the persistent multi-lane production daemon."""
    channel = getattr(args, "channel", "all") or "all"
    acquire_lock, release_lock = _get_locks()

    acquire_lock(channel)
    try:
        interval = int(getattr(args, "interval", 60) or 60)
        lanes_raw = getattr(args, "lanes", None)
        lanes_filter: Optional[Set[str]] = (
            {lane.strip() for lane in str(lanes_raw).split(",") if lane.strip()}
            if lanes_raw
            else None
        )
        max_parallel_val = getattr(args, "max_parallel", None)
        max_parallel = int(max_parallel_val) if max_parallel_val is not None else 3
        generate_only = bool(getattr(args, "generate_only", False))
        db_path = getattr(args, "db_path", DEFAULT_DB_PATH) or DEFAULT_DB_PATH

        print(
            f"Starting multi-lane daemon (poll={interval}s, channel={channel}, "
            f"lanes={lanes_filter or 'todos'}); cadence per lane from config/lanes.json..."
        )

        config = LaneDaemonConfig(
            db_path=db_path,
            interval_seconds=interval,
            lanes_filter=lanes_filter,
            max_parallel=max_parallel,
            generate_only=generate_only,
        )
        orchestrator = LaneDaemonOrchestrator(config)
        orchestrator.run_loop()
        return 0
    finally:
        release_lock(channel)
