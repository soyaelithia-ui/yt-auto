# Multi-Channel Lanes and Smoke Test Specification (Delta)

## Purpose
Extends the six-lane canonical configuration matrix and offline smoke test suite to support declarative visual pipeline paradigms, explicitly configuring and verifying both `image_animation` and `video_loop` execution paths alongside existing `beats` and `director` modes.

## RENAMED Requirements

### Requirement: Canonical Thematic Six-Lane Configuration Parity -> Canonical Thematic Six-Lane Configuration Parity and Declarative Visual Pipelines

(Reason: Incorporate declarative visual pipeline support in six-lane configuration parity)

### Requirement: End-to-End Generate-Only Smoke Test -> End-to-End Generate-Only Smoke Test Across Dual Paradigms

(Reason: Extend offline generate-only smoke testing across dual visual pipeline paradigms)

## MODIFIED Requirements

### Requirement: Canonical Thematic Six-Lane Configuration Parity and Declarative Visual Pipelines
(Previously: Defined six production lanes with canonical thematic IDs configured strictly with generic "beats" or "director" modes without declarative support for distinct image animation and video loop visual pipelines)

`config/lanes.json` and `src/core/lanes.py` SHALL define exactly six production lanes using canonical thematic IDs across three channels (`horror`, `drama`, `scifi`):
1. `horror-scp-shorts` (9:16 vertical, duration target 90s–150s)
2. `horror-horror-long` (16:9 horizontal, duration target 600s)
3. `drama-drama-shorts` (9:16 vertical, duration target 90s–150s)
4. `drama-aita-long` (16:9 horizontal, duration target 600s)
5. `scifi-singularity-shorts` (9:16 vertical, duration target 90s–150s)
6. `scifi-singularity-long` (16:9 horizontal, duration target 600s)

Each lane document in `config/lanes.json` SHALL declare an explicit `visual_pipeline` property choosing between:
- `video_loop`: Pre-baked catalog loops, stream-copy (`-c:v copy`), and soft subtitle track muxing (`mov_text`).
- `image_animation`: Curated still imagery, smoothstep Ken Burns camera motion, dynamic SVG overlays, and single-pass atomic libx264 transcode.
- `beats` / `director`: Canonical multi-act narrative assembly modes.

`src/core/lanes.py` SHALL validate `visual_pipeline` against `ALLOWED_VISUAL_PIPELINES = frozenset({"beats", "director", "image_animation", "video_loop"})`. The lane registry SHALL continue to maintain `LANE_ALIASES` mapping legacy fantasy identifiers (`moku-*`, `aelithia-*`) to their canonical thematic counterparts.

#### Scenario: Six canonical thematic lanes load with declarative visual pipelines (Happy Path)
- **Given** `config/lanes.json` loaded by `load_lanes()`
- **When** lane configurations are parsed into `LaneProfile` instances
- **Then** exactly six canonical production lanes SHALL be registered
- **And** every lane SHALL define a valid `visual_pipeline` belonging to `ALLOWED_VISUAL_PIPELINES`
- **And** both `image_animation` and `video_loop` paradigm lanes SHALL be represented in the configuration.

#### Scenario: Legacy lane ID resolution retains visual pipeline configuration (Happy Path)
- **Given** a run command specifying a legacy lane alias (e.g. `--lane moku-scp-shorts`)
- **When** `resolve_lane_for_run()` executes
- **Then** it SHALL resolve the legacy alias to `horror-scp-shorts`
- **And** preserve the configured `visual_pipeline` attributes from the canonical lane.

#### Scenario: Rejection of unsupported visual pipeline paradigm (Edge Case)
- **Given** a lane configuration specifying `"visual_pipeline": "custom_webgl_renderer"`
- **When** `parse_lane()` executes
- **Then** it SHALL raise a `ValueError` indicating that the visual pipeline is not recognized
- **And** execution SHALL halt before any narrative or media generation is scheduled.

### Requirement: End-to-End Generate-Only Smoke Test Across Dual Paradigms
(Previously: Verified stream-copy video generation for pre-baked loops across legacy and canonical lanes without verifying still image Ken Burns animation or SVG overlay pipelines)

The system SHALL verify offline video generation across all six canonical thematic lanes and visual pipeline paradigms using `main.py run --generate-only`. The smoke test suite SHALL validate that:
1. Lanes configured with `video_loop` execute via stream-copy (`-c:v copy`) and soft subtitle muxing (`-c:s mov_text`), completing in $< 5.0\text{ seconds}$ with CPU utilization $< 0.20\text{ Cores}$.
2. Lanes configured with `image_animation` execute via `UnifiedEncoder` atomic single-pass transcode, compiling smoothstep Ken Burns camera motion and dynamic SVG overlays into a valid MP4 file without intermediate disk chunks or memory leaks.
3. Zero external network requests, Playwright subprocesses, or unauthenticated API calls SHALL be dispatched during smoke testing.

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
