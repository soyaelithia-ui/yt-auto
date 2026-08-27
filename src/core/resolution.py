"""Single source of truth for render resolutions (AD-01).

Every resolution-dependent artifact (SCP renderer, daemon shorts ASS canvas,
prepublication gate, template presets, contact-sheet scoring, 5-cycle audit)
consumes these constants so resolution targets can never drift between
subsystems. Longform upgraded to 1080p per owner quality directive (2026-08-23).
"""

from __future__ import annotations

SHORT_RESOLUTION: tuple[int, int] = (1080, 1920)
SHORT_RESOLUTION_TEST: tuple[int, int] = (540, 960)
LONGFORM_RESOLUTION: tuple[int, int] = (1920, 1080)


def is_short_resolution(width: int, height: int) -> bool:
    """True when the given dimensions are a canonical short-mode canvas.

    Accepts both the full render (1080x1920) and the test-scale render
    (360x640). Longform (1280x720) and any other aspect ratio are rejected.
    """
    return (width, height) in (SHORT_RESOLUTION, SHORT_RESOLUTION_TEST)