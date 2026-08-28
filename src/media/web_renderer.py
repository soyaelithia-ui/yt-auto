"""
src/media/web_video_renderer.py - Web-Based Procedural Video Render Engine.

Uses Playwright Headless Chromium to execute HTML5 Canvas, WebGL, Three.js and CSS
generative templates frame-by-frame deterministically, piping the resulting imagery
into FFmpeg to produce lightweight, mathematically seamless H.264 video loops.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.config import BASE_DIR, DEFAULT_DB_PATH
from src.core.catalog import LoopCatalogRepository, LoopRecord, compute_file_sha256
from src.log import get_logger

logger = get_logger("web_video_renderer")

__all__ = [
    "WebVideoRenderer",
    "RenderSpec",
    "THEMATIC_TEMPLATES",
    "CATEGORY_TECH_MAP",
]

THEMATIC_TEMPLATES: dict[str, str] = {
    "classified_terminal": "archetype_classified_terminal.html",
    "atmospheric_landscape": "archetype_atmospheric_landscape.html",
    "tactical_chamber": "archetype_tactical_chamber.html",
    "synaptic_network": "archetype_synaptic_network.html",
    "anomaly_silhouette": "archetype_anomaly_silhouette.html",
    "cosmic_singularity": "archetype_cosmic_singularity.html",
    "cosmic_horror": "archetype_cosmic_singularity.html",
    "dark_ambient": "archetype_atmospheric_landscape.html",
    "dark_forest": "archetype_atmospheric_landscape.html",
    "monsters": "archetype_anomaly_silhouette.html",
    "space_abyss": "archetype_cosmic_singularity.html",
    "scp": "archetype_classified_terminal.html",
    "drama_aita": "drama_waves_canvas.html",
}

CATEGORY_TECH_MAP: dict[str, str] = {
    "classified_terminal": "canvas2d",
    "atmospheric_landscape": "canvas2d",
    "tactical_chamber": "canvas2d",
    "synaptic_network": "canvas2d",
    "anomaly_silhouette": "canvas2d",
    "cosmic_singularity": "canvas2d",
    "cosmic_horror": "canvas2d",
    "dark_ambient": "canvas2d",
    "dark_forest": "canvas2d",
    "monsters": "canvas2d",
    "space_abyss": "canvas2d",
    "scp": "canvas2d",
    "drama_aita": "canvas2d",
}

CATEGORY_TAGS_MAP: dict[str, list[str]] = {
    "classified_terminal": ["terminal", "crt", "classified", "hud", "radar", "surveillance", "green", "amber", "red"],
    "atmospheric_landscape": ["landscape", "fog", "wanderer", "ruins", "dystopian", "storm", "sky", "wasteland"],
    "tactical_chamber": ["bunker", "chamber", "corridor", "vault", "emergency", "strobe", "containment", "brutalist"],
    "synaptic_network": ["neural", "synapse", "consciousness", "mind", "bioluminescent", "data", "cyan", "purple"],
    "anomaly_silhouette": ["anomaly", "creature", "monster", "colossus", "shadow", "embers", "silhouette", "fire"],
    "cosmic_singularity": ["void", "singularity", "black_hole", "vortex", "cosmic", "abyss", "rift", "purple", "cyan"],
    "cosmic_horror": ["void", "singularity", "black_hole", "vortex", "cosmic", "purple"],
    "dark_ambient": ["ambient", "darkness", "minimal", "void", "calm"],
    "dark_forest": ["trees", "fog", "spores", "nature", "night", "organic", "green"],
    "monsters": ["creepy", "eyes", "tentacles", "shadows", "blood", "red", "darkness"],
    "space_abyss": ["space", "stars", "singularity", "accretion_disk", "cyan", "blue"],
    "scp": ["terminal", "crt", "classified", "hud", "containment"],
    "drama_aita": ["waves", "neon", "gradient", "minimal", "modern", "audio_react"],
}


class RenderSpec:
    def __init__(
        self,
        category: str = "dark_ambient",
        orientation: str = "vertical",
        duration_sec: float = 8.0,
        fps: int = 30,
        seed: int = 42,
        custom_params: Optional[dict[str, Any]] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        template_name: Optional[str] = None,
        output_path: Optional[Union[str, Path]] = None,
        params: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self.category = category.strip().lower().replace("-", "_").replace(" ", "_")
        self.orientation = "horizontal" if orientation in ("horizontal", "16:9", "longform", (1920, 1080)) else "vertical"
        if width is not None and height is not None:
            self.width, self.height = int(width), int(height)
        elif self.orientation == "horizontal":
            self.width, self.height = 1920, 1080
        else:
            self.width, self.height = 1080, 1920
        self.duration_sec = float(duration_sec)
        self.fps = int(fps)
        self.seed = int(seed)
        self.custom_params = custom_params or params or {}
        self.template_name = template_name
        self.output_path = Path(output_path) if output_path else None


class WebVideoRenderer:
    """Headless Chromium web-based deterministic video renderer."""

    def __init__(
        self,
        templates_dir: Optional[str | Path] = None,
        output_loops_dir: Optional[str | Path] = None,
        db_path: str = DEFAULT_DB_PATH,
    ) -> None:
        self.templates_dir = Path(templates_dir or (BASE_DIR / "src" / "media" / "web_templates")).resolve()
        self.output_loops_dir = Path(output_loops_dir or (BASE_DIR / "assets" / "loops" / "web_procedural")).resolve()
        self.output_loops_dir.mkdir(parents=True, exist_ok=True)
        self.catalog = LoopCatalogRepository(db_path=db_path)

    def resolve_template_path(self, category: str, template_name: Optional[str] = None) -> Path:
        if template_name:
            tmpl_path = self.templates_dir / template_name
            if tmpl_path.is_file():
                return tmpl_path
        cat_norm = category.strip().lower().replace("-", "_").replace(" ", "_")
        tmpl_name = THEMATIC_TEMPLATES.get(cat_norm, "cosmic_horror_three.html")
        tmpl_path = self.templates_dir / tmpl_name
        if not tmpl_path.is_file():
            # Fallback to cosmic_horror_three.html if not found
            tmpl_path = self.templates_dir / "cosmic_horror_three.html"
        return tmpl_path

    def render_loop(
        self,
        spec: RenderSpec,
        output_filename: Optional[str] = None,
        register_in_db: bool = True,
    ) -> LoopRecord:
        """
        Renders a seamless procedural loop video from web templates into an MP4 file.
        Pipes PNG frame streams directly into FFmpeg.
        """
        from playwright.sync_api import sync_playwright

        template_path = self.resolve_template_path(spec.category, getattr(spec, "template_name", None))
        if not template_path.is_file():
            raise FileNotFoundError(f"Template file not found: {template_path}")

        if getattr(spec, "output_path", None):
            target_mp4 = Path(spec.output_path).resolve()
            target_mp4.parent.mkdir(parents=True, exist_ok=True)
            cat_dir = target_mp4.parent
        else:
            cat_dir = self.output_loops_dir / spec.category
            cat_dir.mkdir(parents=True, exist_ok=True)

            if not output_filename:
                orient_suffix = "h" if spec.orientation == "horizontal" else "v"
                output_filename = f"web_{spec.category}_{orient_suffix}_s{spec.seed}_{int(spec.duration_sec)}s.mp4"

            target_mp4 = cat_dir / output_filename
        total_frames = max(1, int(round(spec.duration_sec * spec.fps)))
        logger.info(
            "Rendering %s loop [%dx%d @ %dfps, %d frames, seed=%d] -> %s",
            spec.category, spec.width, spec.height, spec.fps, total_frames, spec.seed, target_mp4.name
        )

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-v", "error",
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "-r", str(spec.fps),
            "-i", "-",
            "-c:v", "libx264",
            "-profile:v", "main",
            "-pix_fmt", "yuv420p",
            "-crf", "19",
            "-preset", "ultrafast",
            "-movflags", "+faststart",
            str(target_mp4),
        ]

        from src.media.realtime_video_engine import resolve_chrome_executable
        chrome_exec = resolve_chrome_executable()

        launch_kwargs: Dict[str, Any] = {
            "headless": True,
            "args": [
                "--use-gl=angle",
                "--use-angle=swiftshader",
                "--enable-webgl",
                "--ignore-gpu-blocklist",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--hide-scrollbars",
            ],
        }
        if chrome_exec:
            launch_kwargs["executable_path"] = chrome_exec

        start_t = time.time()
        with subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
            with sync_playwright() as p:
                browser = p.chromium.launch(**launch_kwargs)
                page = browser.new_page(
                    viewport={"width": spec.width, "height": spec.height},
                    device_scale_factor=1.0,
                )
                page.goto(f"file://{template_path.resolve()}")
                page.evaluate(
                    "([w, h, s, p]) => { if (window.__setDimensions) window.__setDimensions(w, h, s, p); if (window.__setParams) window.__setParams(p); }",
                    [spec.width, spec.height, spec.seed, spec.custom_params],
                )

                for frame_idx in range(total_frames):
                    time_sec = frame_idx / float(spec.fps)
                    data_url = page.evaluate(
                        """([f, total, t, dur]) => {
                            if (window.renderSceneFrame) window.renderSceneFrame(f, total, t, dur);
                            const canvas = document.getElementById('c');
                            return canvas ? canvas.toDataURL('image/jpeg', 0.95) : null;
                        }""",
                        [frame_idx, total_frames, time_sec, spec.duration_sec],
                    )
                    if data_url and "," in data_url:
                        frame_bytes = base64.b64decode(data_url.split(",", 1)[1])
                        proc.stdin.write(frame_bytes)

                browser.close()

            proc.stdin.close()
            stderr_out = proc.stderr.read()
            proc.wait()
            if proc.returncode != 0:
                raise RuntimeError(f"FFmpeg encoding failed with code {proc.returncode}: {stderr_out.decode('utf-8', errors='ignore')}")

        elapsed = time.time() - start_t
        file_size = target_mp4.stat().st_size
        sha_hash = compute_file_sha256(target_mp4)
        tech = CATEGORY_TECH_MAP.get(spec.category, "webgl_shader")
        tags = CATEGORY_TAGS_MAP.get(spec.category, [spec.category, spec.orientation])

        logger.info(
            "Loop rendered successfully in %.2fs (%d KB, sha256=%s...)",
            elapsed, file_size // 1024, sha_hash[:10]
        )

        rec = LoopRecord(
            loop_id=f"web_{spec.category}_{spec.orientation}_{spec.seed}",
            category=spec.category,
            technology=tech,
            theme_tags=tags,
            orientation=spec.orientation,
            width=spec.width,
            height=spec.height,
            duration_sec=spec.duration_sec,
            fps=spec.fps,
            file_path=str(target_mp4),
            file_size_bytes=file_size,
            sha256=sha_hash,
            generator_params={"seed": spec.seed, "fps": spec.fps, "duration_sec": spec.duration_sec, **spec.custom_params},
            usage_count=0,
        )

        if register_in_db:
            self.catalog.register_loop(rec)

        return rec

    def render_preview_image(self, category: str, output_image_path: str | Path, orientation: str = "vertical", seed: int = 42) -> Path:
        """Renders a single high-quality PNG preview thumbnail for terminal or UI inspection."""
        from playwright.sync_api import sync_playwright
        from src.media.realtime_video_engine import resolve_chrome_executable

        template_path = self.resolve_template_path(category)
        w, h = (1920, 1080) if orientation in ("horizontal", "16:9") else (1080, 1920)
        out_p = Path(output_image_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        chrome_exec = resolve_chrome_executable()
        launch_kwargs: Dict[str, Any] = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if chrome_exec:
            launch_kwargs["executable_path"] = chrome_exec

        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs)
            page = browser.new_page(viewport={"width": w, "height": h})
            page.goto(f"file://{template_path.resolve()}")
            page.evaluate("([w, h, s]) => { if (window.__setDimensions) window.__setDimensions(w, h, s); }", [w, h, seed])
            page.evaluate("([f, total, t, dur]) => { if (window.renderSceneFrame) window.renderSceneFrame(f, total, t, dur); }", [15, 30, 0.5, 8.0])
            page.locator("#c").screenshot(path=str(out_p), type="png")
            browser.close()

        logger.info("Generated preview thumbnail: %s", out_p)
        return out_p
