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
(Previously: Mandated native `libass` subtitle burning for both 9:16 vertical Shorts and 16:9 horizontal videos without explicit prohibition of `libass` subtitle burning on 16:9 horizontal longform videos)

Subtitles generated for 9:16 vertical Shorts (`image_animation` or vertical re-encode lanes) MUST be compiled into Advanced SubStation Alpha (`.ass`) scripts and burned natively via FFmpeg `libass`. Subtitles generated for 9:16 vertical Shorts MUST enforce bottom UI Safe Area $MarginV \ge 480\text{px}$ (canonical $\ge 25\%$ of canvas height), scaled with procedural 2.5D camera drift offsets to ensure clearance above player UI controls. Subtitles MUST enforce word-level karaoke timing (`{\kf}`). Frame-by-frame Python/Pillow text rasterization loops are strictly prohibited.

For 16:9 horizontal longform videos (600–1800s), burning subtitles into video frames via `libass` is STRICTLY PROHIBITED; subtitles MUST be soft-muxed into the container via `mov_text` and exported as an `.srt` sidecar.

#### Scenario: Native libass subtitle burn for 9:16 vertical Shorts (Happy Path)
- **Given** word-level narration timestamps for a 9:16 vertical Short ($1080\times 1920$)
- **When** subtitles are generated
- **Then** `ASSSubtitleGenerator` MUST emit a compliant `.ass` script with $MarginV \ge 480\text{px}$ (scaling to $\ge 510\text{px}$ under downward camera drift)
- **And** FFmpeg MUST burn subtitles during video composition via `libass`.

#### Scenario: Downward camera drift compensation (Edge Case)
- **Given** a 9:16 video scene with active downward procedural camera drift ($\Delta y = +30\text{px}$)
- **When** subtitle margin calculation executes
- **Then** $MarginV$ MUST be boosted dynamically to $\ge 510\text{px}$
- **And** rendered text MUST remain strictly above the 450px bottom UI danger threshold.

#### Scenario: Prohibition of libass subtitle burn on 16:9 horizontal longform lanes (Edge Case)
- **Given** a 16:9 horizontal longform production lane
- **When** subtitles are processed for video composition
- **Then** the pipeline MUST NOT invoke `libass` or add subtitle filtergraphs to the video stream
- **And** the pipeline MUST route subtitles to container soft muxing (`-c:s mov_text`) and `.srt` sidecar export.
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

### Requirement: Stream-Copy Priority, Multi-Act Longform Concatenation, and Soft Subtitle Muxing
(Previously: Prioritized stream-copy `-c:v copy` composition across single video-loop and ambient pathways with `mov_text` soft subtitles when active, but lacked explicit mandates for multi-act longform stream-copy concatenation turnaround $\le 45\text{s}$, aggregate CPU $\le 120\%$, peak RAM $< 200\text{ MiB}$, and did not explicitly prohibit 60–90 minute full-pixel Ken Burns re-encoding or `libass` subtitle burning on 16:9 horizontal longform videos)

The system MUST prioritize stream-copy (`-c:v copy`) composition across all video-loop and longform horizontal rendering pathways (`horror-horror-long`, `drama-aita-long`, `scifi-singularity-long`) to maintain near-zero CPU consumption ($\approx 0.10\text{ Cores}$ idle/copy, $\le 1.20\text{ Cores}$ during audio ducking/normalizing) and ultra-high throughput.

For multi-act longform horizontal (16:9) narratives (10–30 minutes / 600–1800 seconds):
1. **Mandatory Stream-Copy Concatenation**: Video composition MUST assemble $N$ distinct narrative act loops sequentially using the FFmpeg concat demuxer (`-f concat -safe 0 -c:v copy`). Video packets MUST be demuxed and remuxed directly from disk without decoding or re-encoding video frames.
2. **Turnaround Performance Contract**: Rendering turnaround for an entire 10–30 minute video MUST complete in $\le 45\text{ seconds}$ from invocation to container finalization.
3. **CPU Utilization Ceiling**: Aggregate CPU utilization across all active subprocesses during composition MUST NOT exceed $120\%$ (1.2 CPU Cores), with CPU cycles restricted exclusively to audio highpass/lowpass filtering, sidechain ducking, and EBU R128 loudness normalization (`amix`, `loudnorm` bounded by `-threads 2`).
4. **RAM Footprint Bounding**: Peak resident memory (RSS) MUST remain strictly $< 200\text{ MiB}$ (canonical $< 150\text{ MiB}$) throughout multi-act composition, streaming concat manifests (`ffconcat`) and audio tracks directly from disk or `/dev/shm`.
5. **Transcoding & Subtitle Burning Prohibition**: Full-pixel Ken Burns re-encoding (`libx264` with `zoompan` or procedural transitions) and pixel-rasterized subtitle burning via `libass` are STRICTLY PROHIBITED on 16:9 horizontal longform videos. Any attempt to invoke pixel re-encoding on horizontal longform narratives MUST trigger the Resource Work Refusal policy and immediately abort.
6. **Soft Subtitle Muxing & Sidecar**: Subtitles for horizontal longform videos MUST be soft-muxed into the MP4 container as a timed text track (`-c:s mov_text`) via `subtitle_mux_ffmpeg_parts` and exported as an `.srt` sidecar file for YouTube Captions API upload.
7. **Animation Lanes Exemption**: When video re-encoding is explicitly required (strictly reserved for 9:16 vertical Shorts on `image_animation` lanes), subtitles SHALL be burned natively via `libass` in a single pass with safe-area compliance ($MarginV \ge 480\text{px}$).

#### Scenario: Multi-act longform stream-copy concatenation turnaround and CPU bounding (Happy Path)
- **Given** an 1,800-second (30-minute) horizontal narrative with 6 act loops and mastered audio
- **When** `_render_video_loop` in `stage_09_render.py` executes media composition via `stream_copy.py`
- **Then** the FFmpeg command MUST contain `-f concat -safe 0` and `-c:v copy`
- **And** total video composition turnaround MUST NOT exceed 45 seconds (target 25–35 seconds)
- **And** aggregate CPU utilization across all subprocess threads MUST NOT exceed 120% (1.2 Cores)
- **And** peak resident memory (RSS) MUST remain below 200 MiB.

#### Scenario: Container soft subtitle muxing without video re-encode on longform horizontal video (Happy Path)
- **Given** a multi-act longform horizontal video with narration subtitles
- **When** video composition and container packaging execute
- **Then** subtitles MUST be soft-muxed via `-c:s mov_text`
- **And** an `.srt` sidecar file MUST be generated in the run artifacts directory
- **And** video stream-copy `-c:v copy` MUST be preserved without pixel decoding.

#### Scenario: Subtitle burn enabled exclusively on re-encode animation lane (Happy Path)
- **Given** an `image_animation` lane requiring Ken Burns camera motion and subtitle display
- **When** `UnifiedEncoder` constructs the FFmpeg filtergraph
- **Then** the filtergraph MUST incorporate `libass` subtitle burning into the atomic single-pass filterchain
- **And** enforce $MarginV \ge 480\text{px}$ to preserve mobile UI safe zones.

#### Scenario: Work refusal on full-pixel Ken Burns or libass burning on longform horizontal lane (Edge Case)
- **Given** a 16:9 horizontal longform lane configuration attempting to execute full-pixel `zoompan` re-encode or `libass` subtitle burning
- **When** engine validation or render stage initiates
- **Then** the system MUST trigger Resource Work Refusal and abort execution
- **And** execution MUST NOT proceed with CPU-saturating re-encoding.

#### Scenario: Inactive or missing subtitles preserve stream-copy (Edge Case)
- **Given** a multi-act longform scene configuration where subtitles are absent, empty, or disabled
- **When** the composition engine constructs the concat command
- **Then** subtitle inputs and filter clauses MUST be omitted completely
- **And** stream-copy `-c:v copy` MUST be preserved.

---

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
### Requirement: Hard Target Resource Ceiling Governance (2 Cores CPU, 2.0 GiB RAM)
(Previously: Enforced the hard target operational ceiling of $\le 2.0$ CPU Cores and $\le 2.0\text{ GiB}$ RAM across individual renders and probe tasks, but did not mandate explicit global concurrency semaphores to partition parallel Short and Longform renders during continuous multi-lane daemon execution)

In strict accordance with Section 5 of `AGENTS.md` and anti-regression invariant `REG-14`, all media processing workflows, pipeline stages, and multi-lane autonomous daemon engines MUST operate within an inviolable hard target operational ceiling of:
- **CPU Aggregate Target**: $\le 2.0$ CPU Cores ($\le 200\%$ aggregate CPU utilization across all active threads and subprocesses).
- **RAM Resident Target**: $\le 2.0$ GiB RAM ($2,048\text{ MiB}$ peak resident memory RSS).

To prevent concurrent media rendering operations from exceeding the resource envelope during multi-lane daemon execution, rendering tasks MUST be strictly partitioned by global thread semaphores:
1. **Short Renders Semaphore**: `_SHORT_RENDER_SEMAPHORE = threading.Semaphore(2)`. At most two concurrent vertical Short renders (`image_animation` or vertical re-encode) MAY execute simultaneously.
2. **Longform Renders Semaphore**: `_LONG_RENDER_SEMAPHORE = threading.Semaphore(1)`. At most one horizontal longform render (`horror-horror-long`, `drama-aita-long`, `scifi-singularity-long`) MAY execute concurrently. Concurrent or parallel longform renders are STRICTLY PROHIBITED.

The multi-lane daemon worker thread pool capacity MUST NOT exceed 3 concurrent workers (`YT_MAX_PARALLEL_LANES=3`). Total aggregate CPU utilization across all concurrent lanes and subprocesses MUST NOT exceed $200\%$ (2 Cores), and peak aggregate resident memory MUST NOT exceed $2,048\text{ MiB}$ (2.0 GiB RAM).

All FFmpeg subprocess invocations MUST bound thread execution with `-threads 2` for audio mastering, loudness probes, and QA checks, and at most `-threads 4` during video encoding passes. Probes MUST specify `-vn` to skip decoding video frame data into memory.

Resource consumption MUST follow the monotonic optimization directive: usage MUST only decrease or remain stable, never climbing across commits. If any multi-lane execution or architectural feature breaches the 2 Cores / 2.0 GiB RAM ceiling, the system MUST trigger the Resource Work Refusal policy to halt and optimize the implementation before deployment.

#### Scenario: Multi-lane concurrent render execution bounded by semaphores (Happy Path)
- **Given** a multi-lane daemon running with up to 3 concurrent worker threads across shorts and longform lanes
- **When** video composition stages are reached across multiple lanes simultaneously
- **Then** Short renders MUST acquire a token from `_SHORT_RENDER_SEMAPHORE` (capacity 2)
- **And** Longform renders MUST acquire a token from `_LONG_RENDER_SEMAPHORE` (capacity 1)
- **And** aggregate CPU utilization across all concurrent lanes MUST NOT exceed 2.0 Cores (200%)
- **And** peak aggregate resident memory (RSS) MUST NOT exceed 2,048 MiB.

#### Scenario: Longform render serialization via single-token semaphore (Happy Path)
- **Given** an active horizontal longform render executing `horror-horror-long` holding `_LONG_RENDER_SEMAPHORE`
- **When** a second horizontal longform render (`drama-aita-long`) initiates composition
- **Then** the second longform render MUST block waiting for the semaphore token
- **And** zero concurrent horizontal longform renders MUST execute in parallel.

#### Scenario: Short render concurrency capped at two tokens (Happy Path)
- **Given** two vertical Short renders actively executing and occupying both tokens of `_SHORT_RENDER_SEMAPHORE`
- **When** a third vertical Short render attempts to start video composition
- **Then** the third Short render MUST block until one of the active renders releases its semaphore token
- **And** at most 2 Short renders MUST execute concurrently.

#### Scenario: Probe operations enforce low-CPU thread bounding (Happy Path)
- **Given** an invocation of `ffprobe` or audio loudness analysis on media assets
- **When** the probe command is constructed
- **Then** it MUST specify `-threads 2`
- **And** it MUST specify `-vn` to skip decoding video frame data into memory.

#### Scenario: Resource work refusal on budget breach (Edge Case)
- **Given** a prospective media composition pipeline or multi-lane configuration that consumes $> 2.0$ Cores or $> 2.0$ GiB RAM
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
