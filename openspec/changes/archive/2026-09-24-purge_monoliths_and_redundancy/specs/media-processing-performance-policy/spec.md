# Delta for Media Processing and Performance Policy

## RENAMED Requirements

### Requirement: Stream-Copy Preservation When Subtitles Inactive -> Stream-Copy Preservation When Subtitles Inactive Across Modular Compositors

(Reason: Reflect verification across modular compositors)

### Requirement: Atomic Single-Pass Video Transcoding and Asynchronous Pipe Drain -> Atomic Single-Pass Video Transcoding and Filtergraph Assembly

(Reason: Consolidate filtergraph assembly invariants)

## MODIFIED Requirements

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

## ADDED Requirements

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
