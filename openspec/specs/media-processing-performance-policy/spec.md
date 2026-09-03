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
Video synthesis MUST utilize deterministic WebGPU fragment shaders (`wgpu-py`) with CPU software rasterizer fallback (Mesa Lavapipe) and declarative SVG rasterization (`resvg-py`). Headless browser runtimes (Playwright, Puppeteer, Chromium, SwiftShader) and HTML/CSS web templates are strictly prohibited in the media generation pipeline.

### Scenario: Procedural Rendering without Browser Subprocesses
- **Given** a video scene requiring procedural backgrounds or HUD telemetry
- **When** the media pipeline generates visual frames
- **Then** frames MUST be rendered via native WebGPU shaders or `resvg-py`
- **And** zero browser subprocesses or Chromium dependencies MUST be spawned.

## Requirement: libass Subtitle Rendering and Safe Area
Subtitles generated for 9:16 vertical Shorts MUST be compiled into Advanced SubStation Alpha (`.ass`) scripts and burned natively via FFmpeg `libass`. Subtitles MUST enforce bottom UI Safe Area ($MarginV \ge 240\text{px}$, canonical $260\text{px}$) and word-level karaoke timing (`{\kf}`). Frame-by-frame Python/Pillow text rasterization loops are strictly prohibited.

### Scenario: Native libass Subtitle Burn
- **Given** word-level narration timestamps
- **When** subtitles are generated
- **Then** `ASSSubtitleGenerator` MUST emit a compliant `.ass` script with `MarginV >= 240`
- **And** FFmpeg MUST burn subtitles during the unified encoding pass via `libass`.

## Requirement: Atomic Single-Pass Video Transcoding and Asynchronous Pipe Drain
Video encoding MUST execute in a single atomic FFmpeg `-filter_complex` pass combining raw RGBA video streaming, `libass` subtitle burning, audio sidechain ducking, and EBU R128 normalization. The encoder process MUST drain `stderr` asynchronously in a background thread to prevent OS pipe buffer deadlocks. Intermediate MP4 video chunks on disk are strictly prohibited.

### Scenario: Single-Pass Video Generation
- **Given** raw video frames and master audio tracks
- **When** `UnifiedEncoder` renders the final video
- **Then** FFmpeg MUST stream directly to the target MP4 container in a single pass without intermediate disk chunks.
