# Delta Specification: Media Pipeline Hardening

## Capability Overview
The `media-pipeline-hardening` capability governs the lifecycle, execution safety, and streaming architecture of FFmpeg/FFprobe operations across all audio synthesis, DSP mixing, and multi-act visual compositing engines.

## Modified Requirements

### Requirement 1: Centralized FFmpeg Execution Runtime
All media processing modules (including `mixer.py`, `vocal_chain.py`, `multi_act_renderer.py`, and `realtime_video_engine.py`) MUST execute external FFmpeg operations via `lib.ffmpeg.run_ffmpeg` rather than direct `subprocess.run` or `subprocess.Popen`.

#### Scenario: Audio mixing invokes centralized runner (Happy Path)
- **Given** an audio track mixdown request with voiceover, background ambience, and sound effects
- **When** the audio mixer executes the filtergraph
- **Then** the process MUST invoke `lib.ffmpeg.run_ffmpeg` with timeout tracking and structured logging
- **And** the output mix file MUST be verified upon exit code 0.

#### Scenario: FFmpeg filter failure during vocal processing (Edge Case)
- **Given** an invalid or corrupt audio filtergraph string passed to vocal chain
- **When** `run_ffmpeg` executes
- **Then** the runtime MUST catch the non-zero exit code and raise `FFmpegExecutionError`
- **And** the exception object MUST contain stderr details and the full command array.

### Requirement 2: High-Throughput Rawvideo Stream Piping
Video rendering pipelines streaming generated frames into FFmpeg MUST pipe uncompressed raw pixel buffers (`rawvideo rgb24` or `yuv420p`) directly into the encoder stdin pipe, eliminating PNG disk caching and per-frame PNG encoding overhead.

#### Scenario: Real-time rendering pipes raw video frames (Happy Path)
- **Given** a sequence of uncompressed RGB24 video frames generated at 1080x1920
- **When** frames are dispatched to the FFmpeg child process
- **Then** bytes MUST be written directly to `stdin` without disk intermediate files
- **And** FFmpeg MUST ingest the stream with `-f rawvideo -pix_fmt rgb24 -s 1080x1920`.

#### Scenario: Downstream encoder process crashes prematurely (Edge Case)
- **Given** an active rawvideo pipe stream
- **When** the downstream FFmpeg process exits abruptly mid-render
- **Then** the frame feeder MUST catch `BrokenPipeError` or process termination
- **And** the engine MUST close pipes, reap the child process, and raise `FFmpegExecutionError`.

## Added Requirements

### Requirement 3: Typed Exception Hierarchy Enforcement
Media engines MUST NOT swallow FFmpeg failures or raise untyped generic exceptions; all process failures, timeouts, and probe errors MUST raise explicit subclasses of `FFmpegError`.

#### Scenario: FFmpeg process exceeds execution timeout (Happy Path)
- **Given** a complex rendering task configured with a 30-second timeout
- **When** FFmpeg execution exceeds 30 seconds
- **Then** the process runner MUST terminate the child process group
- **And** the runner MUST raise `FFmpegTimeoutError` with elapsed duration details.

#### Scenario: Media probe targets non-existent file (Edge Case)
- **Given** a requested media probe path that does not exist
- **When** `probe_media` is invoked
- **Then** the probe runner MUST raise `FFprobeError` indicating the missing file.

## Removed Requirements

### Requirement 4: Legacy Shim Modules and Test Audio Pollution
Legacy 3-line re-export shims (`src/video.py`, `src/tts.py`, `src/subtitles.py`, `src/youtube_control.py`) MUST be removed, and synthetic test generators (`generate_synthetic_pcm_audio`) MUST be relocated from production `src/audio.py` to `tests/helpers/audio.py`.

#### Scenario: Direct import from canonical modules (Happy Path)
- **Given** callers importing video, TTS, and subtitle components
- **When** imports are resolved
- **Then** callers MUST import directly from `lib/` or `src/compositing/` without using root shims.

#### Scenario: Test suite requires synthetic audio generation (Edge Case)
- **Given** automated unit tests requiring zero-asset sine/PCM audio buffers
- **When** tests execute
- **Then** tests MUST import helper functions from `tests.helpers.audio`
- **And** production modules MUST NOT import test audio helpers.
