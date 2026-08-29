"""
src/rendering/renderer.py - Headless Playwright/WebGL Cosmic Render Engine.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

from playwright.sync_api import sync_playwright

from src.narrative.schema import CosmicScriptContract, SceneContract, VideoFormat
from src.log import get_logger

logger = get_logger("cosmic_renderer")

DEFAULT_CHROME_CANDIDATES = [
    os.environ.get("PLAYWRIGHT_CHROME_EXECUTABLE_PATH", ""),
    "/opt/hermes/playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell",
    "/opt/hermes/playwright/chromium-1228/chrome-linux/chrome",
    shutil.which("google-chrome") or "",
    shutil.which("chromium-browser") or "",
    shutil.which("chromium") or "",
]


def resolve_chrome_path() -> Optional[str]:
    for cand in DEFAULT_CHROME_CANDIDATES:
        if cand and Path(cand).is_file() and os.access(cand, os.X_OK):
            return cand
    return None


class CosmicShaderRenderer:
    """Renders multi-pass GLSL scenes with unified post-processing deterministically."""

    def __init__(self, chrome_exec_path: Optional[str] = None) -> None:
        self.chrome_path = chrome_exec_path or resolve_chrome_path()
        self.shaders_dir = Path(__file__).resolve().parent / "shaders"
        self.web_dir = Path(__file__).resolve().parent / "web"

    def _load_shader(self, filename: str) -> str:
        shader_file = self.shaders_dir / filename
        if not shader_file.is_file():
            raise FileNotFoundError(f"Shader file not found: {shader_file}")
        return shader_file.read_text(encoding="utf-8")

    def build_runtime_html(
        self,
        script_contract: CosmicScriptContract,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
    ) -> str:
        """Assembles HTML by embedding all GLSL shaders and JSON scene config."""
        template_html = (self.web_dir / "index.html").read_text(encoding="utf-8")

        radar_fs = self._load_shader("radar.frag")
        monoliths_fs = self._load_shader("monoliths.frag")
        singularity_fs = self._load_shader("singularity.frag")
        postprocess_fs = self._load_shader("postprocess.frag")

        # Clean shader sources for JS template literals
        radar_escaped = radar_fs.replace("`", "\\`").replace("${", "\\${")
        monoliths_escaped = monoliths_fs.replace("`", "\\`").replace("${", "\\${")
        singularity_escaped = singularity_fs.replace("`", "\\`").replace("${", "\\${")
        postprocess_escaped = postprocess_fs.replace("`", "\\`").replace("${", "\\${")

        html = template_html.replace("`__RADAR_FRAG__`", f"`{radar_escaped}`")
        html = html.replace("`__MONOLITHS_FRAG__`", f"`{monoliths_escaped}`")
        html = html.replace("`__SINGULARITY_FRAG__`", f"`{singularity_escaped}`")
        html = html.replace("`__POSTPROCESS_FRAG__`", f"`{postprocess_escaped}`")

        scene_config = {
            "format": script_contract.format.value if hasattr(script_contract.format, "value") else str(script_contract.format),
            "telemetryHeader": script_contract.telemetry_header,
            "fps": fps,
            "scenes": [s.to_dict() if hasattr(s, "to_dict") else s for s in script_contract.scenes],
        }
        config_json = json.dumps(scene_config, indent=2, ensure_ascii=False)
        html = html.replace("__SCENE_CONFIG_JSON__", config_json)

        return html

    def render_single_frame(
        self,
        script_contract: CosmicScriptContract,
        frame_idx: int = 0,
        total_frames: Optional[int] = None,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
    ) -> bytes:
        """Renders and returns a single PNG screenshot frame bytes."""
        if total_frames is not None:
            actual_total_frames = max(1, int(total_frames))
        else:
            scenes_dur = sum(getattr(s, "duration_sec", 0.0) for s in getattr(script_contract, "scenes", []))
            actual_total_frames = max(1, int(round((scenes_dur if scenes_dur > 0 else 30.0) * fps)))

        html_content = self.build_runtime_html(script_contract, width=width, height=height, fps=fps)

        launch_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--hide-scrollbars",
        ]
        launch_kwargs: Dict[str, Any] = {"headless": True, "args": launch_args}
        if self.chrome_path:
            launch_kwargs["executable_path"] = self.chrome_path

        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_content(html_content, wait_until="domcontentloaded")
            page.evaluate(
                "([f, total]) => { window.renderFrame(f, total); }",
                [frame_idx, actual_total_frames],
            )
            png_bytes = page.locator("body").screenshot(type="png")
            browser.close()
            return png_bytes
