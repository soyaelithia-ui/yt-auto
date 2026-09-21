"""
src/mcp/sanitizer.py - Credential and Secret Path Sanitizer for yt-auto MCP Server.

Recursively scrubs sensitive keys, tokens, OAuth credentials, and filesystem paths
from MCP tool outputs, resource responses, and error messages.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

# Regex patterns matching known secret token structures
_BEARER_PATTERN = re.compile(r"(?i)bearer\s+[a-z0-9_\-\.]{4,}")
_OAUTH_TOKEN_PATTERN = re.compile(r"ya29\.[a-zA-Z0-9_\-]{5,}")
_TELEGRAM_BOT_TOKEN_PATTERN = re.compile(r"\b\d{8,12}:[a-zA-Z0-9_-]{20,}\b")
_GOOGLE_API_KEY_PATTERN = re.compile(r"\bAIza[a-zA-Z0-9_\-]{8,}\b")
_GOCSPX_SECRET_PATTERN = re.compile(r"\bGOCSPX-[a-zA-Z0-9_\-]{10,}\b")
_PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"
)
_SECRET_PATH_PATTERN = re.compile(
    r"(/[^/:\s]+)*/(?:cookies|token|client_secret|service_account)[^/\s]*\.json"
)

_SENSITIVE_KEY_NAMES = frozenset({
    "auth",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "client_secret",
    "api_key",
    "apikey",
    "private_key",
    "password",
    "passwd",
    "bot_token",
    "telegram_token",
    "authorization",
})


def _is_sensitive_key(k_lower: str) -> bool:
    if k_lower.endswith("_available") or k_lower.endswith("_count") or k_lower.endswith("_status"):
        return False
    if k_lower in _SENSITIVE_KEY_NAMES:
        return True
    tokens = set(re.split(r"[_\-\s]+", k_lower))
    return bool(tokens & _SENSITIVE_KEY_NAMES)


def sanitize_string(value: str) -> str:
    """Mask secret substrings within string content."""
    if not value or not isinstance(value, str):
        return value

    text = _PRIVATE_KEY_PATTERN.sub("[REDACTED PRIVATE KEY]", value)
    text = _BEARER_PATTERN.sub("Bearer [REDACTED]", text)
    text = _OAUTH_TOKEN_PATTERN.sub("[REDACTED]", text)
    text = _TELEGRAM_BOT_TOKEN_PATTERN.sub("[REDACTED]", text)
    text = _GOOGLE_API_KEY_PATTERN.sub("[REDACTED]", text)
    text = _GOCSPX_SECRET_PATTERN.sub("[REDACTED]", text)
    text = _SECRET_PATH_PATTERN.sub("[REDACTED_PATH]", text)
    return text


def sanitize_payload(data: Any) -> Any:
    """
    Recursively traverse dictionaries, lists, and objects, replacing sensitive
    tokens and paths with '[REDACTED]'.
    """
    if data is None:
        return None

    # Booleans are instances of int in Python, so check bool first
    if isinstance(data, bool):
        return data

    if isinstance(data, (int, float)):
        return data

    if isinstance(data, str):
        return sanitize_string(data)

    if isinstance(data, Path):
        name = data.name.lower()
        if any(s in name for s in ("cookie", "token", "secret", "key")):
            return "[REDACTED_PATH]"
        return str(data)

    if isinstance(data, Exception):
        return sanitize_string(str(data))

    if isinstance(data, Mapping):
        sanitized_dict: dict[str, Any] = {}
        for key, value in data.items():
            k_lower = str(key).lower()

            # Replace secret paths with boolean presence flags if applicable
            if k_lower in ("cookies_path", "cookies_file"):
                p = Path(str(value)) if value else None
                sanitized_dict["cookies_available"] = bool(p and p.is_file())
                continue
            if k_lower in ("youtube_token_path", "token_path"):
                p = Path(str(value)) if value else None
                sanitized_dict["youtube_token_available"] = bool(p and p.is_file())
                continue

            # Mask values of sensitive keys
            if _is_sensitive_key(k_lower):
                sanitized_dict[str(key)] = "[REDACTED]"
            else:
                sanitized_dict[str(key)] = sanitize_payload(value)
        return sanitized_dict

    if isinstance(data, (list, tuple, set)):
        items = [sanitize_payload(item) for item in data]
        return type(data)(items)

    # For objects with to_dict or public_dict methods
    if hasattr(data, "public_dict") and callable(data.public_dict):
        return sanitize_payload(data.public_dict())
    if hasattr(data, "to_dict") and callable(data.to_dict):
        return sanitize_payload(data.to_dict())
    if hasattr(data, "dict") and callable(data.dict):
        return sanitize_payload(data.dict())
    if hasattr(data, "model_dump") and callable(data.model_dump):
        return sanitize_payload(data.model_dump())

    return sanitize_string(str(data))
