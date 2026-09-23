# Delta for Continuous Daemon Scheduler

## ADDED Requirements

### Requirement: Autonomous 24-Hour Analytics and Pruning Cadence Sweep
The continuous daemon scheduler MUST maintain a persistent record of the last analytics and pruning sweep timestamp (`last_sweep_at`) in `scheduler_state`. During each scheduling cycle, if the elapsed time since `last_sweep_at` is $\ge 24\text{ hours}$ ($86,400\text{ seconds}$), the scheduler MUST trigger an automated analytics synchronization, empirical success scoring, and underperforming video pruning sweep for all active channels.

The scheduler MUST isolate this maintenance sweep so that any transient network failure, YouTube Data API error, or quota limitation encountered during the sweep does NOT terminate, stall, or delay the primary video generation and rendering queues.

#### Scenario: Daemon executes 24-hour maintenance sweep automatically (Happy Path)
- **Given** the daemon running with a last sweep timestamp recorded 25 hours ago
- **When** the daemon scheduling iteration checks periodic tasks
- **Then** the scheduler MUST dispatch the 24-hour analytics sync and pruning workflow
- **And** upon completion, the scheduler MUST update `last_sweep_at` in `scheduler_state` to the current timestamp
- **And** the daemon MUST continue normal queue processing.

#### Scenario: YouTube Data API failure during sweep does not crash daemon loop (Edge Case)
- **Given** the 24-hour sweep is triggered during an upstream YouTube API outage (HTTP 503 or quota exceeded)
- **When** the sweep catches the API exception
- **Then** the sweep MUST log a warning and exit gracefully without raising an unhandled exception
- **And** the daemon loop MUST remain active and proceed to process rendering jobs normally.
