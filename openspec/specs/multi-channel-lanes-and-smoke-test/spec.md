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
### Requirement: Parameter Signature Sanitization and Dynamic Manifest Defaults
Public function signatures, CLI entrypoints, and manifest models in `src/scene_manifest.py`, `src/daemon.py`, and `src/core/lanes.py` SHALL NOT default to fantasy channel names (`"moku"`). Default channel parameters MUST specify canonical `"horror"` or resolve dynamically based on the requested lane or context. Scene manifest defaults SHALL derive channel stamp overlays dynamically or default to empty/canonical stamps, removing `stamp_text="[MOKU]"`.

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
