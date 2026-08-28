"""
src/compositing/stream_renderer.py - Direct Raw Stream to FFmpeg Video Pipeline.

Streams WebGL canvas frame buffers directly into FFmpeg stdin with backpressure control,
muxing mastered audio and karaoke ASS subtitles without creating temporary disk image files.
"""
from __future__ import annotations

import errno
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from playwright.sync_api import sync_playwright

from src.narrative.schema import CosmicScriptContract
from src.rendering.renderer import CosmicShaderRenderer, resolve_chrome_path
from src.log import get_logger

logger = get_logger("stream_renderer")


class DirectStreamCompositor:
    """Renders WebGL scenes and pipes frames directly into FFmpeg stdin."""

    def __init__(self, chrome_exec_path: Optional[str] = None) -> None:
        self.chrome_path = chrome_exec_path or resolve_chrome_path()
        self.shader_renderer = CosmicShaderRenderer(chrome_exec_path=self.chrome_path)

    def render_and_mux(
        self,
        script_contract: CosmicScriptContract,
        output_mp4_path: Union[str, Path],
        master_audio_path: Optional[Union[str, Path]] = None,
        subtitles_ass_path: Optional[Union[str, Path]] = None,
        duration_sec: float = 30.0,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
    ) -> Path:
        """
        Executes end-to-end direct stream rendering:
        1. Compiles runtime HTML with GLSL shaders and scene parameters.
        2. Spawns FFmpeg process with stdin pipe (`image2pipe`).
        3. Headless Chromium evaluates frames and writes PNG buffers directly to `ffmpeg.stdin`.
        4. Muxes with master audio and burns/applies ASS subtitles.
        """
        out_p = Path(output_mp4_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        log_file_path = out_p.parent / f"{out_p.stem}_ffmpeg.log"

        total_frames = max(1, int(round(duration_sec * fps)))
        logger.info(
            "Iniciando renderizado directo a FFmpeg stdin: %dx%d @ %dfps (%.1fs = %d frames)",
            width, height, fps, duration_sec, total_frames
        )

        html_content = self.shader_renderer.build_runtime_html(
            script_contract=script_contract,
            width=width,
            height=height,
            fps=fps,
        )

        # Build FFmpeg command
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-v", "warning",
            "-f", "image2pipe",
            "-vcodec", "png",
            "-r", str(fps),
            "-i", "-",
        ]

        has_audio = master_audio_path and Path(master_audio_path).is_file()
        if has_audio:
            ffmpeg_cmd.extend(["-i", str(Path(master_audio_path).resolve())])

        has_subs = subtitles_ass_path and Path(subtitles_ass_path).is_file()
        if has_subs:
            sub_escaped = str(Path(subtitles_ass_path).resolve()).replace(":", "\\:").replace("'", "\\'")
            ffmpeg_cmd.extend(["-vf", f"ass='{sub_escaped}'"])

        ffmpeg_cmd.extend([
            "-c:v", "libx264",
            "-profile:v", "high",
            "-level:v", "4.1",
            "-preset", "veryfast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
        ])

        if has_audio:
            ffmpeg_cmd.extend(["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", "-shortest"])
        else:
            ffmpeg_cmd.extend(["-an"])

        ffmpeg_cmd.append(str(out_p.resolve()))

        # Launch Playwright & FFmpeg Pipeline
        launch_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--hide-scrollbars",
        ]
        launch_kwargs: Dict[str, Any] = {"headless": True, "args": launch_args}
        if self.chrome_path:
            launch_kwargs["executable_path"] = self.chrome_path

        start_time = time.time()

        with log_file_path.open("wb") as log_f:
            proc = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=log_f,
                stderr=log_f,
            )

            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(**launch_kwargs)
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.set_content(html_content, wait_until="domcontentloaded")
                    canvas_elem = page.locator("body")

                    for frame_idx in range(total_frames):
                        page.evaluate(
                            "([f, total]) => { window.renderFrame(f, total); }",
                            [frame_idx, total_frames],
                        )
                        frame_bytes = page.screenshot(type="png")
                        try:
                            proc.stdin.write(frame_bytes)
                            if frame_idx % 10 == 0:
                                proc.stdin.flush()
                        except (BrokenPipeError, OSError) as pipe_err:
                            logger.info("FFmpeg pipe cerrado por el receptor en fotograma %d (%s)", frame_idx, pipe_err)
                            break

                    browser.close()

                try:
                    proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
                try:
                    proc.stdin.close()
                except (BrokenPipeError, OSError):
                    pass

                proc.wait()

                if proc.returncode != 0:
                    err_msg = log_file_path.read_text(encoding="utf-8", errors="ignore") if log_file_path.exists() else "Unknown"
                    raise RuntimeError(
                        f"FFmpeg pipeline error (code {proc.returncode}): {err_msg}"
                    )
            except Exception as exc:
                if not isinstance(exc, (BrokenPipeError, OSError)):
                    if proc.poll() is None:
                        proc.kill()
                    raise RuntimeError(f"Error during headless frame stream: {exc}") from exc

        elapsed = time.time() - start_time
        fps_eff = total_frames / max(0.1, elapsed)
        logger.info("✅ Video renderizado con éxito en %.2fs (%.1f fps): %s (%d KB)", elapsed, fps_eff, out_p.name, out_p.stat().st_size // 1024)

        return out_p
