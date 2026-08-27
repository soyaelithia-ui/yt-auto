"""Handler for 'queue' subcommand, channel lifecycle control, and review sweeps."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from src.config import DEFAULT_DB_PATH


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
        from src.core.domain import canonical_channel
        from src.core.repository import QueueRepository

        try:
            ch = canonical_channel(target_channel)
        except (ValueError, KeyError):
            msg = f"Canal desconocido o inválido: {target_channel!r}. Canales válidos: 'moku', 'aelithia'"
            if parser is not None:
                parser.error(msg)
            else:
                print(f"Error: {msg}", file=sys.stderr)
                return 2

        repository = QueueRepository(db_path)
        repository.initialize()
        repository.pause(ch, "pausa solicitada por terminal")
        if getattr(args, "json", False):
            print(json.dumps({"channel": ch.value, "paused": True}, indent=2))
        else:
            print(f"Canal '{ch.value}' pausado.")
        return 0

    if action == "resume":
        if not target_channel:
            print("Error: Especifique el canal a reanudar (ej. 'queue resume moku' o '-c moku')", file=sys.stderr)
            return 2
        from src.core.domain import canonical_channel
        from src.core.repository import QueueRepository

        try:
            ch = canonical_channel(target_channel)
        except (ValueError, KeyError):
            msg = f"Canal desconocido o inválido: {target_channel!r}. Canales válidos: 'moku', 'aelithia'"
            if parser is not None:
                parser.error(msg)
            else:
                print(f"Error: {msg}", file=sys.stderr)
                return 2

        repository = QueueRepository(db_path)
        repository.initialize()
        repository.resume(ch)
        if getattr(args, "json", False):
            print(json.dumps({"channel": ch.value, "paused": False}, indent=2))
        else:
            print(f"Canal '{ch.value}' reanudado.")
        return 0

    if action == "activate":
        if not target_channel:
            print("Error: Especifique el canal a activar (ej. 'queue activate moku' o '-c moku')", file=sys.stderr)
            return 2
        from src.channel_manager import activate_channel

        try:
            res = activate_channel(target_channel)
        except (ValueError, KeyError):
            msg = f"Canal desconocido o inválido: {target_channel!r}. Canales válidos: 'moku', 'aelithia'"
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
        from src.cli.legacy import list_queue

        items = list_queue(db_path=db_path, limit=limit)
        print(json.dumps(items, ensure_ascii=False, indent=2, default=str))
    else:
        from src.cli.legacy import print_queue

        print_queue(db_path=db_path, limit=limit)
    return 0
