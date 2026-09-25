# Multi-Channel Lanes and Smoke Test Specification (Delta)

## Purpose
Extends multi-channel lane verification to cover daemon-level multi-lane concurrent execution contracts, offline synthetic multi-lane daemon turn verification across enabled production lanes, and eradication of legacy channel aliases (`moku`, `aelithia`) from daemon test suites.

## RENAMED Requirements

### Requirement: End-to-End Generate-Only Smoke Test Across Dual Paradigms and Multi-Act Director -> End-to-End Generate-Only Smoke Test Across Dual Paradigms, Multi-Act Director, and Daemon Multi-Lane Execution

(Reason: Extend smoke test contracts to cover daemon multi-lane concurrent execution)

### Requirement: Parameter Signature Sanitization and Dynamic Manifest Defaults -> Parameter Signature Sanitization, Dynamic Manifest Defaults, and Daemon Test Suite Alias Eradication

(Reason: Eradicate legacy channel aliases and fixtures across daemon test suites)

## MODIFIED Requirements

### Requirement: End-to-End Generate-Only Smoke Test Across Dual Paradigms, Multi-Act Director, and Daemon Multi-Lane Execution
(Previously: Verified offline video generation across all canonical lanes via individual single-lane CLI invocations `main.py run --lane <lane_id> --generate-only`, but lacked contracts for multi-lane concurrent daemon turn verification, thread pool dispatching, cadence advancement, and clean shutdown under synthetic test harnesses)

The system SHALL verify offline video generation across all six canonical thematic lanes and visual pipeline paradigms using both single-lane generate-only invocations (`main.py run --lane <lane_id> --generate-only`) AND synthetic multi-lane daemon turn execution (`tests/integration/test_daemon_multi_lane_turn.py`).

The smoke test and verification suites SHALL validate that:
1. Lanes configured with `video_loop` execute via stream-copy (`-c:v copy`) and soft subtitle muxing (`-c:s mov_text`), completing in $< 5.0\text{ seconds}$ with CPU utilization $< 0.20\text{ Cores}$.
2. Lanes configured with `image_animation` execute via `UnifiedEncoder` atomic single-pass transcode, compiling smoothstep Ken Burns camera motion and dynamic SVG overlays into a valid MP4 file without intermediate disk chunks or memory leaks.
3. Lanes configured with `director` on horizontal longform formats (`horror-horror-long`, `drama-aita-long`):
   - Execute multi-act narrative partitioning into 4–8 structured acts with progressive tension scores (1–5).
   - Resolve distinct horizontal catalog loops per act, populating `ctx.scene_bg_list` and `ctx.shot_durations`.
   - Assemble the video via zero-transcode stream-copy concat (`-c:v copy`), completing in $\le 45\text{ seconds}$ with aggregate CPU utilization $\le 120\%$.
   - Soft-mux subtitles into the MP4 container (`-c:s mov_text`) and export an `.srt` sidecar.
   - Generate valid clickable YouTube chapter markers in `ctx.youtube_description` complying with YouTube constraints (starts at `00:00`, $\ge 3$ chapters, each $\ge 10\text{ seconds}$).
4. Synthetic Offline Multi-Lane Daemon Turn Verification:
   The integration smoke test harness SHALL execute multi-lane daemon turns (`LaneDaemonOrchestrator` / `start_daemon_lanes`) across enabled production lanes under synthetic offline conditions:
   - Verifying concurrent worker dispatch up to worker pool limits (`YT_MAX_PARALLEL_LANES=3`).
   - Verifying atomic SQLite WAL lane leasing (`lane_leases`) without lock contention or deadlocks.
   - Verifying cadence commitment advancing `next_due_at = fired_at + min_gap_seconds` upon successful turns and backoff ramping (60s–120s) on empty picks.
   - Verifying graceful shutdown upon completion or `SIGINT` with zero orphaned child processes.
5. Zero external network requests, Playwright subprocesses, or unauthenticated API calls SHALL be dispatched during smoke testing or synthetic daemon execution.

#### Scenario: Synthetic offline multi-lane daemon turn verification (Happy Path)
- **Given** an offline environment with seeded synthetic story records across enabled production lanes
- **When** `test_daemon_multi_lane_turn.py` executes a multi-lane daemon turn
- **Then** the daemon MUST dispatch due lanes concurrently across the worker thread pool
- **And** acquire atomic leases in `lane_leases` with unique owner signatures
- **And** advance the cadence ceiling (`next_due_at = fired_at + min_gap_seconds`) upon completion
- **And** shut down cleanly within $\le 5$ seconds without leaking child processes.

#### Scenario: Longform multi-act director smoke test validates stream-copy and chapter metadata (Happy Path)
- **Given** a longform lane `horror-horror-long` or `drama-aita-long` configured with `visual_pipeline: "director"`
- **When** `main.py run --lane <lane_id> --generate-only` executes
- **Then** the render stage MUST produce a playable MP4 video file via stream-copy (`-c:v copy`)
- **And** `ctx.scene_bg_list` MUST contain distinct loop references corresponding to narrative acts
- **And** `ctx.youtube_description` MUST contain formatted YouTube chapter markers starting at `00:00` with $\ge 3$ chapters of $\ge 10\text{s}$ duration
- **And** an `.srt` subtitle sidecar file MUST be emitted in the output directory.

#### Scenario: Video-loop paradigm smoke test execution (Happy Path)
- **Given** a lane configured with `visual_pipeline: "video_loop"` and pre-baked loops in `assets/loops/`
- **When** `main.py run --lane <lane_id> --generate-only` is executed
- **Then** the render stage MUST produce a playable MP4 video file via stream-copy (`-c:v copy`)
- **And** elapsed composition time MUST be under 5.0 seconds.

#### Scenario: Image-animation paradigm smoke test execution (Happy Path)
- **Given** a lane configured with `visual_pipeline: "image_animation"` and curated still assets
- **When** `main.py run --lane <lane_id> --generate-only` is executed
- **Then** the render stage MUST produce a playable MP4 video file via single-pass atomic encoding
- **And** the output video MUST contain smoothstep Ken Burns motion
- **And** peak memory consumption MUST remain within $\le 2.0\text{ GiB RAM}$ (RSS $< 800\text{ MiB}$).

#### Scenario: Offline network isolation during smoke tests (Security & Policy Invariant)
- **Given** smoke test execution across all six lanes in `--generate-only` mode
- **When** network socket activity is monitored
- **Then** zero external HTTP/HTTPS requests SHALL be emitted
- **And** zero Playwright browser instances SHALL be spawned.

---

### Requirement: Parameter Signature Sanitization, Dynamic Manifest Defaults, and Daemon Test Suite Alias Eradication
(Previously: Enforced parameter sanitization in public signatures and manifests, but permitted unit test fixtures and test cases in `tests/unit/test_daemon_lanes.py` and `tests/unit/test_lane_scheduler.py` to reference legacy channel identifiers `moku` and `aelithia`)

Public function signatures, CLI entrypoints, and manifest models in `src/scene_manifest.py`, `src/daemon.py`, `src/orchestrator/scheduler.py`, and `src/core/lanes.py` SHALL NOT default to fantasy channel names (`"moku"`). Default channel parameters MUST specify canonical `"horror"` or resolve dynamically based on the requested lane or context. Scene manifest defaults SHALL derive channel stamp overlays dynamically or default to empty/canonical stamps, removing `stamp_text="[MOKU]"`.

Furthermore, all daemon unit tests (`tests/unit/test_daemon_lanes.py`), scheduler unit tests (`tests/unit/test_lane_scheduler.py`), and integration test suites SHALL eradicate references to legacy fantasy channel names (`"moku"`, `"aelithia"`) and legacy lane aliases (`moku-*`, `aelithia-*`), using canonical thematic identifiers (`"horror"`, `"drama"`, `"scifi"`) and canonical production lane IDs (`horror-scp-shorts`, `horror-horror-long`, `drama-aita-long`, `drama-drama-shorts`) exclusively in test cases, fixtures, and assertions.

#### Scenario: Daemon test suites execute exclusively with canonical thematic channel IDs (Happy Path)
- **Given** test execution of `pytest tests/unit/test_daemon_lanes.py tests/unit/test_lane_scheduler.py`
- **When** tests create queues, seed stories, and verify lane dispatches
- **Then** all test fixtures and mock parameters SHALL use `"horror"` and `"drama"` channel IDs
- **And** zero tests SHALL fail due to legacy `"moku"` or `"aelithia"` identifier mismatches.

#### Scenario: Scene manifest defaults to canonical horror channel and clean stamp (Happy Path)
- **Given** an invocation of `create_scene_manifest()` without explicit channel or stamp parameters
- **When** default values are initialized
- **Then** `channel_name` SHALL default to `"horror"`
- **And** `stamp_text` SHALL NOT be `"[MOKU]"` (defaulting to `None` or dynamic branding).

#### Scenario: Lane-driven dynamic branding stamp derivation (Happy Path)
- **Given** a scene manifest built for lane `drama-aita-long`
- **When** branding metadata is resolved
- **Then** `channel_name` SHALL resolve to `"drama"`
- **And** watermark stamps SHALL reflect drama branding rather than fantasy identifiers.
