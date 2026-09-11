"""Bounded concurrency semaphores for FFmpeg video rendering.

Isolates heavy longform FFmpeg encoding (N=1) from lightweight stream-copy
Short composition (N=2) so pipeline stages (ingest, TTS, QA, upload) run
concurrently without head-of-line blocking.
"""

from __future__ import annotations

import threading

# Heavy render semaphore: 1 concurrent longform render (prevents CPU saturation)
_LONG_RENDER_SEMAPHORE = threading.Semaphore(1)

# Light render semaphore: up to 2 concurrent stream-copy / short renders
_SHORT_RENDER_SEMAPHORE = threading.Semaphore(2)
