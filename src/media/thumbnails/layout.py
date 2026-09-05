"""
src/media/thumbnails/layout.py - Safe zone management and aspect ratio coordinates.
"""
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class SafeZone:
    top: int
    bottom: int
    left: int
    right: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


class AspectLayoutManager:
    """
    Manages layout positioning respecting YouTube safe zones:
    - 16:9 (1920x1080): Avoids bottom-right timestamp badge (180x45px).
    - 9:16 (1080x1920 Shorts): Avoids bottom 25% (caption + channel buttons) and right sidebar (like/comment/share icons).
    """

    @staticmethod
    def get_safe_zone(width: int, height: int) -> SafeZone:
        is_vertical = height > width
        if is_vertical:
            # 1080x1920 Vertical Shorts
            return SafeZone(
                top=int(height * 0.10),      # Top 10% margin
                bottom=int(height * 0.72),   # Keep main content above 72% height to avoid UI overlay
                left=int(width * 0.06),      # 6% left margin
                right=int(width * 0.88),     # Avoid right side icons
            )
        else:
            # 1920x1080 / 1280x720 Horizontal Longform
            return SafeZone(
                top=int(height * 0.08),      # Top 8% margin
                bottom=int(height * 0.85),   # Bottom 15% margin (avoiding timeline & timestamp badge)
                left=int(width * 0.05),      # Left 5% margin
                right=int(width * 0.81),     # Right 19% margin (avoiding timestamp badge)
            )

    @staticmethod
    def get_hook_text_position(width: int, height: int, text_height: int) -> Tuple[int, int]:
        safe = AspectLayoutManager.get_safe_zone(width, height)
        is_vertical = height > width
        if is_vertical:
            # Place in upper-middle third (striking at first glance)
            y = safe.top + int(safe.height * 0.20)
        else:
            # Lower-middle anchor with high contrast
            y = safe.bottom - text_height - 40
        return safe.left + 20, max(safe.top, y)
