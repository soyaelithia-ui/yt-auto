# Multi-Channel Lanes and Smoke Test Specification (Delta)

## Purpose
Defines 3-channel lane parity across 9:16 Shorts and 16:9 Longform formats, registers canonical SciFi channel contracts, verifies stream-copy composition via smoke tests, validates daemon readiness, and establishes multi-act director lane validation and smoke contracts for `horror-horror-long` and `drama-aita-long`.

## MODIFIED Requirements

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

### Requirement: End-to-End Generate-Only Smoke Test Across Dual Paradigms and Multi-Act Director
(Previously: Verified stream-copy video generation for pre-baked loops and single-pass still image animation, but did not verify multi-act stream-copy concatenation or YouTube chapter metadata formatting for longform director lanes)

The system SHALL verify offline video generation across all six canonical thematic lanes and visual pipeline paradigms using `main.py run --lane <lane_id> --generate-only`. The smoke test suite SHALL validate that:
1. Lanes configured with `video_loop` execute via stream-copy (`-c:v copy`) and soft subtitle muxing (`-c:s mov_text`), completing in $< 5.0\text{ seconds}$ with CPU utilization $< 0.20\text{ Cores}$.
2. Lanes configured with `image_animation` execute via `UnifiedEncoder` atomic single-pass transcode, compiling smoothstep Ken Burns camera motion and dynamic SVG overlays into a valid MP4 file without intermediate disk chunks or memory leaks.
3. Lanes configured with `director` on horizontal longform formats (`horror-horror-long`, `drama-aita-long`):
   - Execute multi-act narrative partitioning into 4–8 structured acts with progressive tension scores (1–5).
   - Resolve distinct horizontal catalog loops per act, populating `ctx.scene_bg_list` and `ctx.shot_durations`.
   - Assemble the video via zero-transcode stream-copy concat (`-c:v copy`), completing in $\le 45\text{ seconds}$ with aggregate CPU utilization $\le 120\%$.
   - Soft-mux subtitles into the MP4 container (`-c:s mov_text`) and export an `.srt` sidecar.
   - Generate valid clickable YouTube chapter markers in `ctx.youtube_description` complying with YouTube constraints (starts at `00:00`, $\ge 3$ chapters, each $\ge 10\text{ seconds}$).
4. Zero external network requests, Playwright subprocesses, or unauthenticated API calls SHALL be dispatched during smoke testing.

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
