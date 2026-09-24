# Spec: Media Processing and Performance Policy

## Requirements

### Requirement: Volatile RAM-Based Audio Temp Storage (`/dev/shm`)
Intermediate audio files, silence chunks, and dramatic pause concatenation buffers MUST be allocated in `/dev/shm` (or OS temp directory fallback) to prevent unnecessary SSD I/O wear and reduce latency during TTS processing.

#### Scenario: RAM Temp Directory Resolution
- **Given** a Linux host with a writable `/dev/shm` filesystem
- **When** `_get_ram_temp_dir()` is invoked during audio generation
- **Then** the returned directory path MUST reside inside `/dev/shm/yt_auto_audio`
- **And** all intermediate chunk files MUST be deleted from RAM immediately after concatenation.

### Requirement: Single-Pass FFmpeg Audio Mastering
Audio mastering MUST execute in a single consolidated FFmpeg `filter_complex` pass combining voice highpass/lowpass equalization, sidechain ducking under background music, and EBU R128 loudness normalization (Integrated Loudness $I=-14.0\text{ LUFS}$, True Peak $TP=-1.5\text{ dBTP}$, Loudness Range $LRA=11.0$). Double-pass disk renders are strictly prohibited.

#### Scenario: Single-Pass Mastering Execution
- **Given** narration speech WAV and background music MP3 inputs
- **When** `master_audio_track` runs
- **Then** FFmpeg MUST emit a stereo 48 kHz master audio file in a single execution pass.

### Requirement: Native Procedural and Vector Rendering (Zero-Browser Policy)
Production video synthesis MUST use FFmpeg (lavfi/catalog loops, concat demuxer `-c:v copy` when `stream_copy_mode`, `DIRECTOR_SINGLE_PASS` assembly, libass subtitles). wgpu-py, resvg-py, WebGPU, and GLSL MUST NOT be the production stack; they MAY run only when `ENABLE_NATIVE_PROCEDURAL` is explicitly enabled from `src/media/_legacy`. Headless browser runtimes (Playwright, Puppeteer, Chromium, SwiftShader) and HTML/CSS web templates are strictly prohibited in the media generation pipeline.

#### Scenario: Procedural Rendering without Browser Subprocesses
- **Given** a video scene requiring procedural backgrounds or HUD telemetry
- **When** the media pipeline generates visual frames
- **Then** frames MUST be produced via FFmpeg lavfi/catalog (HUD via `drawtext`/`drawbox` when `niche_hud` is present)
- **And** zero browser subprocesses or Chromium dependencies MUST be spawned
- **And** wgpu-py and resvg-py MUST NOT be required on the production hot path.

### Requirement: libass Subtitle Rendering and Safe Area
Subtitles generated for 9:16 vertical Shorts MUST be compiled into Advanced SubStation Alpha (`.ass`) scripts and burned natively via FFmpeg `libass`. Subtitles generated for 9:16 vertical Shorts MUST enforce bottom UI Safe Area $MarginV \ge 480\text{px}$ (canonical $\ge 25\%$ of canvas height) and $MarginV \ge 130\text{px}$ for 16:9 horizontal video, scaled with procedural 2.5D camera drift offsets to ensure clearance above player UI controls. Subtitles MUST enforce word-level karaoke timing (`{\kf}`). Frame-by-frame Python/Pillow text rasterization loops are strictly prohibited.

#### Scenario: Native libass subtitle burn for 9:16 vertical Shorts (Happy Path)
- **Given** word-level narration timestamps for a 9:16 vertical Short ($1080\times 1920$)
- **When** subtitles are generated
- **Then** `ASSSubtitleGenerator` MUST emit a compliant `.ass` script with $MarginV \ge 480\text{px}$ (scaling to $\ge 510\text{px}$ under downward camera drift)
- **And** FFmpeg MUST burn subtitles during video composition via `libass`.

#### Scenario: Native libass subtitle burn for 16:9 horizontal video (Happy Path)
- **Given** word-level narration timestamps for a 16:9 horizontal canvas ($1920\times 1080$)
- **When** subtitles are generated
- **Then** `ASSSubtitleGenerator` MUST emit a compliant `.ass` script with $MarginV \ge 130\text{px}$
- **And** FFmpeg MUST burn subtitles during video composition via `libass`.

#### Scenario: Downward camera drift compensation (Edge Case)
- **Given** a 9:16 video scene with active downward procedural camera drift ($\Delta y = +30\text{px}$)
- **When** subtitle margin calculation executes
- **Then** $MarginV$ MUST be boosted dynamically to $\ge 510\text{px}$
- **And** rendered text MUST remain strictly above the 450px bottom UI danger threshold.

### Requirement: Atomic Single-Pass Video Transcoding and Filtergraph Assembly
(Previously: Governed atomic single-pass transcoding in monolithic `hybrid_engine.py` and `MultiActVideoRenderer`)

When video re-encoding is required (due to Ken Burns camera motion, burned libass subtitles, or atmospheric overlay blending), the decomposed modules (`src/media/ken_burns.py`, `src/media/overlays.py`, and `src/media/hybrid_engine.py`) MUST construct a single consolidated FFmpeg `filter_complex` execution pass (`encode_defaults` veryfast/CRF 21). Intermediate video frames or chunk files on disk remain strictly prohibited. All FFmpeg subprocess invocations MUST drain `stderr` asynchronously in a background thread to prevent OS pipe buffer deadlocks (in compliance with invariant REG-06).

#### Scenario: Decomposed Ken Burns zoompan filter emits single-pass filtergraph (Happy Path)
- **Given** a still image asset requiring 3D Ken Burns camera drift and easing
- **When** `build_ken_burns_zoompan_filter()` in `src/media/ken_burns.py` generates filter parameters
- **Then** it MUST construct an atomic `zoompan` filter string
- **And** the engine MUST render the motion sequence in a single FFmpeg execution pass without intermediate PNG frame dumps.

#### Scenario: Decomposed overlay compositor blends alpha layers in single encode pass (Happy Path)
- **Given** a scene requiring atmospheric particle overlays and video loop playback
- **When** `src/media/overlays.py` resolves overlay assets
- **Then** the filtergraph MUST composite alpha overlays directly into the master render pipeline in a single pass
- **And** no intermediate composited video files SHALL be written to disk.

#### Scenario: Asynchronous stderr draining during single-pass encode (Happy Path)
- **Given** a single-pass video encoding task that produces extensive FFmpeg log output
- **When** `run_ffmpeg` executes
- **Then** `stderr` MUST be consumed asynchronously by a reader thread
- **And** the pipe buffer MUST NOT deadlock or block execution.

### Requirement: Stream-Copy Preservation When Subtitles Inactive Across Modular Compositors
(Previously: Mandated that `LoopVideoEngine`, `MultiSceneCompositor`, and `MultiActVideoRenderer` preserve stream-copy `-c:v copy` when subtitles are inactive)

The decomposition of `src/media/hybrid_engine.py` into modular components (`src/media/ken_burns.py`, `src/media/overlays.py`, and lean engine coordinators) MUST preserve stream-copy `-c:v copy` eligibility across all video generation engines. Whenever `burn_subtitles` (or equivalent subtitle burn flag) is `False` or `has_active_subtitles(path)` evaluates to `False`, and visual motion overlays are not active, the decomposed compositors MUST omit subtitle filter clauses and assemble video via FFmpeg concat demuxer `-c:v copy`. Inactive, missing, or empty subtitle paths MUST NOT trigger fallback to video re-encoding passes. When subtitles are active and burning is enabled, subtitle file paths MUST be escaped properly for FFmpeg filter syntax and burned natively via `libass` in a single pass.

#### Scenario: Decomposed hybrid engine preserves stream-copy when subtitles and overlays are inactive (Happy Path)
- **Given** a scene configuration where `burn_subtitles` is `False` and no visual overlays are requested
- **When** `HybridVideoEngine` or decomposed compositors prepare FFmpeg arguments
- **Then** the engine MUST omit any `subtitles=` or `libass` filter from the FFmpeg command
- **And** the engine MUST retain `-c:v copy` for video output muxing when source codecs match target geometry.

#### Scenario: Active subtitle dialogue triggers libass filter injection in modular engine (Happy Path)
- **Given** a valid ASS file with at least one active dialogue event and subtitle burning enabled
- **When** the decomposed video engine constructs the FFmpeg filtergraph
- **Then** `has_active_subtitles(path)` MUST evaluate to `True`
- **And** the engine MUST include the escaped subtitle filter and perform video transcoding with `libass` in a single pass.

#### Scenario: None or empty subtitle path provided to decomposed engine (Edge Case)
- **Given** a subtitle path parameter that is `None`, empty string, or points to a non-existent file
- **When** the decomposed video engine evaluates subtitle eligibility
- **Then** `has_active_subtitles(path)` MUST return `False` without raising an exception
- **And** the engine MUST omit subtitle filters and maintain stream-copy eligibility.

### Requirement: Volatile RAM Audio Temp Storage and Single-Pass Audio Mastering Invariant Retention
Modularization of media composition, audio pipelines, and curator segmentation MUST strictly retain compliance with memory-backed temporary storage and audio mastering rules:
1. **Volatile RAM Temp Audio (`/dev/shm`)**: All intermediate audio files, silence padding buffers, and dramatic pause concatenation buffers MUST be allocated inside volatile RAM (`/dev/shm/yt_auto_audio`, or OS temp directory fallback) to prevent SSD wear and minimize I/O latency. All intermediate chunks MUST be deleted from RAM immediately following concatenation.
2. **Single-Pass Audio Mastering**: Narration audio mastering MUST execute in a single consolidated FFmpeg `filter_complex` pass combining voice equalization (highpass/lowpass), sidechain ducking under background music, and EBU R128 loudness normalization ($I=-14.0\text{ LUFS}$, $TP=-1.5\text{ dBTP}$, $LRA=11.0$). Double-pass disk renders are strictly prohibited.

#### Scenario: Intermediate audio temp storage resolves to RAM during decomposed audio pipeline execution (Happy Path)
- **Given** a Linux host with a writable `/dev/shm` filesystem
- **When** `_get_ram_temp_dir()` is invoked during audio generation in decomposed audio modules
- **Then** the returned directory path MUST reside inside `/dev/shm/yt_auto_audio`
- **And** intermediate chunk files MUST be purged from RAM immediately after concatenation.

#### Scenario: Decomposed audio mastering executes in single FFmpeg pass (Happy Path)
- **Given** narration speech WAV and background music MP3 inputs
- **When** `master_audio_track` runs
- **Then** FFmpeg MUST emit a stereo 48 kHz master audio file in a single execution pass combining ducking and EBU R128 normalization.
