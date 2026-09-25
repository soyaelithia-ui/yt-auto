# Specification: Autonomous Daemon Lane Scheduler

## Capability Overview
The `autonomous-daemon-lane-scheduler` capability manages the autonomous, continuous 24/7 multi-lane production lifecycle for YouTube channels (`horror`, `drama`, `scifi`). It orchestrates concurrent production lanes across multiple visual paradigms, enforcing strict cadence ceilings (`min_gap_seconds`) without catch-up bursts, dynamic overdue lane prioritization, atomic SQLite WAL lane leasing (`lane_leases`), non-blocking responsive futures collection, periodic Telegram human-in-the-loop (HITL) review sweeps, graceful process lifecycle termination, and automatic child zombie process reaping.

Multi-lane execution strictly complies with Section 5 of `AGENTS.md` and invariant `REG-14`, operating under the hard target operational ceiling of **≤ 2 CPU Cores** (≤ 200%) and **≤ 2.0 GiB RAM** (2,048 MiB peak RSS).

---

## Requirements

### Requirement: Cadence Compliance and Zero Catch-Up Bursts
The multi-lane daemon scheduler MUST enforce pure forward monotonic cadence progression based on the configured per-lane interval (`cadence_min_gap_seconds`). Upon a productive fire resulting in a terminal or actionable generation status (`PUBLISHED`, `COMPLETED`, `PENDING_REVIEW`, `RENDERED`, `UPLOAD_UNCONFIRMED`, `WAITING_YOUTUBE_LIMIT`), the scheduler MUST set the lane's next scheduled time to:

$$\text{next\_due\_at} = \text{fired\_at} + \text{lane.cadence\_min\_gap\_seconds}$$

Following daemon restarts, prolonged downtime, or operational pauses, the scheduler MUST NEVER execute catch-up bursts or backfill missed execution intervals; all missed cadence windows MUST be discarded, and scheduling MUST advance forward strictly from the current tick timestamp.

When a scheduled lane has no claimable stories in the queue (`LANE_EMPTY`), the scheduler MUST NOT advance the full cadence ceiling. Instead, the scheduler MUST apply an adaptive linear backoff ramp:

$$\text{backoff}(k) = \min(120, 60 + 30 \times \max(0, k - 1))$$

where $k$ is the count of consecutive empty evaluations (`consecutive_empty`). The lane's `next_due_at` MUST be scheduled for $\text{fired\_at} + \text{backoff}(k)$, allowing newly ingested stories to be processed promptly once available without busy-waiting.

#### Scenario: Normal cadence advancement on productive fire (Happy Path)
- **Given** lane `horror-scp-shorts` with `cadence_min_gap_seconds = 300` and current time $T = 1000$
- **When** the lane executes a pipeline turn and finishes with status `PUBLISHED`
- **Then** `commit_fire` MUST record `fired_at = 1000` and `next_due_at = 1300` in the database
- **And** the lane MUST NOT be eligible for selection until $T \ge 1300$.

#### Scenario: Zero catch-up burst after prolonged daemon downtime (Edge Case)
- **Given** the daemon has been offline for 14,400 seconds (4 hours) for lane `horror-scp-shorts` ($min\_gap = 300\text{s}$)
- **When** the daemon starts up and executes the first due turn at $T = 15000$
- **Then** the scheduler MUST execute exactly one turn for this lane
- **And** `commit_fire` MUST advance `next_due_at` to $15000 + 300 = 15300$
- **And** the scheduler MUST NOT execute the 48 unexecuted turns that lapsed during downtime.

#### Scenario: Empty lane adaptive backoff without cadence advance (Happy Path)
- **Given** lane `drama-drama-shorts` is due at $T = 2000$ but the repository contains no pending stories for the lane
- **When** `_execute_lane_pick` executes and returns status `LANE_EMPTY`
- **Then** `commit_empty` MUST increment `consecutive_empty` to 1
- **And** `next_due_at` MUST be set to $2000 + 60 = 2060$
- **And** the full cadence ceiling of 300 seconds MUST NOT be applied.

#### Scenario: Consecutive empty backoff caps at maximum threshold (Edge Case)
- **Given** lane `drama-drama-shorts` has recorded 4 consecutive empty executions ($k = 4$) at $T = 3000$
- **When** another empty pick occurs
- **Then** the calculated backoff delay MUST be $\min(120, 60 + 30 \times 3) = 120\text{ seconds}$
- **And** `next_due_at` MUST be set to $3000 + 120 = 3120$.

---

### Requirement: Dynamic Due Lane Selection and Priority Sorting
The scheduler MUST dynamically evaluate all registered lanes on every daemon tick and select up to `max_picks` candidate lanes. Candidates MUST be sorted by overdue margin in descending order:

$$\text{overdue\_margin} = \text{current\_timestamp} - \text{next\_due\_at}$$

such that the most-overdue eligible lane is given top priority for dispatch.

Candidate selection MUST enforce the following operational filters:
1. **Lane Enabled Status**: The lane MUST have `enabled = True` in its configuration.
2. **Channel Administrative Pause**: The lane's channel MUST NOT be marked as `paused = 1` in `channel_controls`.
3. **Active Lane Lease Absence**: There MUST NOT be an active, unexpired lease in `lane_leases` (`expires_at > current_timestamp`) for the `lane_id`.
4. **Lane Filter Inclusion**: If `lanes_filter` is supplied, the `lane_id` MUST be present in the filter set.
5. **Running Exclusions**: If `exclude_lanes` is supplied (representing lanes currently executing in worker threads), the lane MUST NOT be in the exclusion set.

#### Scenario: Most-overdue lane prioritized during selection (Happy Path)
- **Given** lane A with `next_due_at = 1000` (overdue margin = 200s at $T = 1200$)
- **And** lane B with `next_due_at = 1100` (overdue margin = 100s at $T = 1200$)
- **When** `LaneScheduler.take_due_lanes(now=1200, max_picks=1)` is invoked
- **Then** lane A MUST be returned as the first pick in the list.

#### Scenario: Paused channel excluded from due lane dispatch (Edge Case)
- **Given** lane `horror-horror-long` is overdue at $T = 2000$
- **And** the `horror` channel has `paused = 1` in `channel_controls`
- **When** `LaneScheduler.take_due_lanes(now=2000)` executes
- **Then** `horror-horror-long` MUST NOT be included in the returned picks
- **And** unpaused channels MUST be evaluated without obstruction.

#### Scenario: Active unexpired lease prevents duplicate lane selection (Edge Case)
- **Given** lane `drama-aita-long` is overdue at $T = 2000$
- **And** an active worker holds an unexpired lease in `lane_leases` with `expires_at = 2500`
- **When** `LaneScheduler.take_due_lanes(now=2000)` executes
- **Then** `drama-aita-long` MUST be excluded from the returned picks.

#### Scenario: Lane filter restricts selection to requested subset (Happy Path)
- **Given** lanes `horror-scp-shorts` and `drama-drama-shorts` are both overdue
- **When** `take_due_lanes` is called with `lanes_filter={"horror-scp-shorts"}`
- **Then** only `horror-scp-shorts` MUST be returned
- **And** `drama-drama-shorts` MUST NOT be picked.

---

### Requirement: Atomic SQLite WAL Lane Leasing and Stale Lease Recovery
All lease acquisitions, renewals, and stale lease recoveries MUST operate within SQLite Write-Ahead Logging (WAL) mode using `BEGIN IMMEDIATE` transactions to prevent database write deadlocks and ensure strict mutual exclusion.

1. **Lease Registration**:
   When claiming a story for a lane, the repository MUST insert or update a record in `lane_leases` containing: `job_id`, `lane_id`, `channel`, `owner`, `run_id`, `acquired_at`, `heartbeat_at`, and `expires_at`.
2. **Worker Signature**:
   The `owner` signature MUST be constructed using the format:
   `lane-{lane_id}:{hostname}:{pid}` (or including worker thread ID), uniquely identifying the process holding the lease.
3. **Bounded Lease Duration**:
   Leases MUST specify an expiration duration bounded by:
   $$\text{lease\_seconds} = \max(900, \text{RENDER\_TIMEOUT\_SECONDS} // 2)$$
   guaranteeing that worker crashes or hangs do not permanently block lanes.
4. **Heartbeat Renewal**:
   Worker threads MUST periodically touch the lease heartbeat via `heartbeat_lane_lease` at stage boundaries, updating `heartbeat_at = current` and extending `expires_at = current + lease_seconds`.
5. **Stale Lease Recovery (`LeaseReaper`)**:
   `LeaseReaper.reap_once()` MUST execute at daemon startup and on every daemon tick. Expired leases (`expires_at <= current`) MUST be deleted from `lane_leases`, and the corresponding abandoned runs in `runs` and stories in `stories` MUST be transitioned to `RETRYABLE_FAILED` with error code `lease_expired`.

#### Scenario: Atomic lane lease acquisition on claimable story (Happy Path)
- **Given** a pending story in queue for lane `horror-scp-shorts`
- **When** `QueueRepository.claim_for_lane()` is invoked within a `BEGIN IMMEDIATE` transaction
- **Then** a lease MUST be inserted into `lane_leases` with the caller's unique `owner` signature
- **And** `expires_at` MUST be set to `now + lease_seconds`
- **And** a run record with status `PROCESSING` and matching `lane_id` MUST be created.

#### Scenario: Concurrent worker contention blocked by active lease (Edge Case)
- **Given** an active unexpired lease for lane `horror-scp-shorts` held by worker A
- **When** worker B attempts to call `claim_for_lane()` for `horror-scp-shorts`
- **Then** the repository MUST return `None`
- **And** worker B MUST NOT claim any story or overwrite worker A's lease.

#### Scenario: Heartbeat renewal extends lease expiration deadline (Happy Path)
- **Given** an active lease expiring at $T = 2000$ with `lease_seconds = 900`
- **When** the worker invokes `heartbeat_lane_lease` at $T = 1500$
- **Then** `heartbeat_at` MUST be updated to 1500
- **And** `expires_at` MUST be extended to $1500 + 900 = 2400$.

#### Scenario: Stale lease recovery reaps expired worker lease (Edge Case)
- **Given** a worker process crashed, leaving a lease in `lane_leases` with `expires_at = 1000` at current time $T = 1100$
- **When** `LeaseReaper.reap_once()` executes on the daemon tick
- **Then** the expired lease row MUST be deleted from `lane_leases`
- **And** the associated run in `runs` MUST be updated to `RETRYABLE_FAILED` with error code `lease_expired`
- **And** the story in `stories` MUST be reset to `RETRYABLE_FAILED` for subsequent reclamation.

---

### Requirement: Non-blocking Responsive Turn Futures Collection and Periodic Sweeps
The multi-lane daemon orchestrator MUST manage asynchronous worker threads via `_await_future_responsive` (single turn) and `_collect_futures_responsive` (batch of lane turns), avoiding unbounded blocking calls (`future.result()` without timeout) that could freeze the daemon lifecycle during hung subprocesses.

1. **Responsive Future Draining**:
   Futures MUST be monitored in slices using `concurrent.futures.wait(..., timeout=min(tick, remaining), return_when=FIRST_COMPLETED)` with tick intervals between 1.0s and 5.0s (`_watchdog_tick_seconds()`).
2. **Liveness Heartbeat Touch**:
   On every wait slice and daemon tick, the orchestrator MUST touch the database liveness heartbeat via `touch_daemon_liveness(database)`.
3. **Autonomous Telegram HITL Review Sweeps**:
   The orchestrator MUST trigger `_run_auto_publish_sweep()` at least once every 30 seconds during futures awaiting and tick loops. The sweep MUST evaluate stories in `PENDING_REVIEW` status and automatically publish those whose approval window (default 24h, configured via `AUTO_PUBLISH_TIMEOUT_HOURS`) has elapsed without rejection.
4. **24-Hour Maintenance Sweeps**:
   The orchestrator MUST execute `_run_24h_maintenance_sweep()` at least once every 24 hours (`86,400s`), synchronizing published video metrics, computing empirical performance scores, and pruning underperforming videos.
5. **Watchdog Subprocess Timeout & hung FFmpeg Termination**:
   If a worker future exceeds `_turn_timeout_seconds()`, the orchestrator MUST cancel the future, terminate any orphaned FFmpeg subprocesses via `terminate_hung_ffmpeg(max_age_seconds=0, parent_pid=os.getpid(), grace_seconds=1.0)`, and emit a `RETRYABLE_FAILED` result with `error_code="timeout"`.

#### Scenario: Responsive future drainage with interleaved liveness updates (Happy Path)
- **Given** two active lane worker futures running in the thread pool
- **When** `_collect_futures_responsive` drains the futures
- **Then** it MUST wait in short slices ($\le 5.0\text{s}$)
- **And** invoke `touch_daemon_liveness` on each slice until all futures complete or timeout.

#### Scenario: Automated Telegram review sweep triggers during turn wait (Happy Path)
- **Given** a long-running composition future taking 45 seconds to complete
- **When** `_collect_futures_responsive` monitors the future
- **Then** after 30 seconds have elapsed since the last sweep, `_run_auto_publish_sweep` MUST be invoked
- **And** any expired pending review items MUST be processed without interrupting video composition.

#### Scenario: Watchdog cancels timed-out worker future and terminates hung processes (Edge Case)
- **Given** a worker thread executing an FFmpeg encoding pass that hangs indefinitely
- **When** elapsed monotonic time reaches `_turn_timeout_seconds()`
- **Then** the orchestrator MUST cancel the future
- **And** invoke `terminate_hung_ffmpeg` to terminate hung FFmpeg subprocesses
- **And** record a `RETRYABLE_FAILED` turn result with error code `timeout`.

---

### Requirement: Graceful Process Lifecycle, Signal Trapping, and Zombie Reaping
The daemon orchestrator MUST guarantee clean process lifecycle management, signal handling, and child process reclamation across continuous 24/7 headless operation.

1. **Signal Trapping (`SIGINT`, `SIGTERM`)**:
   The daemon MUST register signal handlers for `SIGINT` and `SIGTERM` that set `_SHUTDOWN_REQUESTED = True`.
2. **Graceful Turn Draining**:
   Upon receiving a shutdown signal, the loop MUST NOT dispatch new lane turns. Active worker futures MUST be given a bounded grace period ($\le 5\text{s}$ in testing/supervised mode, or up to the watchdog timeout) to complete cleanly and release database leases.
3. **Safe Thread Pool Shutdown**:
   Worker pools MUST be terminated via `pool.shutdown(wait=True, cancel_futures=True)` without leaving orphaned background threads.
4. **Zombie Process Reaping (`_reap_zombies_safe`)**:
   On every daemon tick and within future collection loops, the orchestrator MUST call `_reap_zombies_safe()`, executing:
   ```python
   while True:
       pid, status = os.waitpid(-1, os.WNOHANG)
       if pid <= 0:
           break
   ```
   to reclaim any terminated child processes (FFmpeg, ffprobe, audio mixers) and prevent OS process table exhaustion (`ECHILD` handled safely).

#### Scenario: Graceful daemon shutdown on SIGTERM / SIGINT signal (Happy Path)
- **Given** a running daemon with one active worker thread
- **When** the daemon receives `SIGTERM`
- **Then** `_SHUTDOWN_REQUESTED` MUST become `True`
- **And** the orchestrator MUST stop dispatching new lanes
- **And** wait for active tasks to finish within the shutdown timeout
- **And** exit with return code 0 without database corruption.

#### Scenario: Non-blocking zombie process reaping on daemon tick (Happy Path)
- **Given** an FFmpeg subprocess that has completed and exited, becoming a defunct zombie process
- **When** the daemon executes its tick loop
- **Then** `_reap_zombies_safe` MUST reap the dead process PID via `os.waitpid(-1, os.WNOHANG)`
- **And** no zombie processes MUST remain in the process table.

#### Scenario: Immediate shutdown response when idle (Happy Path)
- **Given** the daemon is idle and sleeping in `_responsive_sleep` waiting for the next cadence window
- **When** `SIGINT` is received
- **Then** `_responsive_sleep` MUST detect the shutdown flag and return immediately ($\le 1.0\text{s}$)
- **And** the daemon loop MUST terminate cleanly without waiting for the full sleep duration.
