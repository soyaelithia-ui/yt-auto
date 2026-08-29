# Specification: Channel Purge Control

## Capability Overview
The `channel-purge-control` capability provides interactive and programmatic mechanisms to inspect, audit, and safely delete YouTube video catalogs associated with managed channels while preventing unauthorized cross-channel deletion and API quota exhaustion.

## Requirements

### Requirement 1: Dry-Run Catalog Inspection
The purge control tool MUST perform a non-destructive dry-run inspection by default or when `--dry-run` is explicitly provided, retrieving all video metadata without issuing mutation or deletion requests.

#### Scenario: Successful dry-run inspection of channel catalog (Happy Path)
- **Given** a target channel identifier `"moku"` containing 15 uploaded videos
- **When** the purge CLI is executed with `--dry-run`
- **Then** the system MUST retrieve and display the list of 15 candidate videos with titles and IDs
- **And** the system MUST NOT call the YouTube Data API `videos().delete()` endpoint
- **And** the return summary report MUST record 0 deleted videos and 15 candidate videos.

#### Scenario: Dry-run inspection on empty channel catalog (Edge Case)
- **Given** a target channel identifier with 0 uploaded videos
- **When** the purge inspection is executed in dry-run mode
- **Then** the system MUST return an empty candidate list with exit code 0
- **And** the summary report MUST indicate 0 candidate items without error.

### Requirement 2: Interactive Confirmation Safeguard
The purge control tool MUST require explicit affirmative user confirmation before initiating non-dry-run video deletions, unless an explicit `--force` or `--non-interactive` override flag is supplied.

#### Scenario: User confirms batch deletion interactively (Happy Path)
- **Given** the purge CLI is executed in live execution mode without `--force`
- **When** the tool prompts for confirmation and the user inputs `"DELETE"`
- **Then** the system MUST proceed with the scheduled batch deletion sequence.

#### Scenario: User rejects or provides invalid confirmation input (Edge Case)
- **Given** the purge CLI prompts for confirmation before deleting 10 videos
- **When** the user inputs `"no"`, an empty string, or any string other than the required confirmation token
- **Then** the purge process MUST immediately abort execution
- **And** no video deletion API requests MUST be dispatched.

### Requirement 3: Paced Batch Deletion with Quota Safeguards
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

### Requirement 4: Channel Ownership Validation and Failure Reporting
The purge control tool MUST verify that each candidate video ID belongs to the expected canonical channel ID before issuing deletion requests, recording per-video outcomes in a structured report.

#### Scenario: Video ownership verification matches canonical channel (Happy Path)
- **Given** candidate video `"vid_123"` belonging to expected channel ID `"UC_MOKU_01"`
- **When** deletion is processed
- **Then** the video is verified and deleted successfully, logged in the output report.

#### Scenario: Candidate video belongs to an unexpected channel ID (Edge Case)
- **Given** candidate video `"vid_999"` whose snippet channel ID does not match the configured expected channel ID
- **When** ownership validation is evaluated
- **Then** the system MUST reject deletion with `PermissionError`
- **And** the batch report MUST log the video as skipped/rejected without affecting remaining items.
