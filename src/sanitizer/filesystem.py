"""src/sanitizer/filesystem.py - File path and filename sanitization."""

from __future__ import annotations

import re


def sanitize_filename(name: str) -> str:
    """Sanitize a string for safe usage as a filename."""
    cleaned = re.sub(r"[^\w\-_]", "_", name)
    return cleaned[:100]
