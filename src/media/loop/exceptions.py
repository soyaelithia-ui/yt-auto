"""Exceptions for LoopVideoEngine subsystem."""

from __future__ import annotations

from src.media.interface import CatalogAssetNotFoundError, CompositorError


class LoopVideoError(CompositorError):
    """Base exception for LoopVideoEngine errors."""
    pass


class LoopVideoAssetError(CatalogAssetNotFoundError, LoopVideoError):
    """Raised when required video loop assets or fallback media cannot be found (fail-closed)."""
    pass


class LoopCompositionError(LoopVideoError):
    """Raised when video composition or FFmpeg execution fails."""
    pass
