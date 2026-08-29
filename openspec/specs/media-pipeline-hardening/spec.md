# Delta Specification: Media Pipeline Hardening

## Capability Overview
The `media-pipeline-hardening` capability governs the lifecycle, execution safety, and streaming architecture of FFmpeg/FFprobe operations across all audio synthesis, DSP mixing, and multi-act visual compositing engines. This delta adds multi-scene rendering fault-tolerance, pipe stream isolation between sequential scene acts, and non-blocking subprocess watchdog monitoring.

## Modified Requirements

### Requirement 2: High-Throughput Rawvideo Stream Piping with Multi-Scene Pipe Isolation
Video rendering pipelines streaming generated frames into FFmpeg MUST pipe uncompressed raw pixel buffers (`rawvideo rgb24` or `yuv420p`) directly into the encoder stdin pipe, eliminating PNG disk caching and per-frame PNG encoding overhead. During multi-scene compositing, the frame feeder MUST enforce pipe stream isolation across scene boundaries, ensuring stdin buffers are completely flushed, synchronized, and cleanly delimited between consecutive acts to prevent corrupted frame interleaving or buffer stall.

#### Scenario: Multi-scene real-time rendering pipes raw video frames with stream isolation (Happy Path)
- **Given** a sequence of 3 discrete procedural scene acts generated at 1080x1920 portrait resolution
- **When** frames are dispatched across scene boundaries to the FFmpeg child process
- **Then** bytes MUST be written directly to `stdin` without disk intermediate files
- **And** the feeder MUST flush and isolate each scene's frame buffer before initiating the subsequent act
- **And** FFmpeg MUST ingest the continuous stream with `-f rawvideo -pix_fmt rgb24 -s 1080x1920` without dropping or misaligning frames.

#### Scenario: Downstream encoder process crashes prematurely during scene transition (Edge Case)
- **Given** an active rawvideo pipe stream transitioning between Act 1 and Act 2
- **When** the downstream FFmpeg process exits abruptly mid-render
- **Then** the frame feeder MUST catch `BrokenPipeError` or process termination
- **And** the engine MUST safely close stdin/stdout pipes, reap child process groups, and raise `FFmpegExecutionError` with stderr diagnostic capture.

## Added Requirements

### Requirement 5: Multi-Scene Rendering Fault-Tolerance and Frame Integrity Validation
The media rendering pipeline MUST validate multi-scene frame sequences, act durations, and spatial dimension consistency prior to and during encoding. If an individual procedural scene fails rendering or produces an incomplete frame stream, the engine MUST isolate the fault, attempt a single scene re-render using a fallback procedural shader, and ensure the overall video stream maintains exact duration and timestamp alignment.

#### Scenario: Single scene render failure recovers with fallback procedural shader (Happy Path)
- **Given** a 4-act video render where Act 2 encounters a WebGL context glitch
- **When** the multi-act compositor detects the incomplete frame stream
- **Then** the engine MUST catch the scene fault and render Act 2 using the safe fallback procedural shader
- **And** the resulting compiled video MUST maintain the target total duration without missing time segments.

#### Scenario: Unrecoverable frame stream corruption across multiple acts (Edge Case)
- **Given** a catastrophic rendering error where multiple scene feeds fail integrity checks
- **When** retry limits are exhausted
- **Then** the media engine MUST terminate the encoding pipeline
- **And** the engine MUST raise `FFmpegExecutionError` with a structured diagnostic payload detailing failed scene acts.

### Requirement 6: Non-Blocking Sub-Process Watchdog and Resource Isolation
All external FFmpeg and media generation subprocesses MUST be monitored by a non-blocking watchdog thread that tracks process liveness, memory consumption (RSS limit $\le 4.0\text{ GB}$), and execution time against strict per-task timeouts ($t_{\text{timeout}} \le 180\text{s}$). If a subprocess hangs, leaks memory, or fails to emit progress telemetry within the timeout window, the watchdog MUST terminate the process group (`SIGKILL` after grace period) and reap all child resources.

#### Scenario: Active FFmpeg render monitored by watchdog finishes within limits (Happy Path)
- **Given** a multi-act video encoding job with a 120-second timeout budget
- **When** the job executes and finishes in 45 seconds using 1.2 GB RSS memory
- **Then** the watchdog thread MUST confirm successful exit code 0
- **And** the watchdog MUST cleanly disengage without interrupting subsequent queue tasks.

#### Scenario: Stalled or runaway FFmpeg subprocess terminated by watchdog (Edge Case)
- **Given** an FFmpeg subprocess that deadlocks on an unclosed pipe or exceeds 180 seconds of execution
- **When** the watchdog timer expires
- **Then** the watchdog MUST send `SIGTERM` followed by `SIGKILL` to the entire process group
- **And** the pipeline MUST raise `FFmpegTimeoutError` and release all associated file descriptors and memory buffers.

### Requirement 7: Exception Guards for Direct Popen Chains
All media render modules (including `proc_engine.py`, `subtitles.py`, `stream_renderer.py`, and `web_renderer.py`) MUST wrap dual `subprocess.Popen` pipe chains and browser sessions in robust `try/finally` blocks to ensure cleanup on exceptions.

#### Scenario: Clean execution of dual Popen chain (Happy Path)
- **Given** a successful rendering operation involving two piped `Popen` subprocesses
- **When** the rendering completes without exceptions
- **Then** the `finally` block MUST safely invoke `wait()` on the processes
- **And** the processes MUST terminate cleanly without leaking resources.

#### Scenario: Exception during browser and FFmpeg processing (Edge Case)
- **Given** an active rendering session involving an FFmpeg `Popen` process and an open browser
- **When** an unexpected exception occurs during the render loop
- **Then** the `finally` block MUST execute
- **And** it MUST explicitly invoke `kill()` and `wait()` on the FFmpeg subprocess
- **And** it MUST invoke `close()` on the browser instance before propagating the exception.

#### Scenario: Cleanup failure during exception handling (Error State)
- **Given** an exception occurred in the render loop triggering the `finally` cleanup block
- **When** the `kill()` or `close()` operations themselves raise an exception (e.g., process already dead)
- **Then** the cleanup block MUST suppress these secondary cleanup exceptions
- **And** the original render loop exception MUST be correctly re-raised to the caller.
