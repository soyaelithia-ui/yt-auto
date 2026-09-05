# Delta Specification: Media Pipeline Hardening

## Capability Overview
The `media-pipeline-hardening` capability governs the lifecycle, execution safety, and streaming architecture of FFmpeg/FFprobe operations across all audio synthesis, DSP mixing, and multi-act visual compositing engines. Production defaults to FFmpeg lavfi/catalog via `ProceduralVideoEngine()`. NativeProceduralEngine and rawvideo stdin are opt-in only when `ENABLE_NATIVE_PROCEDURAL` is set. This spec also covers multi-scene rendering fault-tolerance, pipe stream isolation between sequential scene acts, and non-blocking subprocess watchdog monitoring.

## Modified Requirements

### Requirement 2: High-Throughput Rawvideo Stream Piping with Multi-Scene Pipe Isolation
Production video MUST NOT require piping uncompressed `rawvideo rgb24` frames into FFmpeg stdin. Homogeneous procedural loops MUST use catalog/lavfi files and concat demuxer `-c:v copy` when `stream_copy_mode`. Raw pixel stdin (`rawvideo rgb24` or `yuv420p`) MAY run only when `ENABLE_NATIVE_PROCEDURAL` is explicitly enabled. When that opt-in path is active, the frame feeder MUST isolate stdin across scene boundaries (flush, synchronize, delimit) and MUST NOT use per-frame PNG disk caches.

#### Scenario: Production director path does not use rawvideo stdin (Happy Path)
- **Given** `ENABLE_NATIVE_PROCEDURAL` is unset and a multi-scene procedural manifest without `niche_hud`
- **When** `DIRECTOR_SINGLE_PASS` assembles the video
- **Then** FFmpeg MUST ingest catalog/lavfi media via concat demuxer
- **And** the pipeline MUST NOT require `-f rawvideo -pix_fmt rgb24` stdin.

#### Scenario: Opt-in native feeder isolates pipes (Edge Case)
- **Given** `ENABLE_NATIVE_PROCEDURAL` is enabled and a rawvideo stdin feeder is active
- **When** the downstream FFmpeg process exits abruptly mid-scene
- **Then** the frame feeder MUST catch `BrokenPipeError` or process termination
- **And** the engine MUST close pipes, reap the process group, and raise `FFmpegExecutionError` with stderr.

## Added Requirements

### Requirement 5: Multi-Scene Rendering Fault-Tolerance and Frame Integrity Validation
The media rendering pipeline MUST validate multi-scene frame sequences, act durations, and spatial dimension consistency prior to and during encoding. If an individual procedural scene fails rendering or produces an incomplete frame stream, the engine MUST isolate the fault, attempt a single scene re-render using a fallback FFmpeg procedural loop, and ensure the overall video stream maintains exact duration and timestamp alignment.

#### Scenario: Single scene render failure recovers with fallback procedural loop (Happy Path)
- **Given** a 4-act video render where Act 2 encounters an FFmpeg lavfi or catalog synthesis fault
- **When** the multi-act compositor detects the incomplete frame stream
- **Then** the engine MUST catch the scene fault and render Act 2 using the safe fallback procedural loop
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
All media render modules (including `proc_engine.py`, `unified_encoder.py`, `native_procedural.py`, and `inmemory_compositor.py`) MUST wrap `subprocess.Popen` pipe chains in robust `try/finally` blocks to ensure cleanup on exceptions.

#### Scenario: Clean execution of dual Popen chain (Happy Path)
- **Given** a successful rendering operation involving two piped `Popen` subprocesses
- **When** the rendering completes without exceptions
- **Then** the `finally` block MUST safely invoke `wait()` on the processes
- **And** the processes MUST terminate cleanly without leaking resources.

#### Scenario: Exception during rendering subprocess execution (Edge Case)
- **Given** an active rendering session involving an FFmpeg `Popen` process and rendering subprocesses
- **When** an unexpected exception occurs during the render loop
- **Then** the `finally` block MUST execute
- **And** it MUST explicitly invoke `kill()` and `wait()` on the FFmpeg subprocess
- **And** it MUST ensure all child subprocesses and allocated buffers are closed before propagating the exception.

#### Scenario: Cleanup failure during exception handling (Error State)
- **Given** an exception occurred in the render loop triggering the `finally` cleanup block
- **When** the `kill()` or `close()` operations themselves raise an exception (e.g., process already dead)
- **Then** the cleanup block MUST suppress these secondary cleanup exceptions
- **And** the original render loop exception MUST be correctly re-raised to the caller.

### Requirement 8: Multi-Layer Procedural Atmospheric Shaders
Production loop synthesis MUST resolve catalog rows as FFmpeg lavfi. The nine WGSL archetypes (`tactical_chamber`, `dark_forest`, `arctic_desolation`, `cosmic_singularity`, `arcade_vector_flight`, `parkour_runner`, `cozy_hearth`, `synaptic_network`, `maritime_lighthouse`) MAY compile only when `ENABLE_NATIVE_PROCEDURAL` is set and MUST remain quarantined under `src/media/_legacy`. Production MUST NOT require Mesa Lavapipe or `.wgsl` compilation.

#### Scenario: Production catalog uses FFmpeg lavfi (Happy Path)
- **Given** `ENABLE_NATIVE_PROCEDURAL` is unset and a story referencing maritime, lighthouse, or coastal settings
- **When** the procedural loop engine resolves the video
- **Then** the loop MUST be synthesized as FFmpeg lavfi/catalog
- **And** WGSL/Lavapipe MUST NOT be required.

### Requirement 9: Setting-Adaptive Thumbnail Composition
The `ThumbnailEngine` and `AdaptiveSubjectCompositor` MUST composite setting-accurate anatomical and architectural silhouettes matching the detected narrative archetype without duplicating background celestial or structural elements.

#### Scenario: Coastal Story Thumbnail Generation (Happy Path)
- **Given** a story set at a lighthouse or sea cliff
- **When** a thumbnail is generated
- **Then** the compositor places a solitary coastal keeper with lantern overlooking the sea with accent rim lighting.

### Requirement 10: Orchestrator Pipeline Mode and Lane Config Alignment
The orchestrator in `src/pipeline.py` MUST correctly resolve lane video engine specifications across both `visual_pipeline` and `video_engine` configuration keys. When a lane specifies `"director"` or `"multiscene"`, the pipeline MUST instantiate `MultiSceneCompositor` defaulting to `ProceduralVideoEngine()`. `NativeProceduralEngine` MUST be used only when `ENABLE_NATIVE_PROCEDURAL` is explicitly enabled. If a channel config specifies an unrecognized engine mode, the pipeline MUST fail early with a clear validation error rather than silently defaulting to a 6-second static loop.

#### Scenario: Channel with director pipeline dispatches multiscene compositor (Happy Path)
- **Given** a channel lane configuration specifying `"visual_pipeline": "director"` and `ENABLE_NATIVE_PROCEDURAL` unset
- **When** the pipeline orchestrator initializes the video render phase
- **Then** `engine_mode` MUST resolve to `"director"` (or `"multiscene"`)
- **And** the pipeline MUST invoke `MultiSceneCompositor` rather than `LoopVideoEngine`
- **And** the compositor MUST default to `ProceduralVideoEngine()` not `NativeProceduralEngine`.

#### Scenario: Unrecognized engine mode configuration detection (Error State)
- **Given** a channel configuration with an invalid engine string `"unknown_engine"`
- **When** the pipeline validates configuration during initialization
- **Then** the pipeline MUST raise a `ValueError` detailing the invalid engine mode
- **And** execution MUST NOT proceed with silent fallback to static loop mode.

### Requirement 11: Unit Test Compositor Isolation and Hermetic Execution
Unit tests verifying daemon orchestration, CLI commands, and safety assertions MUST NOT invoke live WebGPU software rasterization (Lavapipe) or FFmpeg encoding for longform video durations (>=600s). MultiSceneCompositor.render MUST be mocked to return a placeholder video artifact in unit tests, preserving sub-second execution speed and zero orphan processes.

#### Scenario: Multi-scene compositor isolation in unit test suite (Happy Path)
- **Given** a unit test orchestrating daemon or safety pipeline execution
- **When** pipeline execution triggers video rendering on a longform lane
- **Then** the compositor MUST be mocked to return placeholder video without invoking FFmpeg or WebGPU software rasterization
- **And** the unit test MUST complete in under 4 seconds.
