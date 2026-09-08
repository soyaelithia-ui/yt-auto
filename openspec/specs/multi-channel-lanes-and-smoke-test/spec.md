# Multi-Channel Lanes and Smoke Test Specification

## Purpose
Defines 3-channel lane parity across 9:16 Shorts and 16:9 Longform formats, registers canonical SciFi channel contracts, verifies stream-copy composition via smoke tests, and validates daemon readiness.

## Requirements

### Requirement: Canonical SciFi Channel and Safe Enum Resolution
The system SHALL register `CanonicalChannel.SCIFI = "scifi"` in `src/core/domain.py` and map aliases (`scifi`, `singularidad_scifi`, `singularidad-scifi`). Lane resolution in `src/core/lanes.py` SHALL handle channel attributes safely for both enum instances and string values without raising `AttributeError`.

#### Scenario: Canonical SciFi alias resolution
- GIVEN an alias "scifi", "singularidad_scifi", or "singularidad-scifi"
- WHEN `canonical_channel(input)` is invoked
- THEN it SHALL return `CanonicalChannel.SCIFI`.

#### Scenario: Safe channel attribute access
- GIVEN a lane profile or raw channel identifier
- WHEN `parse_lane` or `resolve_voice_profile_for_lane` accesses the channel
- THEN it SHALL extract string identifiers safely without raising `AttributeError`.

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

### Requirement: Six-Lane Configuration Parity
`config/lanes.json` SHALL define exactly six production lanes: `moku-scp-shorts` (9:16) and `moku-horror-long` (16:9); `aelithia-drama-shorts` (9:16) and `aelithia-aita-long` (16:9); `scifi-singularity-shorts` (9:16) and `scifi-singularity-long` (16:9).

#### Scenario: Lane parity validation
- GIVEN `config/lanes.json` loaded by `load_lanes`
- WHEN configuration is parsed
- THEN exactly six production lanes SHALL be registered across all three channels.

#### Scenario: Unconfigured lane rejection
- GIVEN a run command with an unconfigured lane identifier
- WHEN `resolve_lane_for_run` executes
- THEN it SHALL raise `ValueError` listing valid lane IDs for that channel.

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

### Requirement: End-to-End Generate-Only Smoke Test
The system SHALL execute offline video generation across all six lanes using `main.py run --generate-only`. Rendering SHALL use stream-copy for pre-baked loops (<5s transcode overhead) and produce zero external network requests.

#### Scenario: Six-lane stream-copy execution
- GIVEN all six lanes and pre-baked master loops in `assets/loops/`
- WHEN `main.py run -c <channel> --lane <lane_id> --generate-only` is executed for each lane
- THEN all six runs SHALL produce valid MP4 files via stream copy without full video re-encoding.

#### Scenario: Zero network egress in test mode
- GIVEN smoke tests executed with `--generate-only`
- WHEN media composition finishes
- THEN the system SHALL NOT contact external YouTube publishing endpoints.

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
