# Delta for Channel Purge Control

## ADDED Requirements

### Requirement: Automated Underperforming Video Pruning with Mandatory Grace Period
The pruning engine MUST evaluate candidates for automated deletion using strict multi-tier safety checks:
1. **Mandatory Grace Period**: Only videos with upload age $\ge 24\text{ hours}$ ($\ge 86,400\text{s}$) SHALL be eligible for underperformance evaluation; videos younger than 24 hours MUST NOT be deleted.
2. **Threshold Violation**: A video SHALL qualify for pruning only if its computed empirical success score is strictly below the survival threshold (`actual_success_score < 25.0`) AND its total view count is below the threshold floor (`views < 50`).
3. **Bounded Deletion Ceiling**: The engine MUST NOT delete more than 2 videos per canonical channel within any rolling 24-hour window, regardless of how many videos meet the threshold violation.
4. **Kill Switch**: If the environment flag `AUTO_PRUNE_ENABLED=false` or CLI flag `--disable-prune` is set, all automated deletions MUST be halted immediately.

#### Scenario: Underperforming video older than 24h is pruned safely (Happy Path)
- **Given** a video uploaded 48 hours ago with 12 views, 0 likes, and an empirical score of 8.5
- **And** fewer than 2 videos have been pruned for the target channel in the last 24 hours
- **And** `AUTO_PRUNE_ENABLED` is true
- **When** the automated pruning sweep executes
- **Then** the video MUST be deleted via YouTube Data API `videos().delete()`
- **And** the record in SQLite `publications` and `stories` MUST be marked with status `"PURGED_UNDERPERFORMING"`
- **And** the daily channel prune counter MUST be incremented by 1.

#### Scenario: Video younger than 24 hours is protected by grace period (Edge Case)
- **Given** a video uploaded 6 hours ago with 4 views, 0 likes, and an empirical score of 5.0
- **When** the automated pruning sweep executes
- **Then** the video MUST be skipped and preserved intact
- **And** zero deletion requests MUST be sent to YouTube Data API.

#### Scenario: Daily deletion ceiling limits maximum deletions to 2 per day (Edge Case)
- **Given** 5 videos all uploaded 3 days ago with 0 views and 0 score
- **When** the pruning sweep evaluates the channel
- **Then** at most 2 videos (the lowest scoring) MUST be deleted
- **And** the remaining 3 videos MUST be skipped until the next rolling 24-hour cycle.

#### Scenario: Kill switch halts all automated deletions (Edge Case)
- **Given** 2 candidate videos eligible for deletion under score and age rules
- **And** `AUTO_PRUNE_ENABLED` is set to `"false"`
- **When** the pruning sweep runs
- **Then** the pruner MUST log an operational notice and abort deletions without modifying YouTube or database state.

### Requirement: Telegram Operational Audit Alert for Pruned Videos
Upon completing an automated pruning sweep, the engine MUST dispatch a structured operational alert to the Telegram notification bus documenting the target channel, total evaluated videos, count of pruned videos, and specific video IDs/titles/scores that were removed.

#### Scenario: Pruning action notifies Telegram channel (Happy Path)
- **Given** a completed pruning sweep that safely removed 1 underperforming video
- **When** post-prune notifications execute
- **Then** a Telegram message MUST be sent containing channel name, video title, ID, calculated score, and reason `"Low 24h Engagement"`.

---

## RENAMED Requirements

### Requirement: Interactive Confirmation Safeguard → Interactive Confirmation Safeguard and Autonomous Prune Override
(Reason: Extended capability to support autonomous criteria-based pruning)

## MODIFIED Requirements

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
