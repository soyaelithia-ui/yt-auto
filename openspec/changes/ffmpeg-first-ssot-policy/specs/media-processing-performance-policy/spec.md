# Delta for Media Processing Performance Policy

## MODIFIED Requirements

### Requirement: Native Procedural and Vector Rendering (Zero-Browser Policy)
Production video synthesis MUST use FFmpeg (lavfi/catalog loops, concat demuxer `-c:v copy` when `stream_copy_mode`, `DIRECTOR_SINGLE_PASS` assembly, libass subtitles). wgpu-py, resvg-py, WebGPU, and GLSL MUST NOT be the production stack; they MAY run only when `ENABLE_NATIVE_PROCEDURAL` is explicitly enabled from `src/media/_legacy`. Headless browser runtimes (Playwright, Puppeteer, Chromium, SwiftShader) and HTML/CSS web templates are strictly prohibited in the media generation pipeline.
(Previously: Production video MUST use wgpu-py fragment shaders with Lavapipe fallback and resvg-py SVG rasterization.)

#### Scenario: Procedural Rendering without Browser Subprocesses
- **Given** a video scene requiring procedural backgrounds or HUD telemetry
- **When** the media pipeline generates visual frames
- **Then** frames MUST be produced via FFmpeg lavfi/catalog (HUD via `drawtext`/`drawbox` when `niche_hud` is present)
- **And** zero browser subprocesses or Chromium dependencies MUST be spawned
- **And** wgpu-py and resvg-py MUST NOT be required on the production hot path.

### Requirement: Atomic Single-Pass Video Transcoding and Asynchronous Pipe Drain
When `stream_copy_mode` is true, production MUST assemble with concat demuxer `-c:v copy` and MUST NOT force a single `-filter_complex` of raw RGBA streaming. When encode is required (HUD, scale, xfade, or burned subtitles), FFmpeg MUST use one encode pass (`encode_defaults` veryfast/CRF 21) with libass and EBU R128 as applicable, and MUST drain `stderr` asynchronously. Intermediate MP4 chunks on disk remain prohibited. Raw RGBA stdin streaming MAY run only when `ENABLE_NATIVE_PROCEDURAL` is enabled.
(Previously: Every encode MUST be one -filter_complex combining raw RGBA streaming, libass, ducking, and EBU R128.)

#### Scenario: Homogeneous beats stay stream-copy (Happy Path)
- **Given** horizontal orientation, no burned subtitles, and no `niche_hud`
- **When** beats/loop composition runs
- **Then** FFmpeg MUST use concat demuxer `-c:v copy`
- **And** MUST NOT require raw RGBA stdin.
