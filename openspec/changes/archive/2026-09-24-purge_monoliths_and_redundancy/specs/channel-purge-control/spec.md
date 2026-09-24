# Delta for Channel Purge Control

## RENAMED Requirements

### Requirement: Dry-Run Catalog Inspection -> Dry-Run Catalog Inspection with Canonical Channel Default

(Reason: Standardize default target channel parameter to canonical horror)

## MODIFIED Requirements

### Requirement: Dry-Run Catalog Inspection with Canonical Channel Default
(Previously: Defaulted candidate target channel to `"moku"` in CLI arguments and inspection examples)

The purge control tool MUST standardize its default target channel parameter to canonical `'horror'`. The tool MUST perform a non-destructive dry-run inspection by default or when `--dry-run` is explicitly provided, retrieving all video metadata without issuing mutation or deletion requests. Target channel inputs MUST be resolved through `canonical_channel()`, seamlessly accepting both canonical identifiers (`'horror'`, `'drama'`, `'scifi'`) and legacy aliases (`'moku'`, `'aelithia'`).

#### Scenario: Default dry-run catalog inspection targets canonical horror channel (Happy Path)
- **Given** the purge CLI executed without an explicit `--channel` argument
- **When** catalog inspection begins in dry-run mode
- **Then** the system MUST resolve target channel to canonical `'horror'`
- **And** the system MUST retrieve candidate videos for the horror channel without calling YouTube Data API `videos().delete()`
- **And** the summary report MUST specify channel `'horror'`.

#### Scenario: Dry-run inspection via legacy alias "moku" resolves to horror channel (Happy Path)
- **Given** the purge CLI executed with `--channel moku` and `--dry-run`
- **When** catalog inspection begins
- **Then** the system MUST resolve `'moku'` to canonical `'horror'`
- **And** candidate inspection MUST query credentials and catalog for canonical `'horror'`.

#### Scenario: Dry-run inspection on empty channel catalog (Edge Case)
- **Given** a target channel identifier with 0 uploaded videos
- **When** the purge inspection is executed in dry-run mode
- **Then** the system MUST return an empty candidate list with exit code 0
- **And** the summary report MUST indicate 0 candidate items without error.

#### Scenario: Unknown channel identifier rejection (Edge Case)
- **Given** an invalid channel identifier (e.g. `--channel unknown_channel`)
- **When** `canonical_channel()` resolution is attempted
- **Then** the system MUST raise `ValueError` listing valid canonical channels and accepted aliases.

### Requirement: Channel Ownership Validation and Failure Reporting
(Previously: Validated channel ownership against legacy channel configurations)

The purge control tool MUST verify that each candidate video ID belongs to the expected canonical channel ID before issuing deletion requests, recording per-video outcomes in a structured report. Channel IDs and OAuth credentials MUST be resolved via `canonical_channel()`, ensuring that invocations using legacy aliases (`'moku'`, `'aelithia'`) map transparently to the expected channel ID for canonical `'horror'` or `'drama'`.

#### Scenario: Video ownership verification matches canonical channel (Happy Path)
- **Given** candidate video `"vid_123"` belonging to expected channel ID `"UC_HORROR_01"`
- **When** deletion is processed for canonical channel `'horror'`
- **Then** the video is verified and deleted successfully, logged in the output report.

#### Scenario: Ownership verification succeeds when invoked with legacy alias (Happy Path)
- **Given** candidate video `"vid_123"` belonging to expected horror channel ID
- **When** purge is executed with `--channel moku`
- **Then** the system MUST map `'moku'` to canonical horror expected channel ID
- **And** ownership validation MUST succeed without permission error.

#### Scenario: Candidate video belongs to an unexpected channel ID (Edge Case)
- **Given** candidate video `"vid_999"` whose snippet channel ID does not match the configured expected channel ID
- **When** ownership validation is evaluated
- **Then** the system MUST reject deletion with `PermissionError`
- **And** the batch report MUST log the video as skipped/rejected without affecting remaining items.

### Requirement: Automated Underperforming Video Pruning with Mandatory Grace Period
(Previously: Tracked daily deletion ceilings without explicit canonical channel indexing)

The pruning engine MUST evaluate candidates for automated deletion using strict multi-tier safety checks:
1. **Mandatory Grace Period**: Only videos with upload age $\ge 24\text{ hours}$ ($\ge 86,400\text{s}$) SHALL be eligible for underperformance evaluation; videos younger than 24 hours MUST NOT be deleted.
2. **Threshold Violation**: A video SHALL qualify for pruning only if its computed empirical success score is strictly below the survival threshold (`actual_success_score < 25.0`) AND its total view count is below the threshold floor (`views < 50`).
3. **Bounded Deletion Ceiling**: The engine MUST NOT delete more than 2 videos per canonical channel within any rolling 24-hour window. Daily deletion quotas MUST be tracked strictly under the canonical channel name (`horror`, `drama`, `scifi`).
4. **Kill Switch**: If `AUTO_PRUNE_ENABLED=false` or `--disable-prune` is set, all automated deletions MUST be halted immediately.

#### Scenario: Pruning sweep tracks daily ceiling per canonical channel across alias invocations (Happy Path)
- **Given** 1 video was pruned today under canonical channel `'horror'`
- **When** a subsequent pruning sweep is executed with `--channel moku`
- **Then** the pruner MUST resolve the alias to `'horror'`
- **And** the engine MUST recognize that 1 deletion has already occurred, permitting at most 1 additional deletion in the rolling 24-hour window.

#### Scenario: Underperforming video older than 24h is pruned safely (Happy Path)
- **Given** a video uploaded 48 hours ago with 12 views, 0 likes, and an empirical score of 8.5
- **And** fewer than 2 videos have been pruned for the canonical channel in the last 24 hours
- **And** `AUTO_PRUNE_ENABLED` is true
- **When** the automated pruning sweep executes
- **Then** the video MUST be deleted via YouTube Data API `videos().delete()`
- **And** the database record MUST be marked `"PURGED_UNDERPERFORMING"`
- **And** the daily canonical channel prune counter MUST be incremented by 1.
