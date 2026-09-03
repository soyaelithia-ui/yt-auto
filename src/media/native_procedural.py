"""
Native Procedural Engine for yt-auto Visual Pipeline.
Provides GPU-accelerated and CPU-fallback (Mesa Lavapipe) WGSL shader rendering
with 64-byte std140 uniform buffer alignment and 256-byte row stride zero-allocation extraction.
"""

from __future__ import annotations

import logging
import os
import struct
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import wgpu

logger = logging.getLogger(__name__)

DEFAULT_SHADERS_DIR = Path(__file__).resolve().parent / "shaders"
VALID_ARCHETYPES = {
    "arcade_vector_flight",
    "arctic_desolation",
    "cosmic_singularity",
    "cozy_hearth",
    "dark_forest",
    "maritime_lighthouse",
    "parkour_runner",
    "synaptic_network",
    "tactical_chamber",
}

DEFAULT_ACCENT_COLORS: Dict[str, Tuple[float, float, float]] = {
    "arcade_vector_flight": (0.0, 1.0, 0.65),
    "arctic_desolation": (0.6, 0.8, 0.95),
    "cosmic_singularity": (0.9, 0.4, 0.1),
    "cozy_hearth": (1.0, 0.45, 0.15),
    "dark_forest": (0.1, 0.9, 0.4),
    "maritime_lighthouse": (0.0, 0.9, 1.0),
    "parkour_runner": (1.0, 0.25, 0.6),
    "synaptic_network": (0.1, 0.8, 1.0),
    "tactical_chamber": (1.0, 0.2, 0.1),
}


class NativeProceduralEngine:
    """
    WebGPU-based procedural visual engine supporting hardware acceleration
    and deterministic Mesa Lavapipe software rasterization fallback.
    """

    def __init__(
        self,
        shaders_dir: Optional[Union[str, Path]] = None,
        force_software: bool = False,
    ) -> None:
        self.shaders_dir = Path(shaders_dir) if shaders_dir else DEFAULT_SHADERS_DIR
        self.force_software = force_software
        self._lock = threading.RLock()

        # 1. Setup Vulkan Software Driver Fallback if requested or on headless host
        lvp_path = Path("/usr/share/vulkan/icd.d/lvp_icd.json")
        if force_software or "VK_ICD_FILENAMES" not in os.environ:
            if lvp_path.exists():
                os.environ.setdefault("VK_ICD_FILENAMES", str(lvp_path))

        # 2. Acquire Adapter
        adapter = None
        if not force_software:
            try:
                adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
            except Exception as e:
                logger.warning("Hardware GPU adapter request failed: %s. Trying software fallback.", e)

        if not adapter:
            if lvp_path.exists():
                os.environ["VK_ICD_FILENAMES"] = str(lvp_path)
            try:
                adapter = wgpu.gpu.request_adapter_sync(power_preference="low-power")
            except Exception as e:
                logger.error("Software adapter request failed: %s", e)

        if not adapter:
            raise RuntimeError(
                "No WebGPU adapter available. Ensure Vulkan drivers or Mesa Lavapipe (/usr/share/vulkan/icd.d/lvp_icd.json) are installed."
            )

        self.adapter = adapter
        self.adapter_summary = getattr(adapter, "summary", "Unknown Adapter")
        logger.info("NativeProceduralEngine initialized with adapter: %s", self.adapter_summary)

        # 3. Create Device
        self.device = adapter.request_device_sync()

        # 4. Resource caches
        self._pipelines: Dict[str, Any] = {}
        self._cached_res: Optional[Tuple[int, int]] = None
        self._texture: Optional[Any] = None
        self._texture_view: Optional[Any] = None
        self._staging_buf: Optional[Any] = None
        self._bytes_per_row: int = 0

        # 5. Fixed 64-byte Uniform Buffer & Bind Group Layout
        self._uniform_buf = self.device.create_buffer(
            size=64,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )
        self._bgl = self.device.create_bind_group_layout(
            entries=[
                {
                    "binding": 0,
                    "visibility": wgpu.ShaderStage.FRAGMENT,
                    "buffer": {"type": wgpu.BufferBindingType.uniform},
                }
            ]
        )
        self._bind_group = self.device.create_bind_group(
            layout=self._bgl,
            entries=[
                {
                    "binding": 0,
                    "resource": {"buffer": self._uniform_buf, "offset": 0, "size": 64},
                }
            ],
        )
        self._pipeline_layout = self.device.create_pipeline_layout(bind_group_layouts=[self._bgl])

    def get_available_archetypes(self) -> List[str]:
        """Return list of supported visual archetype identifiers."""
        return sorted(list(VALID_ARCHETYPES))

    def _load_shader_code(self, archetype_id: str) -> str:
        """Load WGSL shader source code from catalog."""
        shader_file = self.shaders_dir / f"{archetype_id}.wgsl"
        if not shader_file.exists():
            raise KeyError(f"Shader file not found for archetype: '{archetype_id}' at {shader_file}")
        return shader_file.read_text(encoding="utf-8")

    def _get_pipeline(self, archetype_id: str) -> Any:
        """Retrieve or lazily compile render pipeline for the given archetype."""
        if archetype_id in self._pipelines:
            return self._pipelines[archetype_id]

        code = self._load_shader_code(archetype_id)
        shader_module = self.device.create_shader_module(code=code)
        pipeline = self.device.create_render_pipeline(
            layout=self._pipeline_layout,
            vertex={"module": shader_module, "entry_point": "vs_main", "buffers": []},
            fragment={
                "module": shader_module,
                "entry_point": "fs_main",
                "targets": [{"format": wgpu.TextureFormat.rgba8unorm}],
            },
            primitive={"topology": wgpu.PrimitiveTopology.triangle_list},
        )
        self._pipelines[archetype_id] = pipeline
        return pipeline

    def render_frame(
        self,
        width: int,
        height: int,
        time_sec: float,
        duration_sec: float,
        archetype_id: str,
        tension: int = 1,
        seed: int = 42,
        params: Optional[Dict[str, Any]] = None,
        out_buffer: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """
        Render a single RGBA frame for the requested archetype at time_sec.
        Renders in-place into out_buffer if provided.
        """
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid frame dimensions: {width}x{height}. Width and height must be > 0.")
        if duration_sec <= 0.0:
            raise ValueError(f"duration_sec must be > 0, got {duration_sec}")
        if archetype_id not in VALID_ARCHETYPES:
            raise KeyError(f"Unknown archetype_id: '{archetype_id}'. Valid archetypes: {sorted(list(VALID_ARCHETYPES))}")

        with self._lock:
            # 1. Reallocate Texture & Staging Buffer if resolution changed
            if self._cached_res != (width, height):
                self._bytes_per_row = (width * 4 + 255) & ~255
                self._staging_buf = self.device.create_buffer(
                    size=self._bytes_per_row * height,
                    usage=wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ,
                )
                self._texture = self.device.create_texture(
                    size=(width, height, 1),
                    format=wgpu.TextureFormat.rgba8unorm,
                    usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC,
                )
                self._texture_view = self._texture.create_view()
                self._cached_res = (width, height)

            # 2. Pack 64-byte Uniform Buffer (std140: 16 x float32)
            default_accent = DEFAULT_ACCENT_COLORS.get(archetype_id, (1.0, 1.0, 1.0))
            accent_r, accent_g, accent_b = default_accent

            noise_scale = 1.0
            speed = 1.0
            distortion = 1.0
            glow_intensity = 1.0
            custom_1 = 0.0
            custom_2 = 0.0
            custom_3 = 0.0

            if params and isinstance(params, dict):
                if "noise_scale" in params:
                    noise_scale = float(params["noise_scale"])
                if "speed" in params:
                    speed = float(params["speed"])
                if "distortion" in params:
                    distortion = float(params["distortion"])
                if "glow_intensity" in params:
                    glow_intensity = float(params["glow_intensity"])
                if "custom_1" in params:
                    custom_1 = float(params["custom_1"])
                if "custom_2" in params:
                    custom_2 = float(params["custom_2"])
                if "custom_3" in params:
                    custom_3 = float(params["custom_3"])
                if "kelvin" in params:
                    try:
                        custom_1 = float(params["kelvin"]) / 10000.0
                    except (ValueError, TypeError):
                        pass

                raw_accent = params.get("accent_color") or params.get("accentColor") or params.get("u_palette_accent")
                if raw_accent is not None:
                    if isinstance(raw_accent, (list, tuple)) and len(raw_accent) >= 3:
                        accent_r, accent_g, accent_b = float(raw_accent[0]), float(raw_accent[1]), float(raw_accent[2])
                    elif isinstance(raw_accent, str) and raw_accent.startswith("#") and len(raw_accent) == 7:
                        try:
                            accent_r = int(raw_accent[1:3], 16) / 255.0
                            accent_g = int(raw_accent[3:5], 16) / 255.0
                            accent_b = int(raw_accent[5:7], 16) / 255.0
                        except ValueError:
                            pass
                if "accent_r" in params:
                    accent_r = float(params["accent_r"])
                if "accent_g" in params:
                    accent_g = float(params["accent_g"])
                if "accent_b" in params:
                    accent_b = float(params["accent_b"])

            uniform_bytes = struct.pack(
                "16f",
                float(width),
                float(height),
                float(time_sec),
                float(duration_sec),
                float(seed),
                float(tension),
                float(noise_scale),
                float(speed),
                float(accent_r),
                float(accent_g),
                float(accent_b),
                float(distortion),
                float(glow_intensity),
                float(custom_1),
                float(custom_2),
                float(custom_3),
            )
            self.device.queue.write_buffer(self._uniform_buf, 0, uniform_bytes)

            # 3. Encode & Submit Render Pass
            pipeline = self._get_pipeline(archetype_id)
            command_encoder = self.device.create_command_encoder()
            render_pass = command_encoder.begin_render_pass(
                color_attachments=[
                    {
                        "view": self._texture_view,
                        "load_op": wgpu.LoadOp.clear,
                        "store_op": wgpu.StoreOp.store,
                        "clear_value": (0.0, 0.0, 0.0, 1.0),
                    }
                ]
            )
            render_pass.set_pipeline(pipeline)
            render_pass.set_bind_group(0, self._bind_group)
            render_pass.draw(3, 1, 0, 0)
            render_pass.end()

            # 4. Copy Texture to Staging Buffer
            command_encoder.copy_texture_to_buffer(
                {"texture": self._texture, "mip_level": 0, "origin": (0, 0, 0)},
                {"buffer": self._staging_buf, "offset": 0, "bytes_per_row": self._bytes_per_row, "rows_per_image": height},
                (width, height, 1),
            )
            self.device.queue.submit([command_encoder.finish()])

            # 5. Zero-Allocation Readback
            self._staging_buf.map_sync(wgpu.MapMode.READ)
            mapped_view = self._staging_buf.read_mapped()

            if out_buffer is None:
                out_buffer = np.empty((height, width, 4), dtype=np.uint8)
            else:
                if out_buffer.shape != (height, width, 4) or out_buffer.dtype != np.uint8:
                    raise ValueError(
                        f"out_buffer shape {out_buffer.shape} or dtype {out_buffer.dtype} mismatch. "
                        f"Expected {(height, width, 4)} of uint8."
                    )

            raw_2d = np.frombuffer(mapped_view, dtype=np.uint8).reshape((height, self._bytes_per_row))
            if self._bytes_per_row == width * 4:
                out_buffer[:] = raw_2d.reshape((height, width, 4))
            else:
                out_buffer[:] = raw_2d[:, : width * 4].reshape((height, width, 4))

            self._staging_buf.unmap()
            return out_buffer

    def render_video_loop(
        self,
        archetype_id: str,
        output_path: Union[str, Path],
        duration_sec: float = 6.0,
        fps: int = 30,
        width: int = 1080,
        height: int = 1920,
        tension: int = 1,
        seed: int = 42,
        params: Optional[Dict[str, Any]] = None,
        crf: int = 18,
        preset: str = "fast",
    ) -> Path:
        """
        Renders a complete procedural video loop for archetype_id directly to MP4.
        Streams raw RGBA frames to an FFmpeg subprocess for ultra-fast zero-disk-overhead rendering.
        """
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        total_frames = int(round(duration_sec * fps))

        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{width}x{height}",
            "-pix_fmt", "rgba",
            "-r", str(fps),
            "-i", "-",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", str(crf),
            "-preset", preset,
            "-movflags", "+faststart",
            str(out_p),
        ]

        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        buf = np.empty((height, width, 4), dtype=np.uint8)

        try:
            for frame_idx in range(total_frames):
                t_sec = frame_idx / float(fps)
                self.render_frame(
                    width=width,
                    height=height,
                    time_sec=t_sec,
                    duration_sec=duration_sec,
                    archetype_id=archetype_id,
                    tension=tension,
                    seed=seed,
                    params=params,
                    out_buffer=buf,
                )
                if proc.stdin:
                    proc.stdin.write(buf.tobytes())
            if proc.stdin:
                proc.stdin.close()
            stderr = proc.stderr.read() if proc.stderr else b""
            ret = proc.wait()
            if ret != 0:
                err_msg = stderr.decode("utf-8", errors="replace") if stderr else "Unknown error"
                raise RuntimeError(f"FFmpeg render failed with exit code {ret}: {err_msg}")
        except Exception:
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=2.0)
                except Exception:
                    pass
            raise

        return out_p

    def render_loop(
        self,
        template_name: Optional[str] = None,
        category: Optional[str] = None,
        orientation: Optional[str] = None,
        width: int = 1080,
        height: int = 1920,
        duration_sec: float = 6.0,
        fps: int = 30,
        output_path: Union[str, Path] = "output.mp4",
        params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Path:
        """Compatibility wrapper conforming to ProceduralVideoEngine renderer contract."""
        arch_id = template_name if (template_name and template_name in VALID_ARCHETYPES) else (category or "dark_forest")
        if arch_id not in VALID_ARCHETYPES:
            arch_id = "dark_forest"
        tension = int(params.get("tension", 1)) if params else 1
        seed = int(params.get("seed", 42)) if params else 42
        return self.render_video_loop(
            archetype_id=arch_id,
            output_path=output_path,
            duration_sec=duration_sec,
            fps=fps,
            width=width,
            height=height,
            tension=tension,
            seed=seed,
            params=params,
        )

    def close(self) -> None:
        """Release device resources and cached buffers."""
        with self._lock:
            self._pipelines.clear()
            self._texture = None
            self._texture_view = None
            self._staging_buf = None
            self._cached_res = None

    def __enter__(self) -> "NativeProceduralEngine":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
