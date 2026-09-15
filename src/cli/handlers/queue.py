"""Handler for 'queue' subcommand, channel lifecycle control, and review sweeps."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from src.config import DEFAULT_DB_PATH
from src.core.repository import connect
from src.log import get_logger

logger = get_logger("cli.queue")


def list_queue(db_path: str = DEFAULT_DB_PATH, limit: int = 50) -> list[dict[str, Any]]:
    """Retrieve list of stories from the SQLite database queue."""
    stories: list[dict[str, Any]] = []
    if os.path.exists(db_path):
        try:
            with connect(db_path, read_only=True) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT story_id, title, status, created_at, updated_at, error_msg FROM stories ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
                for row in cursor.fetchall():
                    stories.append(dict(row))
        except Exception as e:
            logger.error(f"Error querying queue from {db_path}: {e}")

    return stories


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
        title_disp = (s["title"][:30] + "...") if len(s["title"]) > 30 else s["title"]
        print(f"{s['story_id']:<20} | {s['status']:<10} | {str(s.get('created_at', '')):<20} | {title_disp}")
        if s.get("error_msg"):
            print(f"  └ Error: {s['error_msg']}")


def handle_queue(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Manage queue stories, channel pause/resume states, and publication review sweeps."""
    action = (getattr(args, "action", None) or "list").lower()
    db_path = getattr(args, "db_path", DEFAULT_DB_PATH)

    if action == "sweep" or getattr(args, "check_approvals", False):
        from src.telegram import check_pending_approvals

        published = check_pending_approvals()
        print(f"Auto-publicación: {len(published)} vídeo(s) publicado(s) → {published}")
        return 0

    target_channel = getattr(args, "target_channel", None) or getattr(args, "channel", None)

    if action == "pause":
        if not target_channel:
            print("Error: Especifique el canal a pausar (ej. 'queue pause moku' o '-c moku')", file=sys.stderr)
            return 2
        from src.core.channel_profile import ChannelProfileRegistry
        from src.core.domain import canonical_channel
        from src.core.repository import QueueRepository

        try:
            ch = canonical_channel(target_channel)
        except (ValueError, KeyError):
            valid_str = ", ".join(repr(c) for c in ChannelProfileRegistry.list_active_channel_ids())
            msg = f"Canal desconocido o inválido: {target_channel!r}. Canales válidos: {valid_str}"
            if parser is not None:
                parser.error(msg)
            else:
                print(f"Error: {msg}", file=sys.stderr)
                return 2

        repository = QueueRepository(db_path)
        repository.initialize()
        repository.pause(ch, "pausa solicitada por terminal")
        ch_val = ch.value if hasattr(ch, "value") else str(ch)
        if getattr(args, "json", False):
            print(json.dumps({"channel": ch_val, "paused": True}, indent=2))
        else:
            print(f"Canal '{ch_val}' pausado.")
        return 0

    if action == "resume":
        if not target_channel:
            print("Error: Especifique el canal a reanudar (ej. 'queue resume moku' o '-c moku')", file=sys.stderr)
            return 2
        from src.core.channel_profile import ChannelProfileRegistry
        from src.core.domain import canonical_channel
        from src.core.repository import QueueRepository

        try:
            ch = canonical_channel(target_channel)
        except (ValueError, KeyError):
            valid_str = ", ".join(repr(c) for c in ChannelProfileRegistry.list_active_channel_ids())
            msg = f"Canal desconocido o inválido: {target_channel!r}. Canales válidos: {valid_str}"
            if parser is not None:
                parser.error(msg)
            else:
                print(f"Error: {msg}", file=sys.stderr)
                return 2

        repository = QueueRepository(db_path)
        repository.initialize()
        repository.resume(ch)
        ch_val = ch.value if hasattr(ch, "value") else str(ch)
        if getattr(args, "json", False):
            print(json.dumps({"channel": ch_val, "paused": False}, indent=2))
        else:
            print(f"Canal '{ch_val}' reanudado.")
        return 0

    if action == "activate":
        if not target_channel:
            print("Error: Especifique el canal a activar (ej. 'queue activate moku' o '-c moku')", file=sys.stderr)
            return 2
        from src.channel_manager import activate_channel
        from src.core.channel_profile import ChannelProfileRegistry

        try:
            res = activate_channel(target_channel)
        except (ValueError, KeyError):
            valid_str = ", ".join(repr(c) for c in ChannelProfileRegistry.list_active_channel_ids())
            msg = f"Canal desconocido o inválido: {target_channel!r}. Canales válidos: {valid_str}"
            if parser is not None:
                parser.error(msg)
            else:
                print(f"Error: {msg}", file=sys.stderr)
                return 2
        if getattr(args, "json", False):
            print(json.dumps({"channel": target_channel, "status": res}, indent=2))
        else:
            print(f"Channel '{target_channel}' status:", res)
        return 0

    # Default action: list
    limit = getattr(args, "limit", 50) or 50
    if getattr(args, "json", False):
        items = list_queue(db_path=db_path, limit=limit)
        print(json.dumps(items, ensure_ascii=False, indent=2, default=str))
    else:
        print_queue(db_path=db_path, limit=limit)
    return 0
