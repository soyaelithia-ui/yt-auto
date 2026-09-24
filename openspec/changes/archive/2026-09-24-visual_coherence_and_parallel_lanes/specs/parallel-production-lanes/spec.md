# Parallel Production Lanes Specification

## Purpose
Defines the independent parallel production lanes architecture formalizing the operational segregation of `image_animation` and `video_loop` visual pipelines, shared core media tooling, concurrency isolation controls, and deterministic fallback mechanisms.

## Requirements

### Requirement: Dual Visual Pipeline Taxonomy and Segregation (`visual_pipeline`)
The system MUST support explicit visual pipeline taxonomy declaring `image_animation` and `video_loop` modes within `LaneProfile` and `ALLOWED_VISUAL_PIPELINES` in `src/core/lanes.py`, alongside existing `beats` and `director` modes. The execution paths of these two pipelines SHALL be completely segregated:
1. **Video-Loop Lane (`video_loop`)**:
   - Visual sources: Pre-baked thematic continuous loops (`assets/loops/`).
   - Motion profile: Native video loop motion with subtle color balance grading.
   - Encoding engine: Stream-copy (`-c:v copy`) + `mov_text` subtitle track soft muxing.
   - Turnaround target: $1.2\text{s} - 2.5\text{s}$ per 60s Short.
2. **Image-Animation Lane (`image_animation`)**:
   - Visual sources: Curated still photography, generated concept art, thematic matting.
   - Motion profile: Smoothstep Ken Burns camera motion, segment splitting, dynamic SVG HUDs.
   - Encoding engine: Single-pass atomic FFmpeg transcode (libx264/h264_nvenc) via `UnifiedEncoder`.
   - Turnaround target: $20\text{s} - 35\text{s}$ per 60s Short.

Neither pipeline SHALL introduce branching hacks or conditional sprawl into the other pipeline's hot path.

#### Scenario: Lane profile declaration with image_animation visual pipeline (Happy Path)
- **Given** a raw lane configuration dictionary specifying `"visual_pipeline": "image_animation"`
- **When** `parse_lane(raw)` validates the document
- **Then** the returned `LaneProfile` MUST have `visual_pipeline == "image_animation"`
- **And** no validation errors SHALL be raised.

#### Scenario: Lane profile declaration with video_loop visual pipeline (Happy Path)
- **Given** a raw lane configuration dictionary specifying `"visual_pipeline": "video_loop"`
- **When** `parse_lane(raw)` validates the document
- **Then** the returned `LaneProfile` MUST have `visual_pipeline == "video_loop"`
- **And** no validation errors SHALL be raised.

#### Scenario: Rejection of invalid visual pipeline mode (Edge Case)
- **Given** a raw lane configuration dictionary specifying `"visual_pipeline": "unsupported_webgl"`
- **When** `parse_lane(raw)` validates the document
- **Then** the parser MUST raise a `ValueError` indicating invalid visual pipeline
- **And** list valid options (`{"beats", "director", "image_animation", "video_loop"}`).

### Requirement: Shared Core Media Tooling Architecture
Both `image_animation` and `video_loop` production lanes MUST utilize common, hardened underlying subsystems to eliminate code duplication and drift:
1. `src/media/visual_coherence.py`: Single Source of Truth (SSOT) for narrative act timing scaling (`timing_scales_to_audio`), brand-aligned filmic color grading (`build_coherent_color_grade`), safe-zone margins (`enforce_shorts_safe_zone`), and continuity validation (`validate_visual_continuity`).
2. `src/media/unified_encoder.py`: SSOT for atomic FFmpeg command construction, sidechain audio ducking under background music, EBU R128 loudness mastering ($I=-14.0\text{ LUFS}$), and asynchronous stderr draining.
3. `src/core/lanes.py`: SSOT for lane profile validation, word budgets, and cadence scheduling.

Duplication of audio ducking curves, color grading matrices, or FFmpeg subprocess invocation routines across lanes is strictly prohibited.

#### Scenario: Image-Animation lane executes shared visual coherence and unified encoder (Happy Path)
- **Given** an active run in an `image_animation` lane
- **When** `stage_08_loop` and `stage_09_render` execute
- **Then** scene manifest generation MUST invoke `timing_scales_to_audio` and `build_coherent_color_grade` from `src/media/visual_coherence.py`
- **And** rendering MUST delegate to `UnifiedEncoder` in `src/media/unified_encoder.py` for single-pass transcode and audio mastering.

#### Scenario: Video-Loop lane executes shared visual coherence and stream-copy flow (Happy Path)
- **Given** an active run in a `video_loop` lane
- **When** `stage_08_loop` and `stage_09_render` execute
- **Then** scene manifest generation MUST invoke `build_coherent_color_grade` and `enforce_shorts_safe_zone` from `src/media/visual_coherence.py`
- **And** rendering MUST invoke `UnifiedEncoder` or stream-copy muxer using shared EBU R128 audio mastering without code duplication.

#### Scenario: Code duplication verification across lane renderers (Anti-Duplication Invariant)
- **Given** static analysis scanning all render stages and media engines
- **When** checking for audio loudness normalization and ducking implementations
- **Then** all calls MUST resolve to `src/media/unified_encoder.py` or `src/media/loop_engine.py`
- **And** zero divergent loudness calculation algorithms SHALL exist.

### Requirement: Concurrency Isolation and Semaphore Controls
The system MUST isolate concurrent lane executions to prevent cross-lane resource starvation and filesystem collisions:
1. **Render Semaphores**:
   - Short video renders MUST be bounded by `_SHORT_RENDER_SEMAPHORE = 2` (maximum 2 concurrent short renders).
   - Longform video renders MUST be bounded by `_LONG_RENDER_SEMAPHORE = 1` (maximum 1 concurrent longform render).
   - A CPU-heavy `image_animation` render SHALL NOT monopolize semaphore slots reserved for other queues.
2. **Filesystem Isolation**: Each lane run MUST execute inside an isolated working directory `data/runs/{run_id}/` where all intermediate manifests, audio stems, and output MP4 files are written. Temporary assets SHALL NEVER be written to a shared root directory.
3. **Database Concurrency**: State updates and queue dispatching MUST use SQLite Write-Ahead Logging (WAL) with immediate worker lease transactions in `QueueRepository`, guaranteeing zero database locking deadlocks.

#### Scenario: Concurrent execution of short lanes under semaphore bound (Happy Path)
- **Given** two concurrent short video production runs (one `image_animation` and one `video_loop`)
- **When** both runs acquire render execution slots
- **Then** both runs MUST execute concurrently within the limit of `_SHORT_RENDER_SEMAPHORE = 2`
- **And** aggregate CPU utilization MUST remain within $\le 2.0$ CPU Cores.

#### Scenario: Third short run queues until semaphore release (Happy Path)
- **Given** two active short runs holding both slots of `_SHORT_RENDER_SEMAPHORE`
- **When** a third short run requests rendering
- **Then** the third run MUST wait non-blockingly on the semaphore
- **And** commence rendering only after one of the active runs completes and releases its lease.

#### Scenario: Work directory asset isolation (Happy Path)
- **Given** concurrent runs `run_001` and `run_002` processing identical channel themes
- **When** intermediate audio files and manifests are written
- **Then** `run_001` files MUST reside strictly under `data/runs/run_001/`
- **And** `run_002` files MUST reside strictly under `data/runs/run_002/`
- **And** no cross-run file overwrite SHALL occur.

### Requirement: Graceful Fallback and Configuration-Level Rollback
The system MUST provide automatic graceful degradation and configuration-level rollback for production resilience:
1. **Runtime Graceful Degradation**: If image animation synthesis (Ken Burns compilation, SVG overlay rasterization, or single-pass transcode) encounters missing assets, corruption, or unexpected exceptions, `stage_08_loop` and `stage_09_render` MUST catch the failure, emit a structured observability event, and fall back deterministically to catalog loop stream-copy composition without aborting the queue item.
2. **Configuration Rollback**: Production channels MUST support instantaneous switching between `image_animation` and `video_loop` pipelines via `config/lanes.json` or CLI flag `--visual-pipeline` with zero code deployment or schema migration.

#### Scenario: Automatic fallback to video loop upon image animation error (Edge Case)
- **Given** a story executing under `image_animation` visual pipeline
- **When** Ken Burns filter generation or still asset loading throws an unexpected exception
- **Then** the pipeline stage MUST catch the exception and log an error event
- **And** dynamically switch the composition strategy to `video_loop` catalog loop stream-copy
- **And** produce a valid output MP4 video file.

#### Scenario: CLI runtime override of lane visual pipeline (Happy Path)
- **Given** a lane configured by default as `image_animation`
- **When** the operator invokes `main.py run --lane horror-scp-shorts --visual-pipeline video_loop`
- **Then** the pipeline MUST execute the run using `video_loop` stream-copy mode
- **And** bypass still image animation transcoding.
