"""Health checks for the external services the auto-pipeline depends on.

Provides logic-only validation consumed by operators and by the Telegram bot
buttons: YouTube API credentials, Google Drive access and Playwright cookies.
Checks are intentionally local (file presence / scope / quick subprocess), they
never upload or publish anything.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from src.config import (
    DRIVE_KEY_PATH,
    SETTINGS,
    _oauth_token_has_scope,
    get_channel_settings,
)

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"


def check_youtube_api(channel: str = "moku") -> Dict[str, Any]:
    """Validate YouTube OAuth token / Playwright cookies for a channel."""
    try:
        from src.youtube.uploader import verify_youtube_credentials_preflight

        ok, detail = verify_youtube_credentials_preflight(channel)
        return {"ok": bool(ok), "detail": detail}
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "detail": f"Error al validar YouTube: {exc}"}


def _gcloud_token_ok() -> bool:
    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False


def check_drive_api() -> Dict[str, Any]:
    """Validate Drive access without network uploads."""
    if SETTINGS.drive_use_gcloud:
        if _gcloud_token_ok():
            return {"ok": True, "detail": "gcloud autorizado"}
        return {"ok": False, "detail": "gcloud sin cuenta activa o sin token"}

    if DRIVE_KEY_PATH and Path(DRIVE_KEY_PATH).is_file():
        return {"ok": True, "detail": f"Service account: {Path(DRIVE_KEY_PATH).name}"}

    oauth_tokens = [
        channel.youtube_token_path
        for channel in SETTINGS.channels.values()
        if channel.youtube_token_path.is_file()
        and _oauth_token_has_scope(channel.youtube_token_path, DRIVE_SCOPE)
    ]
    if oauth_tokens:
        return {"ok": True, "detail": "Token OAuth de canal con scope Drive"}

    return {
        "ok": False,
        "detail": "Falta DRIVE_KEY_PATH, gcloud, o token OAuth con scope Drive",
    }


def check_cookies(channel: str = "moku") -> Dict[str, Any]:
    """Validate Playwright cookies files for a given channel."""
    try:
        settings = get_channel_settings(channel)
    except Exception as exc:
        return {"ok": False, "detail": f"Canal inválido: {exc}"}

    path = settings.cookies_path
    if not Path(path).is_file():
        return {"ok": False, "detail": f"Faltan cookies: {path.name}"}
    size = Path(path).stat().st_size
    if size < 2:
        return {"ok": False, "detail": f"Cookies vacías: {path.name}"}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        valid = isinstance(data, list) and len(data) > 0
    except (OSError, ValueError):
        valid = False
    if not valid:
        return {"ok": False, "detail": f"Cookies inválidas: {path.name}"}
    return {"ok": True, "detail": f"Cookies OK ({len(data)} dominios)"}


def check_all(channel: str = "moku") -> Dict[str, Dict[str, Any]]:
    """Combined health report for YouTube, Drive and Cookies."""
    report: Dict[str, Dict[str, Any]] = {
        "youtube": check_youtube_api(channel),
        "drive": check_drive_api(),
        "cookies": check_cookies(channel),
    }
    report["all_ok"] = {"ok": all(item["ok"] for item in report.values())}
    return report


def format_status_report(report: Dict[str, Dict[str, Any]], channel: str = "moku") -> str:
    """Render a clean, single Telegram/CLI status message without secrets or paths."""
    lines = [f"Estado de APIs · canal {channel}", ""]
    order: List[str] = ["youtube", "drive", "cookies"]
    labels = {"youtube": "YouTube", "drive": "Drive", "cookies": "Cookies"}
    for key in order:
        item = report.get(key, {})
        icon = "OK" if item.get("ok") else "FALLO"
        lines.append(f"• {labels[key]}: {icon} — {item.get('detail', '')}")
    overall = report.get("all_ok", {}).get("ok", False)
    lines.append("")
    lines.append("Todas las APIs activas." if overall else "Hay servicios que requieren atención.")
    return "\n".join(lines)