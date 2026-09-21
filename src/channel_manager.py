"""Persistent per-channel pause/resume controls backed by SQLite."""

from __future__ import annotations

from typing import Any, Dict, List

from src.config import DEFAULT_DB_PATH, get_channel_settings
from src.core.domain import canonical_channel
from src.core.repository import QueueRepository, connect, migrate_database
from src.log import get_logger
import json
import os

logger = get_logger("channel_manager")
STATUS_FILE = DEFAULT_DB_PATH


def get_channel_statuses(db_path: str = None) -> Dict[str, Any]:
    target_path = db_path if db_path is not None else STATUS_FILE
    if str(target_path).endswith(".json") and os.path.exists(target_path):
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data:
                    return data
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("No se pudo leer el archivo de estado JSON %s: %s", target_path, exc)
        from src.core.channel_profile import ChannelProfileRegistry

        fallback: Dict[str, Any] = {}
        for cid in ChannelProfileRegistry.list_active_channel_ids():
            try:
                name = ChannelProfileRegistry.get(cid).editorial.public_name
            except Exception:
                name = cid.capitalize()
            fallback[cid] = {"name": name, "status": "ACTIVE", "reason": None}
        return fallback

    def _safe_public_name(cid: str) -> str:
        try:
            return get_channel_settings(cid).public_name
        except Exception:
            try:
                from src.core.channel_profile import ChannelProfileRegistry
                return ChannelProfileRegistry.get_channel(cid).editorial.public_name
            except Exception:
                return cid.capitalize()

    migrate_database(target_path)
    with connect(target_path, read_only=True) as conn:
        rows = conn.execute(
            "SELECT channel, paused, reason, updated_at FROM channel_controls"
        ).fetchall()
    statuses = {
        str(row["channel"]): {
            "name": _safe_public_name(str(row["channel"])),
            "status": "SUSPENDED" if row["paused"] else "ACTIVE",
            "reason": row["reason"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    }
    from src.core.channel_profile import ChannelProfileRegistry

    for cid in ChannelProfileRegistry.list_active_channel_ids():
        if cid not in statuses:
            statuses[cid] = {
                "name": _safe_public_name(cid),
                "status": "ACTIVE",
                "reason": None,
                "updated_at": None,
            }
    return statuses


def get_active_channels(db_path: str = None) -> List[str]:
    target_path = db_path if db_path is not None else STATUS_FILE
    return [
        channel
        for channel, detail in get_channel_statuses(target_path).items()
        if isinstance(detail, dict) and detail.get("status") == "ACTIVE"
    ]


def suspend_channel(
    channel: str,
    reason: str,
    db_path: str = None,
) -> Dict[str, Any]:
    target_path = db_path if db_path is not None else STATUS_FILE
    try:
        key = canonical_channel(channel)
    except ValueError:
        return {}
    repository = QueueRepository(target_path)
    repository.initialize()
    repository.pause(key, reason)
    ch_key = key.value if hasattr(key, "value") else str(key)
    return get_channel_statuses(target_path).get(ch_key, {})


def activate_channel(
    channel: str,
    db_path: str = None,
) -> Dict[str, Any]:
    target_path = db_path if db_path is not None else STATUS_FILE
    try:
        key = canonical_channel(channel)
    except ValueError:
        return {}
    repository = QueueRepository(target_path)
    repository.initialize()
    repository.resume(key)
    ch_key = key.value if hasattr(key, "value") else str(key)
    return get_channel_statuses(target_path).get(ch_key, {})
