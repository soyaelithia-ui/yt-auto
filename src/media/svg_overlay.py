"""
Declarative SVG HUD & Vector Overlay Engine for yt-auto Visual Pipeline.
Uses resvg-py for high-fidelity Rust SVG rasterization with in-memory XML template
and raster caching, parameter interpolation, and zero-allocation buffer mutation.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
from PIL import Image

try:
    import resvg_py
except ImportError:
    resvg_py = None


class SVGOverlayEngine:
    """
    Renders dynamic SVG vector overlays into NumPy RGBA frame buffers.
    Supports in-memory XML template caching, parameter string/regex replacement,
    and raster caching for high-throughput zero-allocation compositing.
    """

    def __init__(self, assets_dir: Optional[Union[str, Path]] = None) -> None:
        if assets_dir:
            self.assets_dir = Path(assets_dir)
        else:
            self.assets_dir = Path(__file__).resolve().parents[2] / "assets" / "svg_overlays"
        self._template_cache: Dict[str, str] = {}
        self._raster_cache: Dict[Tuple[str, int, int, Tuple[Tuple[str, str], ...]], np.ndarray] = {}

    def load_template(self, preset_name: str) -> str:
        """Load and cache raw SVG string from disk."""
        if preset_name in self._template_cache:
            return self._template_cache[preset_name]
        filename = preset_name if preset_name.endswith(".svg") else f"{preset_name}.svg"
        svg_path = self.assets_dir / filename
        if not svg_path.exists():
            raise FileNotFoundError(f"SVG overlay preset '{preset_name}' not found at {svg_path}")
        content = svg_path.read_text(encoding="utf-8")
        self._template_cache[preset_name] = content
        return content

    def interpolate_template(
        self,
        svg_text: str,
        params: Optional[Dict[str, Any]] = None,
        time_sec: float = 0.0,
    ) -> str:
        """Interpolate dynamic parameters into SVG XML placeholders."""
        if not params and not ("{{" in svg_text or "{" in svg_text):
            return svg_text
        merged_params: Dict[str, str] = {"time_sec": f"{time_sec:.2f}"}
        if params:
            merged_params.update({str(k): str(v) for k, v in params.items()})

        rendered = svg_text
        for k, v in merged_params.items():
            rendered = re.sub(r"\{\{\s*" + re.escape(k) + r"\s*\}\}", str(v), rendered)
            rendered = re.sub(r"\{" + re.escape(k) + r"\}", str(v), rendered)
        return rendered

    def render_overlay(
        self,
        preset_name: str,
        width: int,
        height: int,
        time_sec: float = 0.0,
        params: Optional[Dict[str, Any]] = None,
        out_buffer: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """
        Render an SVG overlay preset to an RGBA NumPy array.
        Renders in-place into out_buffer if provided.
        """
        if out_buffer is not None:
            if out_buffer.shape != (height, width, 4) or out_buffer.dtype != np.uint8:
                raise ValueError(
                    f"out_buffer shape {out_buffer.shape} or dtype {out_buffer.dtype} mismatch. "
                    f"Expected {(height, width, 4)} of uint8."
                )

        if not preset_name or str(preset_name).lower() in ("none", "null", ""):
            if out_buffer is not None:
                out_buffer.fill(0)
                return out_buffer
            return np.zeros((height, width, 4), dtype=np.uint8)

        param_key: Tuple[Tuple[str, str], ...] = (
            tuple(sorted((str(k), str(v)) for k, v in params.items())) if params else ()
        )
        cache_key = (str(preset_name), width, height, param_key)

        if cache_key in self._raster_cache:
            cached = self._raster_cache[cache_key]
            if out_buffer is not None:
                np.copyto(out_buffer, cached)
                return out_buffer
            return cached.copy()

        svg_text = self.load_template(preset_name)
        interpolated = self.interpolate_template(svg_text, params, time_sec)

        if resvg_py is None:
            raise RuntimeError("resvg-py is not installed. Please install resvg-py.")

        png_bytes = resvg_py.svg_to_bytes(svg_string=interpolated, width=width, height=height)
        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        arr = np.array(img, dtype=np.uint8)

        # Handle aspect ratio dimension differences when resvg-py preserves SVG viewBox aspect ratio
        if arr.shape != (height, width, 4):
            canvas = np.zeros((height, width, 4), dtype=np.uint8)
            img_h, img_w = arr.shape[:2]
            y_offset = max(0, (height - img_h) // 2)
            x_offset = max(0, (width - img_w) // 2)
            paste_h = min(img_h, height)
            paste_w = min(img_w, width)
            canvas[y_offset : y_offset + paste_h, x_offset : x_offset + paste_w] = arr[:paste_h, :paste_w]
            arr = canvas

        if len(self._raster_cache) >= 128:
            self._raster_cache.clear()

        self._raster_cache[cache_key] = arr
        if out_buffer is not None:
            np.copyto(out_buffer, arr)
            return out_buffer
        return arr
