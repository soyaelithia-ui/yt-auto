"""
src/media/unified_encoder.py - Single-Pass Atomic FFmpeg Encoder Pipeline.
Combines rawvideo stdin, ASS typography burning (libass), audio ducking, and EBU R128 normalization.
"""

from __future__ import annotations

import collections
import os
import subprocess
import threading
from pathlib import Path
from src.media.encode_defaults import default_render_crf, default_render_preset
from src.media.subtitles_ass import libass_filter_clause
from typing import Any, List, Optional, Tuple, Union
import numpy as np


class UnifiedEncoder:
    """Single-pass atomic FFmpeg encoder with background stderr draining and safe broken pipe handling."""

    def __init__(
        self,
        output_mp4: Union[str, Path],
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        crf: int | None = None,
        preset: str | None = None,
        voice_wav: Optional[Union[str, Path]] = None,
        drone_wav: Optional[Union[str, Path]] = None,
        sfx_wavs: Optional[List[Tuple[Union[str, Path], float, float]]] = None,
        ass_subtitle_path: Optional[Union[str, Path]] = None,
        fonts_dir: Optional[Union[str, Path]] = None,
        enable_nvenc: bool = False,
    ) -> None:
        self.output_mp4 = Path(output_mp4)
        self.width = width
        self.height = height
        self.fps = fps
        self.crf = default_render_crf() if crf is None else crf
        self.preset = default_render_preset() if preset is None else preset
        self.voice_wav = Path(voice_wav) if voice_wav else None
        self.drone_wav = Path(drone_wav) if drone_wav else None
        self.sfx_wavs = sfx_wavs or []
        self.ass_subtitle_path = Path(ass_subtitle_path) if ass_subtitle_path else None
        self.fonts_dir = Path(fonts_dir) if fonts_dir else (Path("assets/fonts") if Path("assets/fonts").exists() else None)
        self.enable_nvenc = enable_nvenc

        self.expected_frame_bytes = self.width * self.height * 4

        self.proc: Optional[subprocess.Popen] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._stderr_lines: collections.deque = collections.deque(maxlen=100)
        self._is_started = False
        self._is_finished = False

    def build_ffmpeg_command(self) -> List[str]:
        """Construct the atomic FFmpeg execution command with single-pass filter_complex."""
        cmd = ["ffmpeg", "-y", "-loglevel", "warning"]

        # Input 0: Raw RGBA video from pipe
        cmd.extend([
            "-f", "rawvideo",
            "-pix_fmt", "rgba",
            "-s", f"{self.width}x{self.height}",
            "-r", str(self.fps),
            "-i", "pipe:0",
        ])

        input_idx = 1
        voice_idx: Optional[int] = None
        drone_idx: Optional[int] = None
        sfx_indices: List[Tuple[int, float, float]] = []

        if self.voice_wav and self.voice_wav.exists():
            cmd.extend(["-i", str(self.voice_wav)])
            voice_idx = input_idx
            input_idx += 1

        if self.drone_wav and self.drone_wav.exists():
            cmd.extend(["-i", str(self.drone_wav)])
            drone_idx = input_idx
            input_idx += 1

        for sfx_item in self.sfx_wavs:
            sfx_path, offset_sec, vol = sfx_item
            p = Path(sfx_path)
            if p.exists():
                cmd.extend(["-i", str(p)])
                sfx_indices.append((input_idx, float(offset_sec), float(vol)))
                input_idx += 1

        filter_chains: List[str] = []

        # 1. Video Filter: libass subtitle burn-in (unquoted FFmpeg 6.1 paths)
        if self.ass_subtitle_path and self.ass_subtitle_path.exists():
            fonts = self.fonts_dir if self.fonts_dir and self.fonts_dir.exists() else None
            filter_chains.append(f"[0:v]{libass_filter_clause(self.ass_subtitle_path, fonts)}[v]")
        else:
            filter_chains.append("[0:v]null[v]")

        # 2. Audio Filter: SFX delays, sidechain ducking, amix, and loudnorm
        audio_mix_inputs: List[str] = []

        # Process SFX inputs with adelay & volume
        for idx_num, (s_idx, offset_sec, vol) in enumerate(sfx_indices):
            delay_ms = int(round(max(0.0, offset_sec) * 1000))
            vol_clean = max(0.0, min(5.0, vol))
            filter_chains.append(f"[{s_idx}:a]volume={vol_clean:.2f},adelay={delay_ms}|{delay_ms}[sfx_{idx_num}]")
            audio_mix_inputs.append(f"[sfx_{idx_num}]")

        if voice_idx is not None and drone_idx is not None:
            # Sidechain compress drone with voice
            filter_chains.append(
                f"[{drone_idx}:a][{voice_idx}:a]sidechaincompress=threshold=0.125:ratio=4:attack=50:release=300[ducked_drone]"
            )
            audio_mix_inputs.insert(0, f"[{voice_idx}:a]")
            audio_mix_inputs.insert(1, "[ducked_drone]")
        elif voice_idx is not None:
            audio_mix_inputs.insert(0, f"[{voice_idx}:a]")
        elif drone_idx is not None:
            audio_mix_inputs.insert(0, f"[{drone_idx}:a]")

        has_audio = len(audio_mix_inputs) > 0
        if has_audio:
            if len(audio_mix_inputs) > 1:
                inputs_str = "".join(audio_mix_inputs)
                filter_chains.append(
                    f"{inputs_str}amix=inputs={len(audio_mix_inputs)}:duration=first:dropout_transition=2[amix_raw]"
                )
                filter_chains.append("[amix_raw]loudnorm=I=-16:TP=-1.5:LRA=11[a]")
            else:
                single_in = audio_mix_inputs[0]
                filter_chains.append(f"{single_in}loudnorm=I=-16:TP=-1.5:LRA=11[a]")

        cmd.extend(["-filter_complex", ";".join(filter_chains)])
        cmd.extend(["-map", "[v]"])

        if has_audio:
            cmd.extend(["-map", "[a]"])
            cmd.extend(["-c:a", "aac", "-b:a", "192k", "-ar", "44100"])

        if self.enable_nvenc:
            cmd.extend(["-c:v", "h264_nvenc", "-preset", "p4", "-cq", str(self.crf)])
        else:
            cmd.extend(["-c:v", "libx264", "-preset", self.preset, "-crf", str(self.crf)])

        cmd.extend([
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(self.output_mp4),
        ])

        return cmd

    def _drain_stderr(self) -> None:
        """Background worker thread draining stderr continuously to prevent pipe buffer deadlocks."""
        if not self.proc or not self.proc.stderr:
            return
        try:
            for line in iter(self.proc.stderr.readline, b""):
                decoded = line.decode("utf-8", errors="replace").strip()
                if decoded:
                    self._stderr_lines.append(decoded)
        except Exception:
            pass

    def get_stderr_tail(self) -> str:
        """Return the last captured lines of FFmpeg stderr output."""
        return "\n".join(self._stderr_lines)

    def start(self) -> None:
        """Start the FFmpeg subprocess and background stderr reader."""
        if self._is_started:
            return
        self.output_mp4.parent.mkdir(parents=True, exist_ok=True)
        cmd = self.build_ffmpeg_command()
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            bufsize=10 * 1024 * 1024,
        )
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()
        self._is_started = True

    def write_frame(self, frame_data: Union[bytes, memoryview, np.ndarray]) -> None:
        """Write a raw RGBA frame directly to the FFmpeg stdin pipe."""
        if not self._is_started:
            self.start()

        if self.proc is None or self.proc.stdin is None:
            raise RuntimeError("FFmpeg process is not running")

        if self.proc.poll() is not None:
            raise RuntimeError(f"FFmpeg process terminated prematurely with code {self.proc.returncode}: {self.get_stderr_tail()}")

        if isinstance(frame_data, np.ndarray):
            raw_bytes = frame_data.tobytes()
        elif isinstance(frame_data, memoryview):
            raw_bytes = frame_data
        elif isinstance(frame_data, bytes):
            raw_bytes = frame_data
        else:
            raise ValueError(f"Unsupported frame data type: {type(frame_data)}")

        if len(raw_bytes) != self.expected_frame_bytes:
            raise ValueError(
                f"Frame size mismatch: expected {self.expected_frame_bytes} bytes "
                f"({self.width}x{self.height}x4), got {len(raw_bytes)} bytes"
            )

        try:
            self.proc.stdin.write(raw_bytes)
        except (BrokenPipeError, OSError) as exc:
            self.proc.poll()
            raise RuntimeError(f"FFmpeg BrokenPipeError during frame write: {self.get_stderr_tail()}") from exc

    def finish(self) -> None:
        """Close stdin, wait for FFmpeg transcoding completion, and ensure valid exit."""
        if self._is_finished:
            return
        self._is_finished = True

        if not self._is_started or self.proc is None:
            return

        if self.proc.stdin:
            try:
                self.proc.stdin.close()
            except Exception:
                pass

        try:
            retcode = self.proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            raise RuntimeError(f"FFmpeg timed out: {self.get_stderr_tail()}")

        if self._stderr_thread and self._stderr_thread.is_alive():
            self._stderr_thread.join(timeout=2.0)

        if retcode != 0:
            raise RuntimeError(f"FFmpeg failed with return code {retcode}:\n{self.get_stderr_tail()}")

    def __enter__(self) -> "UnifiedEncoder":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            if self.proc:
                try:
                    self.proc.kill()
                    self.proc.wait(timeout=5.0)
                except Exception:
                    pass
        else:
            self.finish()
