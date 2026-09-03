"""
Zero-allocation In-Memory Frame Compositor for yt-auto Visual Pipeline.
Performs SIMD Porter-Duff Over alpha blending between base procedural frames
and vector overlays, providing zero-copy memoryviews for direct FFmpeg pipe streaming.
"""

from __future__ import annotations

from typing import Optional
import numpy as np


class InMemoryCompositor:
    """
    Composites base procedural frames with vector overlays in host memory
    using zero-allocation pre-allocated buffers and SIMD alpha blending.
    Streams directly to FFmpeg stdin via memoryview.
    """

    def __init__(self, width: int = 1080, height: int = 1920) -> None:
        self.width = width
        self.height = height
        self._base_buffer = np.zeros((height, width, 4), dtype=np.uint8)
        self._overlay_buffer = np.zeros((height, width, 4), dtype=np.uint8)
        self._out_buffer = np.zeros((height, width, 4), dtype=np.uint8)

    @property
    def out_buffer(self) -> np.ndarray:
        """Returns the composite output frame buffer."""
        return self._out_buffer

    @property
    def base_buffer(self) -> np.ndarray:
        """Returns the base layer frame buffer."""
        return self._base_buffer

    @property
    def overlay_buffer(self) -> np.ndarray:
        """Returns the overlay layer frame buffer."""
        return self._overlay_buffer

    def composite_frame(
        self,
        base_rgba: np.ndarray,
        overlay_rgba: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """
        Blend base_rgba and overlay_rgba using Porter-Duff Over.
        Operates in-place on self._out_buffer and returns it.
        """
        # Dynamically adjust buffer dimensions if input dimensions changed
        if base_rgba.shape[0] != self.height or base_rgba.shape[1] != self.width:
            self.height, self.width = base_rgba.shape[0], base_rgba.shape[1]
            self._base_buffer = np.zeros((self.height, self.width, 4), dtype=np.uint8)
            self._overlay_buffer = np.zeros((self.height, self.width, 4), dtype=np.uint8)
            self._out_buffer = np.zeros((self.height, self.width, 4), dtype=np.uint8)

        # Fast path 1: No overlay provided
        if overlay_rgba is None:
            np.copyto(self._out_buffer, base_rgba)
            return self._out_buffer

        a_overlay = overlay_rgba[:, :, 3]

        # Fast path 2: Overlay is completely transparent (all alpha == 0)
        if not np.any(a_overlay):
            np.copyto(self._out_buffer, base_rgba)
            return self._out_buffer

        # Fast path 3: Overlay is completely solid (all alpha == 255)
        if np.all(a_overlay == 255):
            np.copyto(self._out_buffer, overlay_rgba)
            return self._out_buffer

        # Copy base into out buffer
        np.copyto(self._out_buffer, base_rgba)
        nz_mask = a_overlay > 0

        # Fast path 4: All non-zero overlay pixels are 100% solid
        if np.all(a_overlay[nz_mask] == 255):
            self._out_buffer[nz_mask] = overlay_rgba[nz_mask]
            return self._out_buffer

        # Vectorized Porter-Duff Over alpha blending for non-zero pixels
        alpha_over = a_overlay[nz_mask].astype(np.float32) / 255.0
        inv_alpha = 1.0 - alpha_over
        base_nz = base_rgba[nz_mask]
        over_nz = overlay_rgba[nz_mask]

        for c in range(3):
            self._out_buffer[nz_mask, c] = np.clip(
                over_nz[:, c].astype(np.float32) * alpha_over + base_nz[:, c].astype(np.float32) * inv_alpha + 0.5,
                0,
                255,
            ).astype(np.uint8)

        alpha_dst = base_nz[:, 3].astype(np.float32) / 255.0
        alpha_out = alpha_over + alpha_dst * inv_alpha
        self._out_buffer[nz_mask, 3] = np.clip(alpha_out * 255.0 + 0.5, 0, 255).astype(np.uint8)
        return self._out_buffer

    def get_memoryview(self) -> memoryview:
        """
        Returns a contiguous 1D byte memoryview of length width * height * 4
        for zero-copy streaming directly to FFmpeg stdin pipe.
        """
        return memoryview(self._out_buffer).cast("B")
