"""Compatibility adapter for text-free local AI thumbnail generation."""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

from src.media.thumbnails.engine import ThumbnailConfig, ThumbnailEngine


class ResilientThumbnailEngine:
    """Preserve the legacy call shape while delegating to the local AI bank."""

    def __init__(self, custom_font_paths: Optional[List[str]] = None) -> None:
        del custom_font_paths
        self._engine = ThumbnailEngine()
        self.font_candidates: list[str] = []

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
        del highlight_box, badge_text, subtitle_color, badge_color
        if isinstance(accent_color, tuple):
            accent_hex = "#%02x%02x%02x" % accent_color[:3]
        else:
            accent_hex = str(accent_color)
        title = f"{title_main}: {title_sub}" if title_sub else title_main
        return self._engine.generate(
            ThumbnailConfig(
                title=title,
                channel_id=kwargs.get("channel_id", "moku"),
                lane_id=kwargs.get("lane_id"),
                output_path=Path(output_path).resolve(),
                width=width,
                height=height,
                accent_color=accent_hex,
                archetype=kwargs.get("archetype", "scp"),
                template=kwargs.get("template"),
                metadata=kwargs.get("metadata"),
                text_free=True,
            ),
            base_image_path=background_image,
        )
