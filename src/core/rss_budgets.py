"""Near-zero-RAM budgets for live path (stages 8–9).

Baselines from Live smoke (#45 / worktree, 2026-09-05):
  - select (8): ~87.7 MB process, Δ+0.6 MB
  - lavfi synth 2s (9): ~84.5 MB process, Δ+0.8 MB
  - steady process ≈ 84–88 MB; live path barely adds

CI ceilings keep headroom for runner baseline + FFmpeg children while still
catching InMemoryCompositor (~25 MB) / numpy-per-frame bombs. Absolute peak
stays well under docker-compose.small mem_limit (2g).
"""

from __future__ import annotations

import os

# Live-measured steady-state process RSS for select/create smoke (MB).
LIVE_SMOKE_PROCESS_RSS_MB = 88.0

# Per-stage parent RSS delta ceilings (MB) for CI regression.
LIVE_STAGE8_SELECT_DELTA_MB_MAX = float(os.environ.get("YT_LIVE_RSS_DELTA_MB", "16"))
LIVE_STAGE9_LAVFI_DELTA_MB_MAX = float(os.environ.get("YT_LIVE_RSS_DELTA_MB", "16"))

# Peak parent RSS during the live smoke (MB). Env override for tight local runs.
LIVE_SMOKE_PEAK_RSS_MB_MAX = float(os.environ.get("YT_LIVE_RSS_PEAK_MB", "540"))

# Soft align with compose small path (not a hard OOM proxy in unit CI).
COMPOSE_SMALL_MEM_LIMIT_MB = 2048.0
