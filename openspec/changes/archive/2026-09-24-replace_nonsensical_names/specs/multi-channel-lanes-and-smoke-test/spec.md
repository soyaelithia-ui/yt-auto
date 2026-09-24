# Multi-Channel Lanes and Smoke Test Specification (Delta)

## MODIFIED Requirements

### Requirement: Canonical Channel Hierarchy and Alias Resolution
The system SHALL register `CanonicalChannel.HORROR = "horror"`, `CanonicalChannel.DRAMA = "drama"`, and `CanonicalChannel.SCIFI = "scifi"` as the authoritative primary members in `src/core/domain.py`. Legacy names `MOKU` and `AELITHIA` SHALL remain registered as backwards-compatible aliases pointing respectively to `HORROR` and `DRAMA`. The `canonical_channel()` function SHALL resolve both thematic channel names and legacy aliases deterministically without raising `AttributeError` or guessing unconfigured channels.

#### Scenario: Canonical horror and drama resolution
- GIVEN a channel string "horror" or "drama"
- WHEN `canonical_channel(input)` is invoked
- THEN it SHALL return `CanonicalChannel.HORROR` or `CanonicalChannel.DRAMA` respectively.

#### Scenario: Legacy Moku and Aelithia alias resolution
- GIVEN a legacy channel identifier "moku" or "aelithia"
- WHEN `canonical_channel(input)` is invoked
- THEN "moku" SHALL resolve to `CanonicalChannel.HORROR` and "aelithia" SHALL resolve to `CanonicalChannel.DRAMA`.

#### Scenario: Safe channel attribute access
- GIVEN a lane profile or raw channel identifier
- WHEN `parse_lane` or `resolve_voice_profile_for_lane` accesses the channel
- THEN it SHALL extract string identifiers safely without raising `AttributeError`.

### Requirement: Six-Lane Configuration Parity
`config/lanes.json` SHALL define exactly six production lanes using standard thematic naming:
1. `horror-scp-shorts` (channel: `"horror"`, 9:16 vertical)
2. `horror-horror-long` (channel: `"horror"`, 16:9 horizontal)
3. `drama-drama-shorts` (channel: `"drama"`, 9:16 vertical)
4. `drama-aita-long` (channel: `"drama"`, 16:9 horizontal)
5. `scifi-singularity-shorts` (channel: `"scifi"`, 9:16 vertical)
6. `scifi-singularity-long` (channel: `"scifi"`, 16:9 horizontal)

`src/core/lanes.py` SHALL map all legacy lane IDs (`moku-scp-shorts`, `moku-horror-long`, `aelithia-drama-shorts`, `aelithia-aita-long`, `horror-long`, `horror-shorts`, `drama-shorts`, `drama-long`) to the canonical production lanes through `LANE_ALIASES`.

#### Scenario: Canonical lane registration parity
- GIVEN `config/lanes.json` loaded by `load_lanes`
- WHEN configuration is parsed
- THEN exactly six production lanes SHALL be registered across channels `horror`, `drama`, and `scifi`.

#### Scenario: Backward-compatible legacy lane resolution
- GIVEN a legacy lane ID "moku-scp-shorts" or "aelithia-aita-long"
- WHEN `resolve_lane_for_run` executes
- THEN it SHALL resolve to the corresponding canonical lane profile without error.

#### Scenario: Thematic short alias resolution
- GIVEN a short alias "horror-long" or "drama-shorts"
- WHEN `resolve_lane_for_run` executes
- THEN it SHALL resolve to `horror-horror-long` or `drama-drama-shorts` respectively.

### Requirement: Narrative Generation and Curation Rule Naming
The system SHALL expose canonical narrative generator functions (`build_horror_short_narrative`, `build_drama_short_narrative`, `build_horror_longform_narrative`, `build_drama_longform_narrative`) in `src/templates/narratives.py` and canonical story collections (`HORROR_STORIES`, `DRAMA_STORIES`) in `src/templates/longform_stories.py`. `src/curators/text_splitter.py` SHALL key `LANE_CURATION_CONFIGS` by the canonical lane identifiers while retaining legacy aliases.

#### Scenario: Thematic narrative routing
- GIVEN channel "horror" or "drama" and video mode "short" or "longform"
- WHEN `build_channel_narrative` executes
- THEN it SHALL invoke the corresponding thematic narrative builder without referencing hardcoded legacy names.

#### Scenario: Curation configuration lookup by canonical lane
- GIVEN canonical lane `horror-scp-shorts` or `drama-aita-long`
- WHEN `LANE_CURATION_CONFIGS` is queried
- THEN it SHALL return dramatic roles, scene duration bounds, and tension profiles matching the lane.
