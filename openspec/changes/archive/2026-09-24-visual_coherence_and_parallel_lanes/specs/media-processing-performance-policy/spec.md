# Media Processing and Performance Policy Specification (Delta)

## Purpose
Codifies the strict resource governance envelope (hard target ceiling $\le 2.0$ CPU Cores, $\le 2.0$ GiB RAM), zero steady-state idle footprint, disk streaming without in-memory frame buffer loops, stream-copy priority with soft subtitle muxing, and single-pass atomic media composition.

## RENAMED Requirements

### Requirement: Atomic Single-Pass Video Transcoding and Filtergraph Assembly -> Disk Streaming Without Buffer Loops (Zero In-Memory Video Arrays)

(Reason: Explicitly codify prohibition of uncompressed in-memory video array accumulation and enforce single-pass disk streaming)

### Requirement: Stream-Copy Preservation When Subtitles Inactive Across Modular Compositors -> Stream-Copy Priority and Soft Subtitle Muxing

(Reason: Enforce stream-copy priority with soft subtitle muxing on video-loop pathways)

## MODIFIED Requirements

### Requirement: Disk Streaming Without Buffer Loops (Zero In-Memory Video Arrays)
(Previously: Governed atomic single-pass transcoding in monolithic `hybrid_engine.py` and `MultiActVideoRenderer` without explicit prohibition of uncompressed in-memory video array accumulation)

The system MUST stream video and audio data directly from disk to disk via atomic FFmpeg single-pass filtergraphs (`zoompan`, `xfade`, `colorbalance`). Storing uncompressed video frame sequences (such as lists or NumPy arrays of $1080\times 1920$ RGBA frames) in Python memory is STRICTLY PROHIBITED (invariant `REG-08`), as holding 900 frames in memory requires $\approx 7.46\text{ GB}$ RAM and causes immediate out-of-memory termination.

Where custom raster compositing is strictly required (such as in `InMemoryCompositor` or `SVGOverlayEngine`), the engine MUST allocate exactly **one** pre-allocated contiguous reusable buffer (`_out_buffer` of shape `(1920, 1080, 4)` uint8 $\approx 8.29\text{ MB}$) and stream frames sequentially into FFmpeg's standard input pipe (`pipe:0`). All FFmpeg subprocess invocations MUST bound thread execution with `-threads 2` (default) up to an absolute ceiling of `-threads 4` during multi-act renders, and drain `stderr` asynchronously in a background thread to prevent OS pipe deadlocks (invariant `REG-06`).

#### Scenario: Decomposed Ken Burns zoompan filter emits single-pass filtergraph (Happy Path)
- **Given** a still image asset requiring 3D Ken Burns camera drift and easing
- **When** `build_ken_burns_zoompan_filter()` in `src/media/ken_burns.py` generates filter parameters
- **Then** it MUST construct an atomic `zoompan` filter string
- **And** the engine MUST render the motion sequence in a single FFmpeg execution pass without intermediate PNG frame dumps or in-memory frame lists.

#### Scenario: Reusable single-frame buffer compositing without allocation growth (Happy Path)
- **Given** an in-memory frame compositing operation across 300 video frames
- **When** `InMemoryCompositor` composites SVG overlays and frames
- **Then** it MUST mutate a single contiguous `(1920, 1080, 4)` uint8 buffer in-place
- **And** total Python heap memory allocated for frames MUST NOT exceed 10 MiB throughout the render.

#### Scenario: Asynchronous stderr draining during single-pass encode (Happy Path)
- **Given** a single-pass video encoding task that produces extensive FFmpeg log output
- **When** `run_ffmpeg` or `UnifiedEncoder` executes
- **Then** `stderr` MUST be consumed asynchronously by a reader thread
- **And** the pipe buffer MUST NOT deadlock or block execution.

### Requirement: Stream-Copy Priority and Soft Subtitle Muxing
(Previously: Mandated that `LoopVideoEngine`, `MultiSceneCompositor`, and `MultiActVideoRenderer` preserve stream-copy `-c:v copy` when subtitles are inactive)

The system MUST prioritize stream-copy (`-c:v copy`) composition across all video-loop and ambient video rendering pathways to maintain near-zero CPU consumption ($\approx 0.10\text{ Cores}$) and high throughput ($> 80\times\text{ realtime}$). 

When subtitles are enabled on stream-copy pathways, subtitles MUST be soft-muxed as an MP4 timed text track (`-c:s mov_text`) rather than burned into video pixels via CPU-heavy `libass` rasterization. Active subtitle tracks MUST NOT disable stream-copy or trigger video re-encoding on loop pathways. When video re-encoding is explicitly required (e.g. `image_animation` lanes with Ken Burns or complex alpha blending), subtitles SHALL be burned natively via `libass` in a single pass with safe-area compliance ($MarginV \ge 460\text{px}$ for vertical Shorts).

#### Scenario: Stream-copy pipeline muxes subtitles via mov_text without video re-encode (Happy Path)
- **Given** a video-loop production lane with active subtitle dialogue cues
- **When** `LoopVideoEngine.compose()` or `stage_09_render` executes
- **Then** the FFmpeg command MUST contain `-c:v copy`
- **And** the FFmpeg command MUST contain `-c:s mov_text`
- **And** the FFmpeg command MUST NOT contain `libass` or `subtitles=` video filter clauses
- **And** execution MUST complete with CPU utilization $\le 0.20\text{ Cores}$.

#### Scenario: Subtitle burn enabled exclusively on re-encode animation lane (Happy Path)
- **Given** an `image_animation` lane requiring Ken Burns camera motion and subtitle display
- **When** `UnifiedEncoder` constructs the FFmpeg filtergraph
- **Then** the filtergraph MUST incorporate `libass` subtitle burning into the atomic single-pass filterchain
- **And** enforce $MarginV \ge 460\text{px}$ to preserve mobile UI safe zones.

#### Scenario: Inactive or missing subtitles preserve stream-copy (Edge Case)
- **Given** a scene configuration where subtitles are absent, empty, or disabled
- **When** the composition engine constructs the command
- **Then** subtitle inputs and filter clauses MUST be omitted completely
- **And** stream-copy `-c:v copy` MUST be preserved.

## ADDED Requirements

### Requirement: Hard Target Resource Ceiling Governance (2 Cores CPU, 2.0 GiB RAM)

In strict accordance with Section 5 of `AGENTS.md` and anti-regression invariant `REG-14`, all media processing workflows, pipeline stages, and background daemons MUST operate within an inviolable hard target ceiling of:
- **CPU Aggregate Target**: $\le 2.0$ CPU Cores ($\le 200\%$ aggregate CPU utilization across all active threads and subprocesses).
- **RAM Resident Target**: $\le 2.0$ GiB RAM ($2,048\text{ MiB}$ peak resident memory RSS).

Resource consumption MUST follow the monotonic optimization directive: usage MUST only decrease or remain stable, never climbing across commits. If any architectural feature or render pass breaches the 2 Cores / 2.0 GiB RAM ceiling, the system MUST trigger the Resource Work Refusal policy to halt and optimize the implementation before deployment.

#### Scenario: Multi-scene render operates within 2 Cores and 2.0 GiB RAM ceiling (Happy Path)
- **Given** an active video render executing an `image_animation` or `video_loop` production job
- **When** CPU and resident memory consumption are profiled during peak composition
- **Then** aggregate CPU utilization across all subprocess threads MUST NOT exceed 2.0 Cores (200%)
- **And** peak resident memory (RSS) MUST NOT exceed 2,048 MiB.

#### Scenario: Probe operations enforce low-CPU thread bounding (Happy Path)
- **Given** an invocation of `ffprobe` or audio loudness analysis on media assets
- **When** the probe command is constructed
- **Then** it MUST specify `-threads 2`
- **And** it MUST specify `-vn` to skip decoding video frame data into memory.

#### Scenario: Resource work refusal on budget breach (Edge Case)
- **Given** a prospective media composition pipeline that consumes $> 2.0$ Cores or $> 2.0$ GiB RAM
- **When** anti-regression guardrail or performance benchmarks run
- **Then** the test suite MUST fail with a resource target violation
- **And** automated agents MUST refuse to merge the change until optimized.

### Requirement: Zero Steady-State Idle Footprint and Resource Reclamation

The system MUST maintain minimal steady-state resource consumption, dropping to zero active CPU utilization ($0.0\%$) and releasing transient memory buffers when idle:
1. When no story or rendering job is active, background daemons MUST NOT execute busy-wait polling loops, maintain active worker threads, or keep persistent GPU/render contexts resident.
2. FFmpeg subprocesses MUST be managed through explicit context managers and timeouts. Upon process termination, stdout/stderr pipes and reader threads MUST be immediately joined and closed.
3. Memory checkpoints (`memory_checkpoint()`) MUST be invoked at stage boundaries to trigger Python garbage collection and release cached NumPy arrays.

#### Scenario: Steady-state idle resource footprint drops to zero (Happy Path)
- **Given** a background scheduler daemon in an idle state waiting for the next cadence window
- **When** CPU usage is sampled over a 10-second idle period
- **Then** aggregate CPU usage MUST be 0.0%
- **And** resident memory MUST remain below 100 MiB without climbing over time.

#### Scenario: Immediate subprocess pipe and thread reclamation (Happy Path)
- **Given** a completed FFmpeg encoding pass
- **When** `UnifiedEncoder` finishes execution or catches a timeout
- **Then** the asynchronous `_drain_stderr` reader thread MUST terminate immediately
- **And** all associated OS pipe file descriptors MUST be closed without leaking handles.
