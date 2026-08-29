"""
src/compositing/stream_renderer.py - Direct Raw Stream to FFmpeg Video Pipeline.

Streams WebGL canvas frame buffers directly into FFmpeg stdin with backpressure control,
muxing mastered audio and karaoke ASS subtitles without creating temporary disk image files.
"""
from __future__ import annotations

import contextlib
import errno
import math
import os
import select
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from playwright.sync_api import sync_playwright

from src.core.lifecycle import cleanup_subprocesses, register_process
from src.narrative.schema import CosmicScriptContract
from src.rendering.renderer import CosmicShaderRenderer, resolve_chrome_path
from lib.ffmpeg import probe_media
from src.log import get_logger

logger = get_logger("stream_renderer")


class DirectStreamCompositor:
    """Renders WebGL scenes and pipes frames directly into FFmpeg stdin with backpressure flow control."""

    def __init__(self, chrome_exec_path: Optional[str] = None) -> None:
        self.chrome_path = chrome_exec_path or resolve_chrome_path()
        self.shader_renderer = CosmicShaderRenderer(chrome_exec_path=self.chrome_path)

    def render_and_mux(
        self,
        script_contract: CosmicScriptContract,
        output_mp4_path: Union[str, Path],
        master_audio_path: Optional[Union[str, Path]] = None,
        subtitles_ass_path: Optional[Union[str, Path]] = None,
        duration_sec: Optional[float] = None,
        total_frames: Optional[int] = None,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        stream_format: str = "image2pipe",
    ) -> Path:
        """
        Executes end-to-end direct stream rendering:
        1. Dynamically calculates duration and frame count from master audio or scene configuration.
        2. Compiles runtime HTML with GLSL shaders and scene parameters.
        3. Spawns FFmpeg process with stdin pipe and backpressure flow control.
        4. Headless Chromium evaluates frames and streams buffers directly to `ffmpeg.stdin`.
        5. Muxes with master audio and burns/applies ASS subtitles.
        """
        out_p = Path(output_mp4_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        log_file_path = out_p.parent / f"{out_p.stem}_ffmpeg.log"

        has_audio = master_audio_path is not None and Path(master_audio_path).is_file()

        # Dynamic duration & frame count calculation
        if total_frames is not None:
            actual_total_frames = max(1, int(total_frames))
            actual_duration_sec = float(duration_sec) if duration_sec is not None else (actual_total_frames / fps)
        elif has_audio:
            try:
                probe = probe_media(master_audio_path)
                audio_dur = probe.duration
                if audio_dur <= 0.0 and probe.primary_audio:
                    audio_dur = probe.primary_audio.duration
            except Exception as probe_err:
                logger.warning("No se pudo sondear la duración del audio: %s", probe_err)
                audio_dur = float(duration_sec or 30.0)

            actual_total_frames = max(1, math.ceil((audio_dur + 0.5) * fps))
            actual_duration_sec = actual_total_frames / fps
        elif duration_sec is not None:
            actual_duration_sec = float(duration_sec)
            actual_total_frames = max(1, int(round(actual_duration_sec * fps)))
        else:
            # Fallback based on scenes duration or 30s
            scene_dur = sum(getattr(s, "duration_sec", 0.0) for s in getattr(script_contract, "scenes", []))
            actual_duration_sec = float(scene_dur) if scene_dur > 0 else 30.0
            actual_total_frames = max(1, int(round(actual_duration_sec * fps)))

        logger.info(
            "Iniciando renderizado directo a FFmpeg stdin: %dx%d @ %dfps (%.2fs = %d frames)",
            width, height, fps, actual_duration_sec, actual_total_frames
        )

        html_content = self.shader_renderer.build_runtime_html(
            script_contract=script_contract,
            width=width,
            height=height,
            fps=fps,
        )

        # Build FFmpeg command
        if stream_format == "rawvideo":
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-v", "warning",
                "-f", "rawvideo",
                "-pix_fmt", "rgba",
                "-s", f"{width}x{height}",
                "-r", str(fps),
                "-i", "-",
            ]
        else:
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-v", "warning",
                "-f", "image2pipe",
                "-vcodec", "png",
                "-r", str(fps),
                "-i", "-",
            ]

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
            ffmpeg_cmd.extend([
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-ac", "2",
            ])
        else:
            ffmpeg_cmd.extend(["-an"])

        # Restrict output to exact duration derived from frames
        ffmpeg_cmd.extend(["-t", f"{actual_duration_sec:.3f}"])
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
            register_process(proc)
            browser = None

            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(**launch_kwargs)
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.set_content(html_content, wait_until="domcontentloaded")

                    for frame_idx in range(actual_total_frames):
                        page.evaluate(
                            "([f, total]) => { window.renderFrame(f, total); }",
                            [frame_idx, actual_total_frames],
                        )
                        frame_bytes = page.screenshot(type="png")
                        
                        # Backpressure flow control on FFmpeg stdin
                        written = self._write_frame_with_backpressure(proc, frame_bytes)
                        if not written:
                            logger.info("FFmpeg pipe cerrado por el receptor en fotograma %d", frame_idx)
                            break

                    browser.close()
                    browser = None

                try:
                    if proc.stdin:
                        proc.stdin.flush()
                        proc.stdin.close()
                except (BrokenPipeError, OSError):
                    pass

                proc.wait()

                if proc.returncode != 0:
                    err_msg = log_file_path.read_text(encoding="utf-8", errors="ignore") if log_file_path.exists() else "Unknown"
                    raise RuntimeError(
                        f"FFmpeg pipeline error (code {proc.returncode}): {err_msg}"
                    )
            finally:
                if browser is not None:
                    with contextlib.suppress(Exception):
                        browser.close()
                cleanup_subprocesses(proc)

        elapsed = time.time() - start_time
        fps_eff = actual_total_frames / max(0.1, elapsed)
        logger.info("✅ Video renderizado con éxito en %.2fs (%.1f fps): %s (%d KB)", elapsed, fps_eff, out_p.name, out_p.stat().st_size // 1024)

        return out_p

    def _write_frame_with_backpressure(
        self,
        proc: subprocess.Popen,
        frame_bytes: bytes,
        timeout: float = 10.0,
    ) -> bool:
        """
        Pipes frame bytes to FFmpeg stdin with backpressure throttling.
        Uses select to pause frame generation when OS pipe buffer is saturated.
        """
        if proc.poll() is not None or proc.stdin is None:
            return False

        deadline = time.monotonic() + timeout
        try:
            fd = proc.stdin.fileno()
            # Wait for pipe buffer to be writable (backpressure handling)
            while True:
                if proc.poll() is not None:
                    return False
                if time.monotonic() >= deadline:
                    return False
                remaining = max(0.0, deadline - time.monotonic())
                _, writable, _ = select.select([], [fd], [], min(remaining, 0.5))
                if writable:
                    break
                if time.monotonic() >= deadline:
                    return False
                # Buffer full: throttle producer to allow FFmpeg encoder to catch up
                time.sleep(0.002)

            proc.stdin.write(frame_bytes)
            proc.stdin.flush()
            return True
        except (BrokenPipeError, OSError) as e:
            logger.debug("Pipe write interrupted or closed: %s", e)
            return False

