# Multi-Channel Lanes and Smoke Test Specification

## Purpose
Defines 3-channel lane parity across 9:16 Shorts and 16:9 Longform formats, registers canonical SciFi channel contracts, verifies stream-copy composition via smoke tests, and validates daemon readiness.

## Requirements

### Requirement: Canonical Thematic Channels and Bidirectional Alias Resolution
(Previously: Defined `CanonicalChannel` with `MOKU = "moku"`, `AELITHIA = "aelithia"`, and `SCIFI = "scifi"`)

The system SHALL establish canonical thematic identifiers `HORROR = "horror"`, `DRAMA = "drama"`, and `SCIFI = "scifi"` as the primary enum values of `CanonicalChannel` in `src/core/domain.py`. The system SHALL maintain `CanonicalChannel.MOKU` and `CanonicalChannel.AELITHIA` as backwards-compatible enum attributes resolving to `HORROR` and `DRAMA`. `canonical_channel()` and `CHANNEL_ALIASES` SHALL provide bidirectional resolution: mapping both `"horror"` and legacy `"moku"` to `CanonicalChannel.HORROR`, and both `"drama"` and legacy `"aelithia"` to `CanonicalChannel.DRAMA`. Lane resolution in `src/core/lanes.py` SHALL continue to handle channel attributes safely for both enum instances and raw strings without raising `AttributeError`.

#### Scenario: Canonical thematic channel resolution (Happy Path)
- **Given** canonical inputs `"horror"`, `"drama"`, or `"scifi"`
- **When** `canonical_channel(input)` is invoked
- **Then** it SHALL return `CanonicalChannel.HORROR`, `CanonicalChannel.DRAMA`, and `CanonicalChannel.SCIFI` respectively
- **And** `channel.value` SHALL return `"horror"`, `"drama"`, or `"scifi"`.

#### Scenario: Legacy fantasy alias backwards compatibility (Happy Path)
- **Given** legacy inputs `"moku"` or `"aelithia"`
- **When** `canonical_channel(input)` is invoked
- **Then** `"moku"` SHALL resolve to `CanonicalChannel.HORROR`
- **And** `"aelithia"` SHALL resolve to `CanonicalChannel.DRAMA`
- **And** `CanonicalChannel.MOKU == CanonicalChannel.HORROR` SHALL evaluate to `True`.

#### Scenario: Safe channel attribute access on enum and string (Edge Case)
- **Given** a lane profile or raw channel dictionary where `channel` is either a `CanonicalChannel` enum or a string
- **When** `parse_lane` or `resolve_voice_profile_for_lane` accesses the channel
- **Then** it SHALL extract string identifiers safely without raising `AttributeError`.

### Requirement: SciFi Story Type and Voice Profile Registration
The system SHALL include `"scifi"` in `ALLOWED_STORY_TYPES` in `src/core/lanes.py` and register voice profile `scifi_documentary_es` in `config/voice_profiles.json` using approved Edge-TTS neural voices at 0% speed.

#### Scenario: SciFi story type validation
- GIVEN a lane configuration with `"story_type": "scifi"`
- WHEN `parse_lane` validates the lane definition
- THEN validation SHALL pass without raising `ValueError`.

#### Scenario: SciFi voice profile lookup
- GIVEN a lane requesting profile `"scifi_documentary_es"`
- WHEN `resolve_voice_profile_for_lane` queries voice profiles
- THEN it SHALL return approved documentary voices complying with -14 LUFS loudness and ducking rules.

### Requirement: Canonical Thematic Six-Lane Configuration Parity and Declarative Visual Pipelines
(Previously: Defined six production lanes with declarative visual pipelines, but longform director lanes `horror-horror-long` and `drama-aita-long` were coerced at runtime to single-loop mode unless `FORCE_MULTISCENE=1` was manually supplied in the environment)

`config/lanes.json` and `src/core/lanes.py` SHALL define exactly six production lanes using canonical thematic IDs across three channels (`horror`, `drama`, `scifi`):
1. `horror-scp-shorts` (9:16 vertical, duration target 90s–150s, `visual_pipeline`: `image_animation`)
2. `horror-horror-long` (16:9 horizontal, duration target 600s, `visual_pipeline`: `director`)
3. `drama-drama-shorts` (9:16 vertical, duration target 90s–150s, `visual_pipeline`: `image_animation`)
4. `drama-aita-long` (16:9 horizontal, duration target 600s, `visual_pipeline`: `director`)
5. `scifi-singularity-shorts` (9:16 vertical, duration target 90s–150s, `visual_pipeline`: `image_animation`)
6. `scifi-singularity-long` (16:9 horizontal, duration target 600s, `visual_pipeline`: `video_loop`)

Each lane document in `config/lanes.json` SHALL declare an explicit `visual_pipeline` property choosing between:
- `video_loop`: Pre-baked catalog loops, stream-copy (`-c:v copy`), and soft subtitle track muxing (`mov_text`).
- `image_animation`: Curated still imagery, smoothstep Ken Burns camera motion, dynamic SVG overlays, and single-pass atomic libx264 transcode.
- `director`: Canonical multi-act narrative assembly. When configured on horizontal longform lanes (`horror-horror-long`, `drama-aita-long`), the engine SHALL execute the Hybrid Multi-Act Director pipeline (4–8 acts, multi-loop catalog resolution, stream-copy concat, YouTube chapters, mov_text subtitles) without being coerced into single continuous loop mode.
- `beats`: Narrative montage assembly.

`src/core/lanes.py` SHALL validate `visual_pipeline` against `ALLOWED_VISUAL_PIPELINES = frozenset({"beats", "director", "image_animation", "video_loop"})`. Engine mode resolution in `src/pipeline/utils.py` and `src/pipeline/executor.py` SHALL validate and preserve `director` mode on horizontal longform lanes, routing execution to multi-act stream-copy composition instead of falling back to single loop repetition. The lane registry SHALL continue to maintain `LANE_ALIASES` mapping legacy fantasy identifiers (`moku-*`, `aelithia-*`) to their canonical thematic counterparts.

#### Scenario: Longform director lanes validate and route to hybrid multi-act pipeline (Happy Path)
- **Given** lane `horror-horror-long` or `drama-aita-long` configured with `"visual_pipeline": "director"`
- **When** `_resolve_engine_mode` or lane validator executes
- **Then** `is_multiscene_mode` SHALL evaluate to `True`
- **And** `is_loop_mode` SHALL evaluate to `False`
- **And** the pipeline SHALL NOT coerce the lane into single-loop mode unless `FORCE_SINGLE_LOOP=1` is explicitly set.

#### Scenario: Six canonical thematic lanes load with declarative visual pipelines (Happy Path)
- **Given** `config/lanes.json` loaded by `load_lanes()`
- **When** lane configurations are parsed into `LaneProfile` instances
- **Then** exactly six canonical production lanes SHALL be registered
- **And** every lane SHALL define a valid `visual_pipeline` belonging to `ALLOWED_VISUAL_PIPELINES`
- **And** horizontal longform lanes `horror-horror-long` and `drama-aita-long` SHALL preserve the `director` visual pipeline.

#### Scenario: Legacy lane ID resolution retains visual pipeline configuration (Happy Path)
- **Given** a run command specifying a legacy lane alias (e.g. `--lane moku-horror-long` or `--lane aelithia-aita-long`)
- **When** `resolve_lane_for_run()` executes
- **Then** it SHALL resolve the legacy alias to `horror-horror-long` or `drama-aita-long`
- **And** preserve the configured `director` visual pipeline attributes.

#### Scenario: Rejection of unsupported visual pipeline paradigm (Edge Case)
- **Given** a lane configuration specifying `"visual_pipeline": "custom_webgl_renderer"`
- **When** `parse_lane()` executes
- **Then** it SHALL raise a `ValueError` indicating that the visual pipeline is not recognized
- **And** execution SHALL halt before any narrative or media generation is scheduled.

---

### Requirement: SciFi Narrative Generation and Curation Rules
The system SHALL implement SciFi narrative generators in `src/templates/narratives.py` and register lane curation profiles in `src/agents/script_curator.py` for `scifi-singularity-shorts`, `scifi-singularity-long`, and `aelithia-drama-shorts`.

#### Scenario: SciFi narrative routing
- GIVEN channel `scifi` and mode `short` or `longform`
- WHEN `build_channel_narrative` executes
- THEN it SHALL invoke the dedicated SciFi narrative builder.

#### Scenario: Lane curation configuration lookup
- GIVEN lane `scifi-singularity-shorts` or `aelithia-drama-shorts`
- WHEN `LANE_CURATION_CONFIGS` is queried
- THEN it SHALL return dramatic roles and scene duration bounds matching the lane.

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

### Requirement: Production Supervisor Daemon Readiness
`deploy/ctl.sh` SHALL manage `yt-lanes-daemon` and `yt-review-bot` workers, enforcing singleton locks and reporting active operational status.

#### Scenario: Supervisor daemon lifecycle
- GIVEN the operator executes `./deploy/ctl.sh start all`
- WHEN supervisor sessions start
- THEN `./deploy/ctl.sh status` SHALL report active status with valid PIDs.

#### Scenario: Singleton lock protection
- GIVEN an active daemon holding the scheduler lock
- WHEN a second process attempts startup
- THEN the second process SHALL exit cleanly without state corruption.
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
