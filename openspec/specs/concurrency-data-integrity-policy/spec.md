# Spec: Concurrency and Data Integrity Policy

## Requirement: Two-Phase Commit Dual-Database Consistency
State transitions from review approval to YouTube publication MUST execute through `DBReconciler` coordinating `shorts_queue.db` and `review_state.db` under `BEGIN IMMEDIATE` locks. Publication updates MUST be strictly idempotent: subsequent triggers with identical `run_id` and `video_id` MUST return `ALREADY_PUBLISHED` without duplicate writes or multiple YouTube uploads.

### Scenario: Atomic Approval and Publication
- **Given** an approved video job with `job_id` and `run_id`
- **When** `DBReconciler.reconcile_publication(job_id, run_id, video_id)` executes
- **Then** `review_jobs` MUST transition to `PUBLISHED` with `published_id`
- **And** `stories` and `runs` in `shorts_queue.db` MUST atomically transition to `PUBLISHED`
- **And** active leases for `job_id` and `run_id` MUST be cleared immediately.

## Requirement: Proactive Lease Reaping for Dead Worker PIDs
The system MUST run an active `LeaseReaper` monitoring process identifiers (PIDs) associated with active lane leases. When a worker process crashes (OOM/SIGKILL/exit), the reaper MUST detect process death via `os.kill(pid, 0)` within 35 seconds and release the lane lease without waiting for the 900-second TTL expiration.

### Scenario: Crashed Worker Lease Cleanup
- **Given** an active lane lease held by a dead process PID
- **When** `LeaseReaper.reap_once()` executes
- **Then** the lease row MUST be deleted immediately
- **And** the affected story MUST transition to `RETRYABLE_FAILED` with error `Worker PID crashed (reaped)`.

## Requirement: SQLite WAL Mode and Non-Blocking Reads
All SQLite database instances (`shorts_queue.db`, `review_state.db`) MUST operate in Write-Ahead Logging (`PRAGMA journal_mode=WAL;`) with `busy_timeout=30000`. Writers MUST acquire immediate exclusive locks while concurrent readers operate with zero latency without blocking writer threads.

### Scenario: Concurrent Multi-Lane Reads
- **Given** multiple worker threads querying catalog loops and story queues
- **When** an active worker commits a run checkpoint under `BEGIN IMMEDIATE`
- **Then** reader threads MUST query unhindered without encountering `database is locked` errors.
