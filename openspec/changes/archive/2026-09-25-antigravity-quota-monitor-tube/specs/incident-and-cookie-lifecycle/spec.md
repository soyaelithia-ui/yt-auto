# Specification: Incident and Cookie Lifecycle Telemetry

## Capability Overview
The `incident-and-cookie-lifecycle` capability aggregates operational incidents across the pipeline lifecycle, covering pipeline stage execution failures (Stages 1–13), worker crash diagnostics with stack traces, orphaned concurrency lease recoveries, and proactive browser cookie session decay (`cookie_failure` and `cookie_warning`) with stateful 1-hour deduplication.

## Requirements

### Requirement 1: Pipeline Stage Error Aggregation and Worker Crash Diagnostics
The telemetry system MUST capture and index all pipeline stage failures and worker process crashes across Stages 1 through 13.

1. When any stage in the media pipeline encounters an unhandled exception or retryable error:
   - The stage handler MUST format the diagnostic payload using `format_error_diagnostics(exc)`.
   - The stage handler MUST record a structured record in `system_events` with `level = 'ERROR'` or `level = 'CRITICAL'`, containing `stage`, `error_code`, `channel`, `run_id`, `story_id`, and `details_json` with traceback and context.
2. Worker crash diagnostics MUST capture the process exit code, signal (e.g. `SIGTERM`, `SIGKILL`), and last executed stage.
3. The tube collector MUST aggregate stage failure counts broken down by stage number and channel over selectable observation windows (e.g., 24 hours).

#### Scenario: Capturing stage failure diagnostics with structured details (Error State)
- **Given** Stage 8 (render) fails during FFmpeg stream-copy concatenation due to a missing asset file
- **When** the stage exception handler catches the error
- **Then** `format_error_diagnostics()` MUST be invoked to construct diagnostic context
- **And** an event MUST be inserted into `system_events` with `stage = 'stage_8_render'`, `level = 'ERROR'`, and `error_code = 'FFMPEG_CONCAT_ERROR'`
- **And** `details_json` MUST contain the offending file path and error trace.

---

### Requirement 2: Orphaned and Expired Concurrency Lease Reclamation Tracking
The lease management subsystem in `src/core/repository/leases.py` MUST emit structured lifecycle telemetry events when orphaned or expired leases are recovered.

1. When `recover_expired_leases()` identifies an expired worker lease in `leases` or `lane_leases` where `expires_at < current_epoch`:
   - The routine MUST delete or reassign the expired lock atomically.
   - The routine MUST emit an event of type `lease_recovered` into `system_events`.
   - The `lease_recovered` event MUST specify `channel`, `lane_id`, expired `owner`, expired `run_id`, and `heartbeat_at`.
2. The tube collector MUST track total lease reclamation frequency to highlight worker crash loops or hung subprocesses.

#### Scenario: Automated reclamation of dead worker lease
- **Given** a lane lease in `lane_leases` held by `worker-pid-401` whose expiration expired $90\text{ seconds}$ ago
- **When** `recover_expired_leases()` executes
- **Then** the lease record MUST be removed from `lane_leases`
- **And** a `system_events` record with `event_type = 'lease_recovered'` MUST be written
- **And** the event details MUST record `worker-pid-401` and the affected lane.

---

### Requirement 3: Proactive Cookie Health Lifecycle and Deduplicated Incident Emission
The cookie management layer (`src/core/cookies.py`), API health checker (`src/api_health.py`), and session uploader (`src/youtube/session_uploader.py`) MUST emit structured incident events upon cookie invalidation or decay, enforced with a stateful 1-hour deduplication window per channel.

1. **Failure Events (`cookie_failure`)**:
   - When cookie validation yields `SessionStatus.EXPIRED`, `SessionStatus.INCOMPLETE`, or `SessionStatus.INVALID`:
     - An event of type `cookie_failure` MUST be emitted into `system_events` with `level = 'ERROR'`.
     - The event payload MUST specify `channel`, status, missing tokens, and days/hours expired.
2. **Warning Events (`cookie_warning`)**:
   - When cookie validation yields `SessionStatus.EXPIRING_SOON` (remaining lifespan $< 48\text{ hours}$):
     - An event of type `cookie_warning` MUST be emitted into `system_events` with `level = 'WARNING'`.
     - The event payload MUST specify `channel`, `hours_left`, and expiration timestamp.
3. **1-Hour Stateful Deduplication Window**:
   - Repeated health checks or worker runs within $3,600\text{ seconds}$ (1 hour) for the same channel with the same status SHALL NOT insert redundant duplicate rows into `system_events`.
   - If the channel cookie status changes (e.g. from `EXPIRING_SOON` to `EXPIRED`, or from `EXPIRED` to `HEALTHY`), the deduplication filter MUST allow immediate emission.

#### Scenario: Cookie approaching expiration emits single warning within 1 hour
- **Given** channel `horror` cookies expire in 36 hours (`SessionStatus.EXPIRING_SOON`)
- **When** `check_cookies("horror")` is called at $T = 0$
- **Then** a `cookie_warning` event MUST be emitted to `system_events`
- **When** `check_cookies("horror")` is called again at $T = 10\text{ minutes}$ with the same status
- **Then** no duplicate `cookie_warning` row SHALL be inserted into `system_events`.

#### Scenario: Cookie status degradation immediately bypasses deduplication
- **Given** channel `horror` previously emitted a `cookie_warning` at $T = 0$
- **When** at $T = 15\text{ minutes}$ the cookie file is corrupted, causing `SessionStatus.INVALID`
- **Then** a `cookie_failure` event MUST be emitted immediately to `system_events` despite the 1-hour window.

---

### Requirement 4: Operational Incident Querying and Aggregation
The repository in `src/core/repository/queue.py` MUST provide `query_tube_incidents()` to retrieve and aggregate operational incidents.

1. `query_tube_incidents(window_hours=24, event_types=None, limit=50)` MUST query `system_events` filtering by timestamp and optional event types (`cookie_failure`, `cookie_warning`, `lease_recovered`, `audio_prompt_leak`, `quota_saturation`, `stage_error`).
2. The query MUST order incidents chronologically descending (`ts DESC`) and return structured incident objects.
3. Telemetry collector snapshots MUST compile an incident timeline and summary counts for CLI and MCP presentation.

#### Scenario: Querying incidents for a 24-hour observation window
- **Given** 3 `cookie_warning` events and 1 `lease_recovered` event logged over the last 6 hours
- **When** `query_tube_incidents(window_hours=24)` is called
- **Then** 4 incident records MUST be returned
- **And** the newest incident MUST be the first item in the returned list.
