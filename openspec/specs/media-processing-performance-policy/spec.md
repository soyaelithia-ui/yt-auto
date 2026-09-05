# Spec: Media Processing and Performance Policy

## Requirement: Volatile RAM-Based Audio Temp Storage (`/dev/shm`)
Intermediate audio files, silence chunks, and dramatic pause concatenation buffers MUST be allocated in `/dev/shm` (or OS temp directory fallback) to prevent unnecessary SSD I/O wear and reduce latency during TTS processing.

### Scenario: RAM Temp Directory Resolution
- **Given** a Linux host with a writable `/dev/shm` filesystem
- **When** `_get_ram_temp_dir()` is invoked during audio generation
- **Then** the returned directory path MUST reside inside `/dev/shm/yt_auto_audio`
- **And** all intermediate chunk files MUST be deleted from RAM immediately after concatenation.

## Requirement: Single-Pass FFmpeg Audio Mastering
Audio mastering MUST execute in a single consolidated FFmpeg `filter_complex` pass combining voice highpass/lowpass equalization, sidechain ducking under background music, and EBU R128 loudness normalization (Integrated Loudness $I=-14.0\text{ LUFS}$, True Peak $TP=-1.5\text{ dBTP}$, Loudness Range $LRA=11.0$). Double-pass disk renders are strictly prohibited.

### Scenario: Single-Pass Mastering Execution
- **Given** narration speech WAV and background music MP3 inputs
- **When** `master_audio_track` runs
- **Then** FFmpeg MUST emit a stereo 48 kHz master audio file in a single execution pass.

## Requirement: Native Procedural and Vector Rendering (Zero-Browser Policy)
Production video synthesis MUST use FFmpeg (lavfi/catalog loops, concat demuxer `-c:v copy` when `stream_copy_mode`, `DIRECTOR_SINGLE_PASS` assembly, libass subtitles). wgpu-py, resvg-py, WebGPU, and GLSL MUST NOT be the production stack; they MAY run only when `ENABLE_NATIVE_PROCEDURAL` is explicitly enabled from `src/media/_legacy`. Headless browser runtimes (Playwright, Puppeteer, Chromium, SwiftShader) and HTML/CSS web templates are strictly prohibited in the media generation pipeline.

### Scenario: Procedural Rendering without Browser Subprocesses
- **Given** a video scene requiring procedural backgrounds or HUD telemetry
- **When** the media pipeline generates visual frames
- **Then** frames MUST be produced via FFmpeg lavfi/catalog (HUD via `drawtext`/`drawbox` when `niche_hud` is present)
- **And** zero browser subprocesses or Chromium dependencies MUST be spawned
- **And** wgpu-py and resvg-py MUST NOT be required on the production hot path.

## Requirement: libass Subtitle Rendering and Safe Area
Subtitles generated for 9:16 vertical Shorts MUST be compiled into Advanced SubStation Alpha (`.ass`) scripts and burned natively via FFmpeg `libass`. Subtitles MUST enforce bottom UI Safe Area ($MarginV \ge 240\text{px}$, canonical $260\text{px}$) and word-level karaoke timing (`{\kf}`). Frame-by-frame Python/Pillow text rasterization loops are strictly prohibited.

### Scenario: Native libass Subtitle Burn
- **Given** word-level narration timestamps
- **When** subtitles are generated
- **Then** `ASSSubtitleGenerator` MUST emit a compliant `.ass` script with `MarginV >= 240`
- **And** FFmpeg MUST burn subtitles during the unified encoding pass via `libass`.

## Requirement: Atomic Single-Pass Video Transcoding and Asynchronous Pipe Drain
When `stream_copy_mode` is true, production MUST assemble with concat demuxer `-c:v copy` and MUST NOT force a single `-filter_complex` of raw RGBA streaming. When encode is required (HUD, scale, xfade, or burned subtitles), FFmpeg MUST use one encode pass (`encode_defaults` veryfast/CRF 21) with libass and EBU R128 as applicable, and MUST drain `stderr` asynchronously. Intermediate MP4 chunks on disk remain prohibited. Raw RGBA stdin streaming MAY run only when `ENABLE_NATIVE_PROCEDURAL` is enabled.

### Scenario: Homogeneous beats stay stream-copy (Happy Path)
- **Given** horizontal orientation, no burned subtitles, and no `niche_hud`
- **When** beats/loop composition runs
- **Then** FFmpeg MUST use concat demuxer `-c:v copy`
- **And** MUST NOT require raw RGBA stdin.
