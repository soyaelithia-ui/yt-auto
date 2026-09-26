# Specification: YouTube Quota and Draft Publication Tracking

## Capability Overview
The `youtube-quota-and-draft-tracking` capability monitors consumption of the YouTube Data API v3 daily 10,000 quota units, handles channel upload capacity saturation, tracks staged publications across draft/unlisted privacy tiers, enforces custom thumbnail verification, and prevents duplicate uploads when API responses are ambiguous (`UPLOAD_UNCONFIRMED`).

## Requirements

### Requirement 1: YouTube 10,000 Daily API Quota Burn and Upload Limit Tracking
The YouTube publishing pipeline in `src/pipeline/stages/stage_13_publish.py` and `src/youtube/uploader/` MUST track estimated YouTube Data API v3 quota consumption against the daily budget of 10,000 units.

1. Each video upload operation MUST account for approximately 1,600 quota units consumed.
2. Each custom thumbnail upload operation MUST account for 50 quota units consumed.
3. Each metadata update or playlist insertion MUST account for 50 quota units consumed.
4. Quota burn estimations SHALL reset at 00:00 PST (08:00 UTC) matching YouTube's daily API quota cycle.
5. The system MUST monitor daily upload counts per channel against the channel's daily upload limit (typically 5–10 videos per rolling 24 hours depending on channel verification status).

#### Scenario: Tracking YouTube quota burn across daily uploads (Happy Path)
- **Given** 4 successful uploads executed on channel `horror` within the current quota cycle
- **When** YouTube quota telemetry is evaluated
- **Then** estimated daily quota consumption MUST equal approximately $4 \times 1650 = 6,600\text{ units}$
- **And** remaining quota headroom MUST reflect approximately $3,400\text{ units}$ remaining
- **And** estimated remaining uploads MUST be reported as $2$.

---

### Requirement 2: Automatic State Transition to WAITING_YOUTUBE_LIMIT
When YouTube returns an API quota exhaustion or upload limit exceeded error, the pipeline MUST catch the exception, emit a telemetry event, and transition the active job to `JobStatus.WAITING_YOUTUBE_LIMIT`.

1. Upon intercepting `YouTubeQuotaExceededError` (HTTP 403 `quotaExceeded`), the publisher MUST:
   - Emit a `youtube_quota_limit` event with details (`reason: "quota_exceeded"`) into `system_events`.
   - Update story job status to `JobStatus.WAITING_YOUTUBE_LIMIT`.
   - Set `next_attempt_at` to the next 08:00 UTC quota reset timestamp.
   - Release any active concurrency leases.
2. Upon intercepting `YouTubeUploadLimitError` (HTTP 400/403 `uploadLimitExceeded`), the publisher MUST:
   - Emit a `youtube_quota_limit` event with details (`reason: "upload_limit_exceeded"`) into `system_events`.
   - Update story job status to `JobStatus.WAITING_YOUTUBE_LIMIT`.
   - Set `next_attempt_at` to a minimum backoff delay of 12 hours.
   - Release active concurrency leases.

#### Scenario: Catching quotaExceeded error and transitioning to WAITING_YOUTUBE_LIMIT
- **Given** a story in stage 13 attempting to publish to YouTube
- **When** YouTube API raises `YouTubeQuotaExceededError`
- **Then** the publisher MUST update the story status to `JobStatus.WAITING_YOUTUBE_LIMIT`
- **And** an event of type `youtube_quota_limit` MUST be inserted into `system_events`
- **And** `next_attempt_at` MUST be scheduled for the next 08:00 UTC cycle
- **And** the worker lease MUST be released cleanly.

---

### Requirement 3: Draft and Unlisted Staging Telemetry
The telemetry hub MUST monitor and report staged video publication states (`draft`, `unlisted`, `public`) in `stories` and `publications`.

1. When a video is staged in draft or unlisted status prior to human review or scheduled rollout:
   - The publication record MUST store `privacy_status = 'draft'` or `privacy_status = 'unlisted'`.
   - The telemetry snapshot MUST aggregate staged draft counts per channel.
2. The tube collector MUST track unreviewed draft accumulation, flagging any channel with $> 5$ unpromoted drafts as `DRAFT_BACKLOG_WARNING`.

#### Scenario: Aggregating draft and unlisted staging counts
- **Given** 3 unlisted videos and 2 draft videos staged for channel `drama`
- **When** the tube collector queries publication telemetry
- **Then** `staged_drafts` for channel `drama` MUST equal 5
- **And** privacy distribution MUST report `{"unlisted": 3, "draft": 2}`.

---

### Requirement 4: Custom Thumbnail Confirmation and Ambiguous Upload Safeguard (UPLOAD_UNCONFIRMED)
The publishing stage MUST verify successful application of custom thumbnails and guard against duplicate uploads when API responses timeout or fail ambiguously.

1. **Custom Thumbnail Verification**:
   - Following video upload, the publisher MUST upload the custom thumbnail image.
   - The publisher MUST verify that the API returns HTTP 200 or confirmation before marking publication complete.
   - If thumbnail upload fails, the publication MUST log a warning and record `thumbnail_confirmed = 0`.
2. **Ambiguous Upload Handling (`UPLOAD_UNCONFIRMED`)**:
   - If an upload request times out or disconnects after binary bytes were transmitted but before an explicit video ID response was received:
     - The publisher MUST NOT blindly retry uploading the video immediately.
     - The publisher MUST set story status to `JobStatus.UPLOAD_UNCONFIRMED`.
     - The publisher MUST record `upload_unconfirmed` in `system_events` with video title, SHA-256 hash, and timestamp.
     - A preflight verification check MUST query channel recent uploads by title or video hash before retrying to confirm whether YouTube actually registered the video.

#### Scenario: Network drop during video upload triggers UPLOAD_UNCONFIRMED
- **Given** a video file being transmitted to YouTube whose network connection drops at 99% progress
- **When** the uploader catches a connection reset without an API confirmation payload
- **Then** the story MUST NOT be marked `RETRYABLE_FAILED` for immediate retry
- **And** the story status MUST be updated to `JobStatus.UPLOAD_UNCONFIRMED`
- **And** an `upload_unconfirmed` event MUST be emitted into `system_events`.

#### Scenario: Custom thumbnail confirmation verified successfully
- **Given** a completed video upload with video ID `abc123xyz`
- **When** the custom thumbnail is transmitted to YouTube Studio API and returns HTTP 200
- **Then** the publication record MUST have `thumbnail_confirmed = 1`
- **And** publication status MUST transition to `PUBLISHED`.
