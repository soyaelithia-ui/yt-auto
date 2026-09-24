# Specification: Channel Purge Control

## Capability Overview
The `channel-purge-control` capability provides interactive and programmatic mechanisms to inspect, audit, and safely delete YouTube video catalogs associated with managed channels while preventing unauthorized cross-channel deletion and API quota exhaustion.

## Requirements

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

### Requirement: Interactive Confirmation Safeguard and Autonomous Prune Override
The purge control tool MUST require explicit affirmative user confirmation before initiating non-dry-run video deletions, unless an explicit `--force`, `--non-interactive`, or autonomous criteria-based pruning execution mode is active with all safety bounds verified.
(Previously: Required interactive "DELETE" confirmation unless an explicit `--force` or `--non-interactive` override flag was supplied)

#### Scenario: User confirms batch deletion interactively (Happy Path)
- **Given** the purge CLI is executed in live execution mode without `--force`
- **When** the tool prompts for confirmation and the user inputs `"DELETE"`
- **Then** the system MUST proceed with the scheduled batch deletion sequence.

#### Scenario: User rejects or provides invalid confirmation input (Edge Case)
- **Given** the purge CLI prompts for confirmation before deleting 10 videos
- **When** the user inputs `"no"`, an empty string, or any string other than the required confirmation token
- **Then** the purge process MUST immediately abort execution
- **And** no video deletion API requests MUST be dispatched.

#### Scenario: Autonomous criteria-based pruning executes headlessly without terminal prompt (Happy Path)
- **Given** the daemon or CLI running in autonomous criteria-prune mode with live credentials
- **When** eligible underperforming videos meeting grace period and daily ceiling are scheduled for deletion
- **Then** the deletion MUST proceed without blocking on `sys.stdin` or `input()` prompts.
### Requirement: Paced Batch Deletion with Quota Safeguards
The batch deletion engine MUST enforce rate-limiting pacing intervals between consecutive delete requests and MUST gracefully handle API rate limit responses (HTTP 429 or quota exceeded).

#### Scenario: Paced batch deletion of multiple videos (Happy Path)
- **Given** a verified candidate list of 5 videos to delete
- **When** batch deletion executes
- **Then** each video deletion MUST be separated by a configurable delay interval ($\ge 0.5\text{s}$)
- **And** each deletion event MUST be logged with video ID and timestamp.

#### Scenario: API quota exhaustion during batch deletion (Edge Case)
- **Given** a batch deletion in progress on item 3 of 10
- **When** YouTube Data API returns a quota exceeded error or HTTP 429
- **Then** the purge engine MUST stop further deletion attempts
- **And** the engine MUST generate a failure report indicating 2 successes, 1 failure, and 7 skipped items.

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
### Requirement: Telegram Operational Audit Alert for Pruned Videos
Upon completing an automated pruning sweep, the engine MUST dispatch a structured operational alert to the Telegram notification bus documenting the target channel, total evaluated videos, count of pruned videos, and specific video IDs/titles/scores that were removed.

#### Scenario: Pruning action notifies Telegram channel (Happy Path)
- **Given** a completed pruning sweep that safely removed 1 underperforming video
- **When** post-prune notifications execute
- **Then** a Telegram message MUST be sent containing channel name, video title, ID, calculated score, and reason `"Low 24h Engagement"`.

### Requirement: Diagnostic Failure Classification and Pre-Purge Marking
Before deleting any video from YouTube, the system MUST diagnose the specific root cause of failure and mark the video in the local SQLite database.

1. **Failure Classification Codes**:
   - `ZERO_ENGAGEMENT_STALE`: Age $\ge 48\text{ hours}$, views $< 50$, likes $= 0$.
   - `CROSS_CONTAMINATED_TITLE`: Title contains thematic cues of another lane or channel (e.g. "Soy el malo" in a horror lane video).
   - `EMPTY_TITLE_ARTIFACT`: Title is "video", "test", or empty string.
   - `UNDERPERFORMING_SCORE`: Empirical success score $< 40.0$ after the 24h grace period.

2. **Pre-Purge Marking State Machine**:
   - When candidate videos are identified, the system MUST set `stories.status = 'MARKED_FOR_PURGE'` and record the failure reason in `stories.failure_code`.
   - The marked state MUST be visible in CLI inventory and diagnostic reports.
   - The system MUST allow inspecting the marked batch before dispatching YouTube Data API deletion.
   - Upon successful YouTube API deletion (`videos.delete`), the state MUST transition to `stories.status = 'PURGED'`.

#### Scenario: Stale video with zero views is diagnosed and marked for purge
- **Given** a video published 96 hours ago with 0 views and 0 likes
- **When** `mark_candidates_for_purge()` is executed
- **Then** the failure code MUST be determined as `ZERO_ENGAGEMENT_STALE`
- **And** `stories.status` MUST be updated to `'MARKED_FOR_PURGE'`
- **And** `stories.failure_code` MUST be updated to `'ZERO_ENGAGEMENT_STALE'`.

#### Scenario: Marked batch deletion via YouTube API
- **Given** a batch of videos with status `'MARKED_FOR_PURGE'`
- **When** `purge_marked_videos()` executes with YouTube Data API service
- **Then** each video MUST be deleted via `service.videos().delete(id=video_id).execute()`
- **And** the status MUST be updated to `'PURGED'`.

---
