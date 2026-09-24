# Specification: Channel Purge Control (Delta)

## MODIFIED Requirements

### Requirement: Automated Underperforming Video Pruning with Elevated Thresholds
The pruning engine MUST evaluate candidates for automated deletion using elevated performance thresholds and strict multi-tier safety checks:
1. **Mandatory Grace Period**: Only videos with upload age $\ge 24\text{ hours}$ SHALL be eligible for underperformance evaluation; videos younger than 24 hours MUST NOT be deleted.
2. **Elevated Threshold Violation**: A video SHALL qualify for underperforming candidate status if its computed empirical success score is strictly below the elevated survival floor (`actual_success_score < 40.0`).
3. **Daily Deletion Ceiling**: Autonomous sweeps MUST NOT delete more than 2 videos per canonical channel per 24 hours, unless explicit batch purge mode is invoked.
4. **Kill Switch**: If `AUTO_PRUNE_ENABLED=false` or `--disable-prune` is set, all automated deletions MUST be halted immediately.

#### Scenario: Video with score between 25.0 and 39.9 is now classified for purge
- **Given** a published video uploaded 72 hours ago with an empirical score of 32.0
- **When** the candidate evaluation executes with `min_score=40.0`
- **Then** the video MUST be recognized as a pruning candidate.

## NEW Requirements

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
