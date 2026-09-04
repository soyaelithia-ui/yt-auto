"""
src/media/thumbnails/layouts/base.py - Abstract Base Layout and Registry for Niche Thumbnails.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type
from PIL import Image

from src.media.thumbnails.layout import SafeZone


class BaseThumbnailLayout(ABC):
    """
    Abstract contract for niche-specific thumbnail layout renderers.
    """

    @abstractmethod
    def apply_layout(
        self,
        canvas: Image.Image,
        title: str,
        channel_id: str,
        safe_zone: SafeZone,
        metadata: Dict[str, Any],
    ) -> Image.Image:
        """
        Apply niche graphical overlays, HUD elements, badges, and typography to the canvas.
        """
        pass


class LayoutRegistry:
    """
    Registry and dispatcher for channel/lane/archetype thumbnail layouts.
    """
    _registry: Dict[str, Type[BaseThumbnailLayout]] = {}
    _default_layout_cls: Optional[Type[BaseThumbnailLayout]] = None

    @classmethod
    def register(cls, *keys: str) -> Any:
        """Decorator to register a layout class under one or more keys."""
        def decorator(subclass: Type[BaseThumbnailLayout]) -> Type[BaseThumbnailLayout]:
            for key in keys:
                cls._registry[key.lower()] = subclass
            return subclass
        return decorator

    @classmethod
    def register_default(cls, subclass: Type[BaseThumbnailLayout]) -> Type[BaseThumbnailLayout]:
        cls._default_layout_cls = subclass
        return subclass

    @classmethod
    def get_layout(
        cls,
        channel_id: Optional[str] = None,
        archetype: Optional[str] = None,
        template: Optional[str] = None,
        is_vertical: Optional[bool] = None,
    ) -> BaseThumbnailLayout:
        """
        Resolves the appropriate layout instance based on archetype, template, or channel_id.
        Falls back to GeneralCinematicLayout if no specific match is found.
        """
        if not cls._registry:
            import src.media.thumbnails.layouts  # noqa: F401

        # Channel moku has two distinct operational lanes based on aspect ratio
        norm_chan = str(channel_id or "").lower()
        if norm_chan == "moku" and not archetype and not template:
            if is_vertical is True and "moku-scp-shorts" in cls._registry:
                return cls._registry["moku-scp-shorts"]()
            if is_vertical is False and "moku-horror-long" in cls._registry:
                return cls._registry["moku-horror-long"]()

        keys_to_try = [
            k.lower() for k in [archetype, template, channel_id] if k
        ]

        # 1. Exact match
        for key in keys_to_try:
            if key in cls._registry:
                return cls._registry[key]()

        # 2. Substring matching: prefer reg_key in key (archetype keyword in lane)
        for key in keys_to_try:
            for reg_key, layout_cls in cls._registry.items():
                if reg_key in key:
                    return layout_cls()

        for key in keys_to_try:
            for reg_key, layout_cls in cls._registry.items():
                if key in reg_key:
                    return layout_cls()

        if cls._default_layout_cls:
            return cls._default_layout_cls()

        # Lazy fallback import
        from src.media.thumbnails.layouts.cinematic import GeneralCinematicLayout
        return GeneralCinematicLayout()
