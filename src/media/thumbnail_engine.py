"""
src/media/thumbnail_engine.py - Backward-Compatibility Adapter for Thumbnail Generation.

Delegates thumbnail rendering to canonical src.media.thumbnails.engine.ThumbnailEngine.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union
from PIL import ImageFont

from src.media.thumbnails.engine import ThumbnailEngine, ThumbnailConfig
from src.media.thumbnails.typography import DynamicTypographyEngine

logger = logging.getLogger("thumbnail_engine")

SYSTEM_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/opt/hermes/hermes-webui/static/vendor/katex/0.16.22/fonts/KaTeX_SansSerif-Bold.ttf",
    "/opt/hermes/hermes-webui/static/vendor/katex/0.16.22/fonts/KaTeX_Main-Bold.ttf",
]


class ResilientThumbnailEngine:
    """Backward-compatibility adapter delegating to ThumbnailEngine."""

    def __init__(self, custom_font_paths: Optional[List[str]] = None) -> None:
        self._engine = ThumbnailEngine()
        self.font_candidates = (custom_font_paths or []) + SYSTEM_FONT_CANDIDATES

    def resolve_font(self, size: int) -> ImageFont.FreeTypeFont:
        """Loads TrueType font via DynamicTypographyEngine."""
        return DynamicTypographyEngine.resolve_font("LiberationSans-Bold.ttf", size)

    def generate(
        self,
        output_path: Union[Path, str],
        title_main: str = "SCP-2000",
        title_sub: str = "DEUS EX MACHINA",
        highlight_box: str = "EL REINICIO DE LA HUMANIDAD",
        badge_text: str = "NIVEL 5 // CLASIFICADO // TOP SECRET",
        background_image: Optional[Union[Path, str]] = None,
        accent_color: Tuple[int, int, int] | str = (0, 255, 180),
        subtitle_color: Tuple[int, int, int] | str = (255, 255, 255),
        badge_color: Tuple[int, int, int] | str = (190, 25, 35),
        width: int = 1280,
        height: int = 720,
        **kwargs: Any,
    ) -> Path:
        """Adapts legacy keyword arguments into a ThumbnailConfig and delegates to ThumbnailEngine."""
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(accent_color, tuple):
            accent_hex = f"#{accent_color[0]:02x}{accent_color[1]:02x}{accent_color[2]:02x}"
        else:
            accent_hex = str(accent_color)

        title_full = f"{title_main}: {title_sub}" if title_sub else title_main
        hook = highlight_box or title_sub or title_main
        is_vertical = height > width

        metadata: dict[str, Any] = {
            "badge_text": badge_text,
            "category": badge_text,
            "title_raw": title_full,
        }
        if kwargs.get("metadata"):
            metadata.update(kwargs["metadata"])

        cfg = ThumbnailConfig(
            title=title_full,
            channel_id=kwargs.get("channel_id", "horror"),
            lane_id=kwargs.get("lane_id", "horror-scp-shorts" if is_vertical else "scp"),
            hook_text=hook,
            output_path=out_p,
            width=width,
            height=height,
            accent_color=accent_hex,
            archetype=kwargs.get("archetype", "scp"),
            template=kwargs.get("template"),
            metadata=metadata,
        )

        return self._engine.generate(
            config=cfg,
            base_image_path=background_image,
        )