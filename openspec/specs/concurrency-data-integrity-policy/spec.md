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

## Requirement: Defensive Database Path Validation & Mock Sanitization
All database connection and initialization entry points in `src/core/repository.py` and `review/db.py` (`connect()`, `init_review_db()`, `get_db_connection()`, and `ReviewStateStore`) MUST strictly validate the `db_path` argument before performing any filesystem operations (such as directory creation or SQLite file opening). Valid inputs are valid path instances or `":memory:"`. Mock objects (`unittest.mock.Base` / `MagicMock`) MUST be rejected immediately with `TypeError`, and stringified mock representations (`<MagicMock...>`, `<Mock...>`) MUST be rejected with `ValueError`, ensuring zero untracked mock database artifacts on disk.

### Scenario: Rejection of Mock Objects in Database Entry Points
- **Given** a `unittest.mock.MagicMock` or stringified mock representation passed as `db_path`
- **When** `connect()`, `init_review_db()`, `get_db_connection()`, or `ReviewStateStore()` is invoked
- **Then** a `TypeError` (for mock objects) or `ValueError` (for mock string representations) MUST be raised immediately
- **And** NO database files or parent directories MUST be created on disk.

## Requirement: ChannelLock Isolation & Environment Configurability
The process locking mechanism in `src/core/lock.py` MUST support deterministic isolation across independent test runs, multi-process workers, and parallel test runners (e.g., `pytest -n`). `ChannelLock` and `acquire_lock` MUST accept configurable `lock_dir` and `lock_file_path` parameters and respect `YT_LOCK_DIR` and `LOCK_FILE_PATH` environment variables, defaulting to `scratch/youtube_automation.lock` when unconfigured.

### Scenario: Isolated ChannelLock Execution
- **Given** an isolated temporary directory `tmp_path` passed via `lock_dir` or `YT_LOCK_DIR`
- **When** `ChannelLock(channel_name="moku")` is acquired and released
- **Then** the lock file MUST be created exclusively inside the isolated directory
- **And** lock release MUST close descriptors and remove the lock file cleanly upon context exit.

