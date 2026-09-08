# Delta Spec: Loop Engine Pre-baked Master Loops Bank

## ADDED Requirements

### Requirement: Pre-baked 60s Master Loop Resolution
The `LoopVideoEngine` SHALL resolve pre-baked master loops from `assets/loops/` via `LoopCatalogRepository` SQLite database or direct filesystem traversal without executing runtime procedural synthesis or live image-to-video generation.

#### Scenario: Horizontal master loop query
- **Given** an engine initialized with default loops directory `assets/loops/` and category `horror`, `drama`, or `scifi`
- **When** `resolve_loop_video` is invoked with `orientation="horizontal"`
- **Then** the engine SHALL return an existing master loop with duration $\ge 30.0$ seconds and H.264 Main profile.

#### Scenario: Vertical master loop query for Shorts
- **Given** an engine initialized with default loops directory `assets/loops/`
- **When** `resolve_loop_video` is invoked with `orientation="vertical"` for `horror`, `drama`, or `scifi`
- **Then** the engine SHALL return an existing 9:16 vertical master loop with duration $\ge 30.0$ seconds without raising `LoopVideoAssetError`.

### Requirement: Zero-Transcode Profile Alignment
All master loop video files placed into `assets/loops/` SHALL be pre-encoded in H.264 `Main` profile (`yuv420p`, 24fps) with faststart flags.

#### Scenario: YouTube compliance gate bypass
- **Given** a master loop from `assets/loops/`
- **When** `LoopVideoEngine.ensure_h264_main_profile` inspects the asset probe
- **Then** it SHALL recognize profile as `Main` and return the file path immediately without running an FFmpeg transcoding subprocess.
