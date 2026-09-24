"""Handler for 'inventory' subcommand and AI-native published video management."""
from __future__ import annotations

import argparse
import json
import sys

from src.config import DEFAULT_DB_PATH
from src.core.inventory import (
    backup_inventory_to_drive,
    get_inventory_ai_digest,
    get_published_inventory,
    sync_all_channel_publications,
    sync_channel_publications_from_youtube,
)


def handle_inventory(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Dispatch inventory actions (list, sync, backup, digest)."""
    action = getattr(args, "inventory_action", "list") or "list"
    db_path = getattr(args, "db_path", DEFAULT_DB_PATH)
    channel = getattr(args, "channel", None)
    if channel == "all":
        channel = None
    limit = int(getattr(args, "limit", 50) or 50)
    as_json = getattr(args, "json", False)

    if action == "list":
        records = get_published_inventory(db_path=db_path, channel=channel, limit=limit)
        if as_json:
            print(json.dumps([r.to_dict() for r in records], indent=2, ensure_ascii=False))
        else:
            print(f"=== INVENTARIO DE VIDEOS PUBLICADOS ({len(records)} encontrados) ===")
            for r in records:
                print(f"[{r.channel}] {r.video_id} | {r.verified_at[:10]} | {r.title}")
                print(f"   Puntuación: {r.actual_success_score:.1f}/100 | Vistas: {r.view_count} | Likes: {r.like_count} | Comentarios: {r.comment_count}")
                if r.hook_summary:
                    print(f"   Hook: {r.hook_summary}")
                if r.themes:
                    print(f"   Themes: {', '.join(r.themes[:6])}")
                print(f"   URL: {r.url}")
        return 0

    elif action == "digest":
        digest = get_inventory_ai_digest(db_path=db_path, channel=channel, limit=limit)
        if as_json:
            print(json.dumps(digest, indent=2, ensure_ascii=False))
        else:
            print(f"=== DIGEST DE INVENTARIO PARA AGENTES IA (Canal: {digest['channel_scope']}) ===")
            print(f"Total en catálogo: {digest['total_catalog_count']}")
            print(json.dumps(digest["recent_publications"], indent=2, ensure_ascii=False))
        return 0

    elif action == "sync":
        if channel:
            result = sync_channel_publications_from_youtube(channel, db_path=db_path, max_items=limit)
        else:
            result = sync_all_channel_publications(db_path=db_path, max_items_per_channel=limit)

        if as_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("=== SINCRONIZACIÓN DE VIDEOS DESDE YOUTUBE COMPLETADA ===")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok", True) else 1

    elif action == "backup":
        folder_id = getattr(args, "folder_id", None)
        try:
            result = backup_inventory_to_drive(db_path=db_path, folder_id=folder_id)
            if as_json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print("=== RESPALDO DE INVENTARIO A GOOGLE DRIVE EXITOSO ===")
                print(f"Database File ID: {result['database_backup']['file_id']}")
                print(f"Database Size: {result['database_backup']['size_bytes']} bytes")
                print(f"Digest File ID: {result['digest_backup']['file_id']}")
                print(f"Digest Size: {result['digest_backup']['size_bytes']} bytes")
            return 0
        except Exception as exc:
            print(f"ERROR al respaldar a Google Drive: {exc}", file=sys.stderr)
            return 1

    else:
        print(f"Acción de inventario desconocida: {action}", file=sys.stderr)
        return 2
