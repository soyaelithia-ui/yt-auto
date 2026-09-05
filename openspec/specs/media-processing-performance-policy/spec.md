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
Subtitles generated for 9:16 vertical Shorts MUST be compiled into Advanced SubStation Alpha (`.ass`) scripts and burned natively via FFmpeg `libass`. Subtitles generated for 9:16 vertical Shorts MUST enforce bottom UI Safe Area $MarginV \ge 480\text{px}$ (canonical $\ge 25\%$ of canvas height) and $MarginV \ge 130\text{px}$ for 16:9 horizontal video, scaled with procedural 2.5D camera drift offsets to ensure clearance above player UI controls. Subtitles MUST enforce word-level karaoke timing (`{\kf}`). Frame-by-frame Python/Pillow text rasterization loops are strictly prohibited.

### Scenario: Native libass subtitle burn for 9:16 vertical Shorts (Happy Path)
- **Given** word-level narration timestamps for a 9:16 vertical Short ($1080\times 1920$)
- **When** subtitles are generated
- **Then** `ASSSubtitleGenerator` MUST emit a compliant `.ass` script with $MarginV \ge 480\text{px}$ (scaling to $\ge 510\text{px}$ under downward camera drift)
- **And** FFmpeg MUST burn subtitles during video composition via `libass`.

### Scenario: Native libass subtitle burn for 16:9 horizontal video (Happy Path)
- **Given** word-level narration timestamps for a 16:9 horizontal canvas ($1920\times 1080$)
- **When** subtitles are generated
- **Then** `ASSSubtitleGenerator` MUST emit a compliant `.ass` script with $MarginV \ge 130\text{px}$
- **And** FFmpeg MUST burn subtitles during video composition via `libass`.

### Scenario: Downward camera drift compensation (Edge Case)
- **Given** a 9:16 video scene with active downward procedural camera drift ($\Delta y = +30\text{px}$)
- **When** subtitle margin calculation executes
- **Then** $MarginV$ MUST be boosted dynamically to $\ge 510\text{px}$
- **And** rendered text MUST remain strictly above the 450px bottom UI danger threshold.

## Requirement: Atomic Single-Pass Video Transcoding and Asynchronous Pipe Drain
When `stream_copy_mode` is true, production MUST assemble with concat demuxer `-c:v copy` and MUST NOT force a single `-filter_complex` of raw RGBA streaming. When encode is required (HUD, scale, xfade, or burned subtitles), FFmpeg MUST use one encode pass (`encode_defaults` veryfast/CRF 21) with libass and EBU R128 as applicable, and MUST drain `stderr` asynchronously. Intermediate MP4 chunks on disk remain prohibited. Raw RGBA stdin streaming MAY run only when `ENABLE_NATIVE_PROCEDURAL` is enabled.

### Scenario: Homogeneous beats stay stream-copy (Happy Path)
- **Given** horizontal orientation, no burned subtitles, and no `niche_hud`
- **When** beats/loop composition runs
- **Then** FFmpeg MUST use concat demuxer `-c:v copy`
- **And** MUST NOT require raw RGBA stdin.

## Requirement: Stream-Copy Preservation When Subtitles Inactive
Video generation engines (`LoopVideoEngine`, `MultiSceneCompositor`, `MultiActVideoRenderer`) MUST omit the subtitle filter and preserve `-c:v copy` stream-copy eligibility whenever `burn_subtitles` (or equivalent subtitle burn flag) is `False` or `has_active_subtitles(path)` evaluates to `False`. Video generation engines MUST NOT inject inactive or empty subtitle filters into FFmpeg filtergraphs, avoiding unnecessary video re-encoding passes and preserving lossless source video streams. When subtitles are active and burning is enabled, subtitle file paths MUST be escaped properly for FFmpeg filter syntax. Inactive subtitle files MUST NOT force MultiAct off the homogeneity-gated stream-copy path when HUD and xfade are off.

### Scenario: Stream-copy preserved when subtitle burning is inactive or disabled (Happy Path)
- **Given** a media generation pipeline where subtitle burning is disabled or `has_active_subtitles(path)` returns `False`
- **When** `LoopVideoEngine`, `MultiSceneCompositor`, or `MultiActVideoRenderer` prepares FFmpeg arguments
- **Then** the engine MUST omit any `subtitles=` filter from the FFmpeg command
- **And** the engine MUST retain `-c:v copy` for video output muxing when source codecs and parameters permit stream copy.

### Scenario: Active subtitle dialogue triggers libass filter injection (Happy Path)
- **Given** a valid ASS file with at least one active dialogue event and subtitle burning enabled
- **When** video engine constructs the FFmpeg filtergraph
- **Then** `has_active_subtitles(path)` MUST evaluate to `True`
- **And** the engine MUST include the escaped subtitle filter and perform video transcoding with `libass`.

### Scenario: None or empty subtitle path provided to engine (Edge Case)
- **Given** a subtitle path parameter that is `None`, empty string, or points to a non-existent file
- **When** video engine evaluates subtitle eligibility
- **Then** `has_active_subtitles(path)` MUST return `False` without raising an exception
- **And** the engine MUST omit subtitle filters and maintain stream-copy eligibility.
