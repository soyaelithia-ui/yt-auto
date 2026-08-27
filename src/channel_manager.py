"""Persistent per-channel pause/resume controls backed by SQLite."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from src.config import DEFAULT_DB_PATH, get_channel_settings
from src.core.domain import CanonicalChannel, canonical_channel
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
        return {
            "terror": {"name": "Historias de Terror", "status": "ACTIVE", "reason": None},
            "moku": {"name": "Historias de Terror", "status": "ACTIVE", "reason": None},
            "aelithia": {"name": "Aelithia", "status": "ACTIVE", "reason": None},
            "soy_el_malo": {"name": "Aelithia", "status": "ACTIVE", "reason": None},
        }

    migrate_database(target_path)
    with connect(target_path, read_only=True) as conn:
        rows = conn.execute(
            "SELECT channel, paused, reason, updated_at FROM channel_controls"
        ).fetchall()
    return {
        str(row["channel"]): {
            "name": get_channel_settings(str(row["channel"])).public_name,
            "status": "SUSPENDED" if row["paused"] else "ACTIVE",
            "reason": row["reason"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    }


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
    return get_channel_statuses(target_path).get(key.value, {})


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
    return get_channel_statuses(target_path).get(key.value, {})
