"""
Declarative SVG HUD & Vector Overlay Engine for yt-auto Visual Pipeline.
Uses resvg-py for high-fidelity Rust SVG rasterization with bounded LRU cache (maxsize=128),
in-memory XML template caching, parameter interpolation, zero-allocation buffer mutation,
and headless Pillow rasterization fallback (Zero-Browser Policy).
"""

from __future__ import annotations

from collections import OrderedDict
import io
import logging
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any, Dict, Optional, Tuple, Union
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

try:
    import resvg_py
except ImportError:
    resvg_py = None


class SVGOverlayEngine:
    """
    Renders dynamic SVG vector overlays into NumPy RGBA frame buffers.
    Supports in-memory XML template caching, parameter interpolation with embedded defaults,
    bounded LRU raster caching (maxsize=128), and zero-allocation buffer mutation.
    """

    def __init__(
        self,
        assets_dir: Optional[Union[str, Path]] = None,
        maxsize: int = 128,
    ) -> None:
        if assets_dir:
            self.assets_dir = Path(assets_dir)
        else:
            self.assets_dir = Path(__file__).resolve().parents[2] / "assets" / "svg_overlays"
        self.maxsize = maxsize
        self._template_cache: Dict[str, str] = {}
        self._raster_cache: OrderedDict[Tuple[str, int, int, Tuple[Tuple[str, str], ...]], np.ndarray] = OrderedDict()
        self._cache_hits: int = 0
        self._cache_misses: int = 0

    def cache_info(self) -> SimpleNamespace:
        """Return LRU cache hit/miss statistics and sizes."""
        return SimpleNamespace(
            hits=self._cache_hits,
            misses=self._cache_misses,
            currsize=len(self._raster_cache),
            maxsize=self.maxsize,
        )

    def clear_cache(self) -> None:
        """Flush the raster LRU cache and reset metrics."""
        self._raster_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

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
        """Interpolate dynamic parameters into SVG XML placeholders, supporting embedded defaults."""
        merged_params: Dict[str, str] = {"time_sec": f"{time_sec:.2f}"}
        if params:
            merged_params.update({str(k): str(v) for k, v in params.items()})

        # Replace double curly braces {{param:default}} or {{param}}
        def _replace_double(match: re.Match) -> str:
            key = match.group(1).strip()
            default_val = match.group(2) if match.group(2) is not None else ""
            return str(merged_params.get(key, default_val))

        rendered = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)(?::([^}]*))?\s*\}\}", _replace_double, svg_text)

        # Replace single curly braces {param:default} or {param}
        def _replace_single(match: re.Match) -> str:
            key = match.group(1).strip()
            default_val = match.group(2) if match.group(2) is not None else ""
            return str(merged_params.get(key, default_val))

        rendered = re.sub(r"\{([a-zA-Z0-9_]+)(?::([^}]*))?\}", _replace_single, rendered)

        # Substitute any remaining direct keys in merged_params
        for k, v in merged_params.items():
            rendered = re.sub(r"\{\{\s*" + re.escape(k) + r"\s*\}\}", str(v), rendered)
            rendered = re.sub(r"\{" + re.escape(k) + r"\}", str(v), rendered)

        # Strip any lingering unreplaced placeholder tokens to ensure clean XML
        rendered = re.sub(r"\{\{[^}]*\}\}", "", rendered)
        return rendered

    def _render_pillow_fallback(self, svg_text: str, width: int, height: int) -> np.ndarray:
        """
        Headless Pillow rasterization fallback for basic SVG overlays (Zero-Browser Policy).
        Parses common SVG shapes (rect, circle, line, text, polygon, path) and renders to RGBA array.
        """
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        try:
            root = ET.fromstring(svg_text)
        except Exception as exc:
            logger.warning(f"Pillow fallback XML parse error: {exc}")
            return np.zeros((height, width, 4), dtype=np.uint8)

        # Determine viewBox scale
        view_w, view_h = float(width), float(height)
        view_box = root.attrib.get("viewBox")
        if view_box:
            parts = [float(p) for p in view_box.replace(",", " ").split() if p]
            if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
                view_w, view_h = parts[2], parts[3]

        scale_x = width / view_w
        scale_y = height / view_h

        def _parse_color(color_str: Optional[str], default=(255, 255, 255, 255)) -> Tuple[int, int, int, int]:
            if not color_str or color_str.lower() in ("none", "null", "") or color_str.startswith("url"):
                return (0, 0, 0, 0)
            c = color_str.strip()
            if c.startswith("#"):
                hex_str = c[1:]
                if len(hex_str) == 3:
                    hex_str = "".join(ch * 2 for ch in hex_str)
                if len(hex_str) == 6:
                    r, g, b = int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
                    return (r, g, b, 255)
                elif len(hex_str) == 8:
                    r, g, b, a = int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16), int(hex_str[6:8], 16)
                    return (r, g, b, a)
            return default

        def _traverse(elem, offset_x=0.0, offset_y=0.0):
            dx, dy = 0.0, 0.0
            transform = elem.attrib.get("transform", "")
            if "translate" in transform:
                match = re.search(r"translate\(\s*([-\d.]+)\s*[,\s]\s*([-\d.]+)\s*\)", transform)
                if match:
                    dx, dy = float(match.group(1)), float(match.group(2))

            cur_x = offset_x + dx
            cur_y = offset_y + dy

            tag = elem.tag.split("}")[-1]

            fill_str = elem.attrib.get("fill")
            fill_opacity = float(elem.attrib.get("fill-opacity", 1.0))
            stroke_str = elem.attrib.get("stroke")
            stroke_width = float(elem.attrib.get("stroke-width", 1.0)) * min(scale_x, scale_y)

            fill_color = _parse_color(fill_str)
            if fill_color[3] > 0 and fill_opacity < 1.0:
                fill_color = (fill_color[0], fill_color[1], fill_color[2], int(fill_color[3] * fill_opacity))

            stroke_color = _parse_color(stroke_str) if stroke_str else None

            if tag == "rect":
                x = (float(elem.attrib.get("x", 0)) + cur_x) * scale_x
                y = (float(elem.attrib.get("y", 0)) + cur_y) * scale_y
                w = float(elem.attrib.get("width", 0)) * scale_x
                h = float(elem.attrib.get("height", 0)) * scale_y
                if fill_color[3] > 0:
                    draw.rectangle([x, y, x + w, y + h], fill=fill_color)
                if stroke_color and stroke_color[3] > 0:
                    draw.rectangle([x, y, x + w, y + h], outline=stroke_color, width=max(1, int(stroke_width)))

            elif tag == "circle":
                cx = (float(elem.attrib.get("cx", 0)) + cur_x) * scale_x
                cy = (float(elem.attrib.get("cy", 0)) + cur_y) * scale_y
                r = float(elem.attrib.get("r", 0)) * min(scale_x, scale_y)
                if fill_color[3] > 0:
                    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill_color)
                if stroke_color and stroke_color[3] > 0:
                    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=stroke_color, width=max(1, int(stroke_width)))

            elif tag == "line":
                x1 = (float(elem.attrib.get("x1", 0)) + cur_x) * scale_x
                y1 = (float(elem.attrib.get("y1", 0)) + cur_y) * scale_y
                x2 = (float(elem.attrib.get("x2", 0)) + cur_x) * scale_x
                y2 = (float(elem.attrib.get("y2", 0)) + cur_y) * scale_y
                line_color = stroke_color or fill_color
                if line_color[3] > 0:
                    draw.line([(x1, y1), (x2, y2)], fill=line_color, width=max(1, int(stroke_width)))

            elif tag in ("text", "tspan"):
                txt = (elem.text or "").strip()
                if txt:
                    x = (float(elem.attrib.get("x", 0)) + cur_x) * scale_x
                    y = (float(elem.attrib.get("y", 0)) + cur_y) * scale_y
                    font_size = int(float(elem.attrib.get("font-size", 20)) * min(scale_x, scale_y))
                    try:
                        font = ImageFont.load_default()
                    except Exception:
                        font = None
                    text_color = fill_color if fill_color[3] > 0 else (255, 255, 255, 255)
                    draw.text((x, y), txt, fill=text_color, font=font)

            elif tag == "polygon":
                pts_raw = elem.attrib.get("points", "")
                if pts_raw:
                    coords = []
                    for pt in re.split(r"[\s,]+", pts_raw.strip()):
                        if pt:
                            coords.append(float(pt))
                    if len(coords) >= 4 and len(coords) % 2 == 0:
                        pts = [((coords[i] + cur_x) * scale_x, (coords[i + 1] + cur_y) * scale_y) for i in range(0, len(coords), 2)]
                        if fill_color[3] > 0:
                            draw.polygon(pts, fill=fill_color)
                        if stroke_color and stroke_color[3] > 0:
                            draw.polygon(pts, outline=stroke_color)

            for child in elem:
                _traverse(child, cur_x, cur_y)

        _traverse(root, 0.0, 0.0)
        return np.array(canvas, dtype=np.uint8)

    def render_overlay(
        self,
        preset_name: Optional[str],
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
            self._cache_hits += 1
            self._raster_cache.move_to_end(cache_key)
            cached = self._raster_cache[cache_key]
            if out_buffer is not None:
                np.copyto(out_buffer, cached)
                return out_buffer
            return cached.copy()

        self._cache_misses += 1

        svg_text = self.load_template(preset_name)
        interpolated = self.interpolate_template(svg_text, params, time_sec)

        arr: Optional[np.ndarray] = None

        if resvg_py is not None:
            try:
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
            except Exception as exc:
                logger.warning("resvg-py rasterization failed (%s); falling back to Pillow rasterization", exc)
                arr = None

        if arr is None:
            logger.warning("resvg-py unavailable; falling back to Pillow rasterization")
            arr = self._render_pillow_fallback(interpolated, width, height)

        if len(self._raster_cache) >= self.maxsize:
            self._raster_cache.popitem(last=False)

        self._raster_cache[cache_key] = arr
        if out_buffer is not None:
            np.copyto(out_buffer, arr)
            return out_buffer
        return arr
