# Specification: Asset Rejection Analytics

## Capability Overview
The `asset-rejection-analytics` capability aggregates and categorizes asset and video rejections across both automated pre-publish QA verification gates (`src/verification/technical_qa.py`, `src/agents/video_qa.py`) and human review decisions via Telegram (`review_jobs.status = 'REJECTED'`). It classifies defects into standardized categories (`visual`, `audio`, `sync`, `luminance`, `pacing`, `editorial`), associates defect occurrences with specific asset and story identifiers, and provides aggregated tallies for operational monitoring.

## Requirements

### Requirement 1: Structured Asset Rejection Emission Across Automated QA Gates
The automated technical and visual QA verification modules MUST emit structured rejection events to `system_events` whenever an asset or composed video fails validation thresholds.

1. In `src/verification/technical_qa.py`:
   - When black frame detection exceeds threshold, audio clipping occurs, or A/V sync drift $> 100\text{ ms}$ is detected:
     - The verification routine MUST record an event in `system_events` with `event_type = 'asset_rejection'` and `level = 'WARNING'`.
     - The event MUST include `channel`, `story_id`, `run_id`, `stage = 'stage_10_verify'`, and `details_json` with defect category, measured metric value, and allowed threshold.
2. In `src/agents/video_qa.py`:
   - When luminance, contrast, or scene diversity analysis triggers a rejection:
     - The agent MUST record an `asset_rejection` event detailing the offending scene index, shot index, and defect class.

#### Scenario: Video fails automated A/V sync QA check
- **Given** a composed MP4 video where audio/video sync drift is measured at $145\text{ ms}$ (threshold $\le 100\text{ ms}$)
- **When** `technical_qa` validates the stream
- **Then** validation MUST fail
- **And** an `asset_rejection` event MUST be emitted to `system_events` with category `'sync'`
- **And** `details_json` MUST specify `measured_ms: 145` and `threshold_ms: 100`.

#### Scenario: Image asset fails luminance contrast gate
- **Given** an AI-generated still image with average luminance $< 12.0$ (black frame / extreme under-exposure)
- **When** `video_qa` inspects the asset
- **Then** the asset MUST be rejected
- **And** an `asset_rejection` event MUST be emitted with category `'luminance'`.

---

### Requirement 2: Human Telegram Review Rejection Tracking
The queue repository and review lifecycle handlers in `src/orchestrator/` MUST track and categorize human operator rejections submitted via Telegram review jobs.

1. When an operator clicks `REJECT` on a pending Telegram review item:
   - The job status in `review_jobs` MUST update to `status = 'REJECTED'`.
   - The handler MUST record a `review_rejection` or `asset_rejection` event into `system_events` with `category = 'editorial'` (or custom defect reason if provided).
   - The event payload MUST reference `job_id`, `version`, `channel`, and `reviewed_at`.
2. The tube collector MUST aggregate review rejection rates against total submissions over selectable time windows.

#### Scenario: Human reviewer rejects candidate video via Telegram
- **Given** a pending review job `job-404` for channel `drama`
- **When** the human reviewer presses the `REJECT` button with note `"Audio pacing too fast"`
- **Then** `review_jobs` row for `job-404` MUST transition to `status = 'REJECTED'`
- **And** an event MUST be recorded in `system_events` capturing the rejection timestamp and channel.

---

### Requirement 3: Defect Categorization and Asset Identifier Tracking
Every rejection event MUST map to one of six standardized defect categories and reference the specific asset or story identifier.

1. The system MUST classify rejections into the following categories:
   - `visual`: Image distortion, rendering artifacts, glitching, resolution mismatch.
   - `audio`: Audio clipping, narration distortions, volume normalization failure.
   - `sync`: Subtitle timing drift, audio-to-video offset $> 100\text{ ms}$.
   - `luminance`: Over-exposure, under-exposure, black frames.
   - `pacing`: Shot duration violations, rushed/stalled act pacing.
   - `editorial`: Human reviewer rejection for tone, story hook, or content policy.
2. The event payload MUST specify `asset_id` (e.g. catalog loop path, generated image path, or story ID).

#### Scenario: Rejection event defect categorization mapping
- **Given** a QA rejection caused by audio peak clipping ($> 0\text{ dBFS}$)
- **When** the event is constructed
- **Then** the category MUST strictly evaluate to `'audio'`
- **And** `asset_id` MUST identify the offending audio stream.

---

### Requirement 4: Rejection Analytics Aggregation and Dashboard Queries
The repository in `src/core/repository/queue.py` MUST provide `query_asset_rejection_counts()` to compute rejection breakdowns.

1. `query_asset_rejection_counts(window_hours=24, channel=None)` MUST calculate:
   - Total automated QA rejections.
   - Total human review rejections.
   - Rejection counts broken down by category (`visual`, `audio`, `sync`, `luminance`, `pacing`, `editorial`).
   - Top recurring offending assets or templates.
2. The aggregated rejection tallies MUST be incorporated into the `TubeSnapshot` for display in `python main.py tube` and MCP resources.

#### Scenario: Aggregating QA and review rejections over 24 hours
- **Given** 2 visual rejections, 1 sync rejection, and 1 human editorial rejection recorded in the last 24 hours
- **When** `query_asset_rejection_counts(window_hours=24)` is called
- **Then** total rejections MUST equal 4
- **And** `category_breakdown` MUST reflect `{"visual": 2, "sync": 1, "editorial": 1}`.
