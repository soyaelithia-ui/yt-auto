# Delta for Multi-Channel Lanes and Smoke Test

## RENAMED Requirements

### Requirement: Canonical SciFi Channel and Safe Enum Resolution -> Canonical Thematic Channels and Bidirectional Alias Resolution

(Reason: Generalize SciFi enum resolution to all canonical thematic channels and bidirectional aliases)

### Requirement: Six-Lane Configuration Parity -> Canonical Thematic Six-Lane Configuration Parity

(Reason: Canonicalize six-lane IDs to thematic prefixes)

## MODIFIED Requirements

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

### Requirement: Canonical Thematic Six-Lane Configuration Parity
(Previously: Defined six production lanes with fantasy prefix IDs `moku-scp-shorts`, `moku-horror-long`, `aelithia-drama-shorts`, `aelithia-aita-long`, `scifi-singularity-shorts`, `scifi-singularity-long`)

`config/lanes.json` and `src/core/lanes.py` SHALL define exactly six production lanes using canonical thematic IDs:
- `horror-scp-shorts` (9:16 vertical)
- `horror-horror-long` (16:9 horizontal)
- `drama-drama-shorts` (9:16 vertical)
- `drama-aita-long` (16:9 horizontal)
- `scifi-singularity-shorts` (9:16 vertical)
- `scifi-singularity-long` (16:9 horizontal)

The lane registry SHALL register bidirectional alias resolution (`LANE_ALIASES`) mapping legacy lane names (`moku-scp-shorts`, `moku-horror-long`, `aelithia-drama-shorts`, `aelithia-aita-long`) to their canonical thematic counterparts.

#### Scenario: Six canonical thematic lanes load and validate (Happy Path)
- **Given** `config/lanes.json` loaded by `load_lanes`
- **When** lane configuration is parsed
- **Then** exactly six production lanes SHALL be registered across all three channels (`horror`, `drama`, `scifi`)
- **And** every lane ID SHALL use the canonical thematic prefix (`horror-*`, `drama-*`, `scifi-*`).

#### Scenario: Legacy lane ID resolution via alias registry (Happy Path)
- **Given** a run command specifying a legacy lane identifier (e.g. `--lane moku-scp-shorts`)
- **When** `resolve_lane_for_run` executes
- **Then** it SHALL resolve the legacy ID to canonical `horror-scp-shorts`
- **And** execution SHALL proceed without error.

#### Scenario: Unconfigured lane rejection (Edge Case)
- **Given** a run command with an unknown lane identifier not present in canonical lanes or `LANE_ALIASES`
- **When** `resolve_lane_for_run` executes
- **Then** it SHALL raise `ValueError` listing valid canonical lane IDs.

### Requirement: End-to-End Generate-Only Smoke Test
(Previously: Verified stream-copy video generation using legacy lane IDs)

The system SHALL execute offline video generation across all six canonical thematic lanes using `main.py run --generate-only`. Rendering SHALL use stream-copy for pre-baked loops (<5s transcode overhead) and produce zero external network requests. The test suite SHALL also verify that invoking smoke tests via legacy lane aliases (`moku-*`, `aelithia-*`) succeeds identically through alias resolution.

#### Scenario: Six canonical lane stream-copy execution (Happy Path)
- **Given** all six canonical lanes and pre-baked master loops in `assets/loops/`
- **When** `main.py run -c <channel> --lane <canonical_lane_id> --generate-only` is executed for each lane
- **Then** all six runs SHALL produce valid MP4 files via stream copy without full video re-encoding.

#### Scenario: Legacy lane alias smoke test execution (Happy Path)
- **Given** smoke test commands executed using legacy lane IDs (e.g. `--lane moku-horror-long`)
- **When** media generation runs in `--generate-only` mode
- **Then** the system SHALL resolve the alias to `horror-horror-long` and produce the target MP4 file cleanly.

## ADDED Requirements

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
