# Technical Design: Hardened Autonomous Multi-Lane Daemon Orchestration Engine

## 1. Executive Summary & Architecture Context

This technical design formalizes the implementation architecture for the **Hardened Autonomous Multi-Lane Daemon Orchestration Engine** (`daemon_lane_orchestration`) within the `yt-auto` media production system.

### 1.1 Problem Context
The pipeline requires continuous, 24/7 headless production across two active thematic channels (`horror` and `drama`), executing four distinct production lanes configured in `config/lanes.json`:
1. `horror-scp-shorts` (Vertical 9:16, image animation, 300s cadence)
2. `horror-horror-long` (Horizontal 16:9, multi-act director, 1800s cadence)
3. `drama-aita-long` (Horizontal 16:9, multi-act director, 1800s cadence, 900s initial offset)
4. `drama-drama-shorts` (Vertical 9:16, video loop, 300s cadence, 150s initial offset)

Prior to this change:
- **Coupling & Monolithic Entrypoints**: `src/daemon.py` spanned over 1,200 lines, bundling CLI argument parsing, single-run execution, Telegram polling, database heartbeat touching, process cleanup, and thread pool dispatching. `src/orchestrator/` lacked a dedicated `scheduler.py` module encapsulating the autonomous multi-lane scheduling lifecycle.
- **Lease Contention & Orphan Leases**: High-throughput multi-lane execution can encounter orphan leases in SQLite (`lane_leases` and `runs` tables) when worker threads or underlying FFmpeg processes hang or crash. Without deterministic lease heartbeating, periodic stale lease recovery (`LeaseReaper`), and automated child process reaping (`reap_zombies`), stale locks can block lane throughput.
- **Cadence Gating & Anti-Burst Protection**: Standard cron-like schedulers attempt to catch up after daemon downtime, which would flood the pipeline with concurrent renders, exhausting LLM quotas and CPU limits. Pure forward cadence progression and adaptive empty-lane backoffs (60s–120s) must be deterministically preserved.
- **Asynchronous HITL Review Integration**: Human-in-the-loop (HITL) Telegram approvals require responsive background sweeps (`_run_auto_publish_sweep` every 30s) and callback polling without interfering with video composition threads.
- **Strict Resource Target Governance (AGENTS.md Section 5)**: Multi-lane concurrent rendering must strictly comply with the hard operational ceiling of **≤ 2 CPU Cores** (≤ 200% thread aggregate) and **≤ 2.0 GiB RAM** (2,048 MiB peak resident memory). Render concurrency must be partitioned via global semaphores (`_SHORT_RENDER_SEMAPHORE = 2`, `_LONG_RENDER_SEMAPHORE = 1`).
- **Test Suite Flakiness & Legacy Lane Drift**: Unit tests in `tests/unit/test_daemon_lanes.py` and `tests/unit/test_lane_scheduler.py` contained residual hardcoded references to legacy lane IDs (`moku-scp-shorts`, `aelithia-aita-long`), causing test suite failures against canonical channel identifiers (`horror`, `drama`).

---

## 2. Technical Approach & Architecture Decisions (ADRs)

### ADR-01: Decoupled `LaneDaemonOrchestrator` Lifecycle in `src/orchestrator/scheduler.py`
- **Context**: Low-level daemon execution, task dispatching, and thread pool management were tightly coupled inside `src/daemon.py`, preventing modular lifecycle testing and violating Single Responsibility Principles.
- **Decision**: Extract the multi-lane scheduling engine into `LaneDaemonOrchestrator` in `src/orchestrator/scheduler.py`. The class encapsulates:
  1. `initialize()`: Preflight checks, database migrations, initial lane offset seeding, and startup stale lease recovery.
  2. `tick()`: Single evaluation cycle performing zombie process reaping, stale lease reclamation, background sweeps, due lane selection, and asynchronous worker submission.
  3. `run_loop()`: Continuous 24/7 execution loop with responsive interval waits and graceful signal interception.
  4. `request_shutdown()`: Clean cancellation and bounded future draining.
- **Alternatives Considered**:
  - *Alternative A: Keep scheduling in `src/daemon.py`*: Continuing to expand `src/daemon.py`. *Rejected*: Bloats a 1,200-line file further and violates Section 8 of `AGENTS.md`.
  - *Alternative B: Asyncio-based loop*: Rewriting the daemon to use `asyncio`. *Rejected*: Subprocess execution (FFmpeg), Edge TTS, SQLite, and repository operations are synchronous/blocking; an asyncio loop would require intrusive wrappers and introduce event-loop contention without measurable resource gains.
- **Rationale**: A dedicated orchestrator class decouples scheduling logic from CLI facades and enables comprehensive mocking and integration testing in headless environments.

### ADR-02: Atomic SQLite WAL Lane Leasing & Stale Recovery via `LeaseReaper`
- **Context**: Concurrent worker threads claiming jobs simultaneously risk SQLite lock contention (`OperationalError: database is locked`) or duplicate story/lane execution if transactional boundaries are not strictly isolated.
- **Decision**: In `src/core/repository/leases.py` and `src/core/repository/queue.py`:
  1. Acquire lane leases inside `BEGIN IMMEDIATE` transactions in SQLite WAL mode.
  2. Embed unique worker signatures: `lane-{lane_id}:{hostname}:{pid}:{thread_id}`.
  3. Bound lease expiration to $\max(900, \text{RENDER\_TIMEOUT\_SECONDS} // 2)$.
  4. Worker threads touch lease heartbeats (`heartbeat_lane_lease`) at pipeline stage boundaries.
  5. Automatically execute `LeaseReaper.reap_once()` at daemon startup and on every tick, transitioning abandoned runs and stories to `RETRYABLE_FAILED` with error code `lease_expired`.
- **Alternatives Considered**:
  - *Alternative A: File-based lockfiles per lane*: Using `.lock` files in `data/locks/`. *Rejected*: Vulnerable to orphan stale locks after OS crashes and does not maintain transactional atomicity with story state in `shorts_queue.db`.
- **Rationale**: SQLite WAL mode with `BEGIN IMMEDIATE` provides true ACID guarantees, while `LeaseReaper` eliminates deadlocks from crashed worker processes.

### ADR-03: Render Concurrency Partitioning via Semaphores (`_SHORT_RENDER_SEMAPHORE = 2`, `_LONG_RENDER_SEMAPHORE = 1`)
- **Context**: A worker thread pool running up to 3 parallel lanes could simultaneously trigger multiple horizontal longform renders (1080p, 10–30 min), causing CPU aggregate utilization to spike to $> 400\%$ and exhausting memory limits.
- **Decision**: Enforce render concurrency partitioning using global threading semaphores defined in `src/core/render_guard.py`:
  1. `_SHORT_RENDER_SEMAPHORE = threading.Semaphore(2)`: At most two concurrent vertical Short renders (`image_animation` or `video_loop`).
  2. `_LONG_RENDER_SEMAPHORE = threading.Semaphore(1)`: At most one horizontal longform render (`horror-horror-long`, `drama-aita-long`). Concurrent longform renders are strictly prohibited.
  3. Worker pool size is capped at 3 workers (`YT_MAX_PARALLEL_LANES=3`).
  4. FFmpeg thread limits: `-threads 2` for audio mastering, loudness probes, and QA checks, and at most `-threads 4` for video encoding passes. Probes must specify `-vn`.
- **Alternatives Considered**:
  - *Alternative A: Single Worker Pool (Max Parallel = 1)*: Serializing all lanes sequentially. *Rejected*: Causes head-of-line blocking where a 45-second longform render starves 5-second short lanes.
  - *Alternative B: Dynamic CPU throttling based on psutil*: *Rejected*: Introduces runtime instability, complex feedback loops, and external library dependencies.
- **Rationale**: Static semaphore partitioning guarantees deterministic adherence to the **≤ 2 CPU Cores** and **≤ 2.0 GiB RAM** envelope without runtime overhead.

### ADR-04: Non-Blocking Responsive Turn Futures Collection & Child Process Reclamation
- **Context**: Calling `future.result()` without a timeout blocks the orchestrator thread. If an FFmpeg subprocess or network call hangs, the entire daemon freezes, skipping liveness heartbeats and HITL review sweeps.
- **Decision**: In `src/orchestrator/scheduler.py`:
  1. Manage worker futures using `_await_future_responsive` and `_collect_futures_responsive`, awaiting futures in slices of $\le 5.0\text{s}$ using `concurrent.futures.wait(..., timeout=min(tick, remaining), return_when=FIRST_COMPLETED)`.
  2. On every slice, touch database liveness (`touch_daemon_liveness`) and invoke `_reap_zombies_safe()`.
  3. If a future exceeds `_turn_timeout_seconds()`, cancel the future, terminate any orphaned FFmpeg subprocesses via `terminate_hung_ffmpeg()`, and record a `RETRYABLE_FAILED` result with `error_code="timeout"`.
  4. Clean zombie child processes on every tick via `os.waitpid(-1, os.WNOHANG)`.
- **Alternatives Considered**:
  - *Alternative A: Thread join with timeout*: Joining worker threads directly. *Rejected*: Doesn't integrate cleanly with `ThreadPoolExecutor` and requires manual thread pooling.
- **Rationale**: Guarantees zero daemon freeze, continuous liveness telemetry, and zero zombie process accumulation in the OS process table.

### ADR-05: Monotonic Pure-Forward Cadence Advancement & Adaptive Empty Backoff
- **Context**: Following downtime or system restarts, standard schedulers queue multiple back-to-back runs to catch up, causing sudden resource spikes. Conversely, empty lanes can busy-loop if not backed off.
- **Decision**: In `src/core/scheduler.py`:
  1. Productive fires (`PUBLISHED`, `COMPLETED`, `PENDING_REVIEW`, `RENDERED`, `UPLOAD_UNCONFIRMED`, `WAITING_YOUTUBE_LIMIT`): Advance cadence monotonically:
     $$\text{next\_due\_at} = \text{fired\_at} + \text{lane.cadence\_min\_gap\_seconds}$$
     Missed turns during outages are permanently dropped.
  2. Empty picks (`LANE_EMPTY`): Do not advance the full cadence ceiling. Apply an adaptive linear backoff ramp:
     $$\text{backoff}(k) = \min(120, 60 + 30 \times \max(0, k - 1))$$
     where $k$ is `consecutive_empty`. The next check occurs in 60s–120s, ensuring that newly scraped stories are picked up promptly without busy-waiting.
- **Alternatives Considered**:
  - *Alternative A: Exponential backoff*: $60 \times 2^k$. *Rejected*: Lanes would quickly back off to hours, starving production when new stories are added.
- **Rationale**: Pure-forward cadence eliminates catch-up bursts, and linear backoff guarantees responsive story ingestion while preventing busy polling loops.

### ADR-06: Asynchronous Telegram HITL Review Sweeps & Singleton Poller Lock
- **Context**: Telegram HITL operator reviews (approvals/rejections) must be swept continuously (every 30s) and callback polling must run continuously without conflicting or starting duplicate instances.
- **Decision**:
  1. The orchestrator invokes `_run_auto_publish_sweep()` every 30 seconds during future awaits and tick loops.
  2. The callback poller is managed as a background daemon thread protected by a file-based singleton lock `_acquire_telegram_poller_lock()` with PID verification, preventing HTTP 409 Conflict errors.
- **Alternatives Considered**:
  - *Alternative A: Webhooks instead of long-polling*: *Rejected*: Requires public HTTPS domain and inbound firewall configuration, violating headless server simplicity.
- **Rationale**: Background sweeps ensure timely publication of approved videos within the 2-hour rejection window without impacting composition threads.

### ADR-07: Backward-Compatible Forwarding Facade in `src/daemon.py`
- **Context**: Existing scripts, CLI entrypoints (`main.py daemon`), and tests rely on `src/daemon.py` functions: `start_daemon_lanes`, `run_daemon_loop`, `run_lane_once`, `request_shutdown`.
- **Decision**: Keep `src/daemon.py` as a public facade that forwards multi-lane execution to `LaneDaemonOrchestrator` in `src/orchestrator/scheduler.py`, while re-exporting necessary helper functions and state flags (`_SHUTDOWN_EVENT`, `_SHUTDOWN_REQUESTED`).
- **Rationale**: Complete backward compatibility without breaking existing CLI invocations or operational deployment scripts (`deploy/ctl.sh`).

### ADR-08: Eradication of Legacy Fantasy Channel Aliases Across Daemon Test Suites
- **Context**: Residual test references to `"moku"`, `"aelithia"`, `"moku-scp-shorts"`, and `"aelithia-aita-long"` in `tests/unit/test_daemon_lanes.py` and `tests/unit/test_lane_scheduler.py` cause test failures against canonical channels (`horror`, `drama`).
- **Decision**: Modernize all unit test fixtures, seeding functions, and assertions to use canonical thematic identifiers (`"horror"`, `"drama"`) and canonical production lane IDs (`horror-scp-shorts`, `horror-horror-long`, `drama-aita-long`, `drama-drama-shorts`).
- **Rationale**: Eliminates test drift and achieves 100% green test execution.

---

## 3. Concurrency Architecture & Data Flow

### 3.1 Autonomous Multi-Lane Daemon Scheduling Loop

```
+========================================================================================================================+
|                                              DAEMON PROCESS LIFECYCLE                                                  |
|                                                                                                                        |
|  CLI / Main (main.py daemon --lanes)                                                                                  |
|      │                                                                                                                 |
|      ▼                                                                                                                 |
|  LaneDaemonOrchestrator.initialize()                                                                                   |
|      ├── Preflight check (disk available, incident check)                                                              |
|      ├── Startup stale lease recovery (LeaseReaper.reap_once(startup=True))                                            |
|      ├── Clean expired failed runs & untracked temp files                                                              |
|      └── LaneScheduler.initialize(apply_offsets=True)  [Seeds initial cadence offsets]                                 |
+========================================================================================================================+
                                                       │
                                                       ▼
+========================================================================================================================+
|                                           MAIN SCHEDULER TICK LOOP (Continuous)                                        |
|                                                                                                                        |
|  Loop while not _SHUTDOWN_REQUESTED:                                                                                   |
|      │                                                                                                                 |
|      ├── 1. OS & DB Hygiene:                                                                                           |
|      │      ├── _reap_zombies_safe()            --> os.waitpid(-1, WNOHANG) to reclaim defunct FFmpeg child processes      |
|      │      ├── LeaseReaper.reap_once()          --> Scan lane_leases; delete expired leases & mark runs RETRYABLE_FAILED  |
|      │      └── touch_daemon_liveness(db)        --> Record timestamp in daemon_liveness (AUD-08)                         |
|      │                                                                                                                 |
|      ├── 2. Background Maintenance Sweeps:                                                                             |
|      │      ├── HITL Review Sweep (every 30s)    --> _run_auto_publish_sweep() (publishes stories pending > 2h)            |
|      │      ├── Telegram Callback Poller Check   --> Ensure poller thread active (singleton lock protected)            |
|      │      └── 24h Maintenance Sweep (every 24h)--> Score published videos, retention analytics, prune temp files     |
|      │                                                                                                                 |
|      ├── 3. Drain Active Futures:                                                                                      |
|      │      ├── Check done futures in active_jobs                                                                      |
|      │      └── Collect results, commit cadence/backoff, release leases                                                |
|      │                                                                                                                 |
|      ├── 4. Watchdog Subprocess Timeout Check:                                                                         |
|      │      ├── Identify futures exceeding _turn_timeout_seconds()                                                      |
|      │      ├── Cancel future and invoke terminate_hung_ffmpeg(max_age=0, parent_pid=self)                             |
|      │      └── Record RETRYABLE_FAILED with error_code="timeout"                                                      |
|      │                                                                                                                 |
|      ├── 5. Dynamic Due Lane Dispatch:                                                                                 |
|      │      ├── running_lanes = {active_jobs.keys()}                                                                   |
|      │      ├── available_slots = max(0, capacity - len(active_jobs))                                                  |
|      │      ├── Query: LaneScheduler.take_due_lanes(max_picks=available_slots, exclude_lanes=running_lanes)            |
|      │      └── For each LanePick: pool.submit(_execute_lane_pick, db, pick, breaker)                                  |
|      │                                                                                                                 |
|      └── 6. Responsive Sleep / Wait:                                                                                   |
|             ├── If active_jobs: wait(active_jobs, timeout=min(5.0, watchdog_tick), return_when=FIRST_COMPLETED)        |
|             └── If idle: _responsive_sleep(min(interval, seconds_until_due)) with 1s wake slices                       |
+========================================================================================================================+
                                                       │
                                                       ▼
+========================================================================================================================+
|                                           WORKER THREAD POOL EXECUTION (Parallel)                                      |
|                                                                                                                        |
|  ThreadPoolExecutor(max_workers=3, thread_name_prefix="lane")                                                          |
|      │                                                                                                                 |
|      ├── Worker Thread 1 (horror-scp-shorts)                                                                           |
|      │      ├── Atomic claim_for_lane() in SQLite WAL via BEGIN IMMEDIATE                                              |
|      │      ├── Stage 01..08: Ingest, LLM Script, Narration TTS, Audio Ducking                                         |
|      │      ├── Stage 09: Video Composition                                                                           |
|      │      │      ├── Acquire _SHORT_RENDER_SEMAPHORE (Capacity: 2)                                                   |
|      │      │      ├── UnifiedEncoder atomic single-pass Ken Burns image animation                                     |
|      │      │      └── Release _SHORT_RENDER_SEMAPHORE                                                                 |
|      │      ├── Heartbeat touch_lease_heartbeat() at each stage boundary                                               |
|      │      ├── Stage 10..12: QA Gating, Review Notification / Telegram, YouTube Upload                               |
|      │      └── Finish run, commit_fire(advance cadence), release lease, clean temp intermediates                      |
|      │                                                                                                                 |
|      ├── Worker Thread 2 (horror-horror-long)                                                                          |
|      │      ├── Atomic claim_for_lane() in SQLite WAL via BEGIN IMMEDIATE                                              |
|      │      ├── Stage 01..08: Ingest, LLM Multi-Act Script, Narration TTS                                              |
|      │      ├── Stage 09: Video Composition                                                                           |
|      │      │      ├── Acquire _LONG_RENDER_SEMAPHORE (Capacity: 1)  <-- STRICT SERIALIZATION                          |
|      │      │      │   [Any other longform render MUST block until this releases]                                      |
|      │      │      ├── Multi-Act Director stream-copy concat (-c:v copy) (turnaround <= 45s)                          |
|      │      │      └── Release _LONG_RENDER_SEMAPHORE                                                                  |
|      │      ├── Heartbeat touch_lease_heartbeat() at each stage boundary                                               |
|      │      └── Finish run, commit_fire(advance cadence), release lease, clean temp intermediates                      |
|      │                                                                                                                 |
|      └── Worker Thread 3 (drama-drama-shorts)                                                                          |
|             ├── Atomic claim_for_lane() in SQLite WAL via BEGIN IMMEDIATE                                              |
|             ├── Stage 09: Video Composition                                                                           |
|             │      ├── Acquire _SHORT_RENDER_SEMAPHORE (Capacity: 2)                                                   |
|             │      ├── Video-loop stream-copy composition (-c:v copy) (turnaround < 5s)                                |
|             │      └── Release _SHORT_RENDER_SEMAPHORE                                                                 |
|             └── Finish run, commit_fire(advance cadence), release lease, clean temp intermediates                      |
+========================================================================================================================+
```

### 3.2 Atomic Lane Lease Protocol & Stale Recovery Flow

```
   Worker Thread                    QueueRepository (WAL)                 lane_leases / runs              LeaseReaper
        │                                     │                                    │                           │
        │── claim_for_lane(lane_id, ch) ─────>│                                    │                           │
        │                                     │── BEGIN IMMEDIATE ────────────────>│                           │
        │                                     │── Check active lease for lane ────>│                           │
        │                                     │<── [Active lease exists?] ─────────│                           │
        │                                     │   (If yes: ROLLBACK & return None) │                           │
        │                                     │── INSERT INTO lane_leases ────────>│                           │
        │                                     │── INSERT INTO runs (PROCESSING) ──>│                           │
        │                                     │── COMMIT ─────────────────────────>│                           │
        │<── Return story & run_id ───────────│                                    │                           │
        │                                     │                                    │                           │
        │── Pipeline execution stage 1..N ───>│                                    │                           │
        │── heartbeat_lane_lease(run_id) ────>│── UPDATE heartbeat_at, expires_at ─>│                           │
        │                                     │                                    │                           │
        │ [Case A: Successful Turn]           │                                    │                           │
        │── finish_lane_run(COMPLETED) ──────>│── UPDATE runs (COMPLETED) ────────>│                           │
        │                                     │── DELETE FROM lane_leases ────────>│                           │
        │                                     │                                    │                           │
        │ [Case B: Worker Crash / OOM]        │                                    │                           │
        │   Worker process terminates         │                                    │                           │
        │                                     │                                    │── reap_once() ───────────>│
        │                                     │                                    │   Check PID alive / TTL   │
        │                                     │                                    │<── Dead PID or expired ───│
        │                                     │── BEGIN IMMEDIATE ────────────────>│                           │
        │                                     │── UPDATE runs (RETRYABLE_FAILED) ─>│                           │
        │                                     │── UPDATE stories (RETRYABLE_FAILED)│                           │
        │                                     │── DELETE FROM lane_leases ────────>│                           │
        │                                     │── COMMIT ─────────────────────────>│                           │
```

---

## 4. Interfaces & Data Contracts

### 4.1 `LanePick` Contract (`src/core/scheduler.py`)

```python
from dataclasses import dataclass
from src.core.domain import CanonicalChannel

@dataclass(frozen=True, slots=True)
class LanePick:
    """One lane the scheduler has decided to fire on this tick."""
    lane_id: str
    channel: CanonicalChannel
    fired_at: int
    next_due_at: int
```

### 4.2 `LaneDaemonConfig` Contract (`src/orchestrator/scheduler.py`)

```python
from dataclasses import dataclass, field
from typing import Optional, Set

@dataclass(frozen=True, slots=True)
class LaneDaemonConfig:
    """Configuration options governing multi-lane daemon orchestration."""
    db_path: str
    interval_seconds: int = 60
    max_picks: Optional[int] = None
    lanes_filter: Optional[Set[str]] = None
    max_parallel: int = 3
    generate_only: bool = False
    max_ticks: Optional[int] = None
    apply_offsets: bool = True
    enable_sweeps: bool = True
```

### 4.3 `ConcurrencyPolicy` Contract (`src/orchestrator/scheduler.py`)

```python
import threading
from dataclasses import dataclass
from src.core.render_guard import _LONG_RENDER_SEMAPHORE, _SHORT_RENDER_SEMAPHORE

@dataclass(frozen=True, slots=True)
class ConcurrencyPolicy:
    """System-wide concurrency limits adhering to AGENTS.md Section 5."""
    max_parallel_lanes: int = 3
    short_render_semaphore: threading.Semaphore = _SHORT_RENDER_SEMAPHORE  # Capacity 2
    long_render_semaphore: threading.Semaphore = _LONG_RENDER_SEMAPHORE    # Capacity 1
    ffmpeg_probe_threads: int = 2
    ffmpeg_encode_max_threads: int = 4
    cpu_cores_hard_ceiling: float = 2.0
    ram_gib_hard_ceiling: float = 2.0
```

### 4.4 `LeaseReaperInterface` Contract (`src/core/lease_reaper.py`)

```python
from typing import Optional, Protocol

class LeaseReaperInterface(Protocol):
    """Protocol for active lease and orphan recovery."""
    def reap_once(self, startup: bool = False, channel: Optional[str] = None) -> int:
        """Scan active leases; delete expired rows and mark abandoned runs RETRYABLE_FAILED."""
        ...
```

### 4.5 Turn Result Contract

```python
from typing import Any, Optional, TypedDict

class TurnResult(TypedDict, total=False):
    status: str          # "PUBLISHED", "COMPLETED", "RENDERED", "PENDING_REVIEW", "LANE_EMPTY", "RETRYABLE_FAILED", "WAITING_LLM_QUOTA"
    lane: Optional[str]  # e.g. "horror-scp-shorts"
    channel: str         # "horror", "drama"
    error: Optional[str]
    error_code: Optional[str]  # e.g. "timeout", "lease_expired", "lane_turn_exception"
    run_id: Optional[str]
    work_dir: Optional[str]
```

---

## 5. File Changes

| File Path | Action | Description of Changes |
| :--- | :--- | :--- |
| `src/orchestrator/scheduler.py` | **Create** | Implements `LaneDaemonOrchestrator`, `LaneDaemonConfig`, `ConcurrencyPolicy`, `_await_future_responsive`, `_collect_futures_responsive`, `_reap_zombies_safe`, and execution loop. Functions under ~100 lines. |
| `src/daemon.py` | **Modify** | Forwarding facade. Delegates `start_daemon_lanes` and `run_daemon_loop` to `LaneDaemonOrchestrator`. Preserves public helpers (`_responsive_sleep`, `_reap_zombies_safe`, `request_shutdown`, `reset_shutdown`). |
| `src/core/repository/leases.py` | **Modify** | Hardens atomic transactional boundaries (`BEGIN IMMEDIATE`) on `lane_leases`, ensures owner signatures with thread identifiers, and validates TTL boundaries. |
| `src/core/scheduler.py` | **Modify** | Ensures `LaneScheduler` interoperability with orchestrator; validates `take_due_lanes` overdue sorting and empty streak backoff calculations. |
| `src/core/render_guard.py` | **Verify/Maintain** | SSOT for `_LONG_RENDER_SEMAPHORE` (1) and `_SHORT_RENDER_SEMAPHORE` (2). |
| `config/lanes.json` | **Verify/Maintain** | Ensures enabled production lanes (`horror-scp-shorts`, `horror-horror-long`, `drama-aita-long`, `drama-drama-shorts`) have verified cadences and offsets. |
| `tests/unit/test_daemon_lanes.py` | **Modify** | Eliminates legacy channel aliases (`moku`, `aelithia`) in favor of canonical channels (`horror`, `drama`). Fixes mock signatures and assertions. |
| `tests/unit/test_lane_scheduler.py` | **Modify** | Updates test cases to use canonical lane IDs (`horror-scp-shorts`, `drama-aita-long`) instead of legacy identifiers. |
| `tests/integration/test_daemon_multi_lane_turn.py` | **Create** | New end-to-end integration test verifying concurrent dispatch across enabled lanes, lease acquisition, cadence advance, and clean shutdown under synthetic offline conditions. |

---

## 6. Strict Resource Governance & Performance Budgets (AGENTS.md Section 5)

### 6.1 Inviolable Hard Target Ceilings
All daemon loops, thread pools, and media processing workflows MUST strictly operate within:
- **CPU Utilization**: $\le 2.0\text{ CPU Cores}$ ($\le 200\%$ aggregate CPU utilization across all active threads and subprocesses).
- **Peak Resident Memory (RAM)**: $\le 2.0\text{ GiB}$ ($2,048\text{ MiB}$ peak resident set size RSS).
- **Idle Daemon Footprint**: $\le 0.05\text{ Cores}$ ($\le 5\%$) and $\le 120\text{ MiB}$ RSS during idle sleep intervals.

### 6.2 Concurrency Bounding Rules
1. **Thread Pool Sizing**: Worker thread pool default capacity is bounded to 3 (`YT_MAX_PARALLEL_LANES=3`).
2. **Render Semaphore Partitioning**:
   - `_SHORT_RENDER_SEMAPHORE = threading.Semaphore(2)`: Max 2 concurrent vertical Short renders.
   - `_LONG_RENDER_SEMAPHORE = threading.Semaphore(1)`: Max 1 concurrent horizontal longform render. Parallel longform renders are strictly prohibited.
3. **FFmpeg Subprocess Thread Capping**:
   - Audio mastering, loudness normalization, and QA probes: strictly `-threads 2` and `-vn` (no video decoding).
   - Video encoding passes: maximum `-threads 4`.
4. **Memory Hygiene & Zero Array Buffers**:
   - Zero in-memory video array accumulation (`REG-08`). Video frames stream from disk to FFmpeg pipes or stream-copy directly.
   - Intermediate chunk files and audio buffers are cleaned immediately via `clean_run_intermediates()` in `finally` blocks.

---

## 7. Testing & Verification Strategy

### 7.1 Unit Testing Strategy
1. **`tests/unit/test_lane_scheduler.py`**:
   - Verify most-overdue lane prioritization.
   - Verify pure-forward cadence advancement (`next_due_at = fired_at + min_gap_seconds`) with zero catch-up bursts after simulated 4-hour outage.
   - Verify adaptive linear backoff on empty picks (60s then 120s).
   - Verify active lease exclusion and paused channel exclusion.
2. **`tests/unit/test_daemon_lanes.py`**:
   - Verify concurrent multi-lane dispatching into thread pool.
   - Verify failure circuit breaker recording without crashing daemon loop.
   - Verify resumable claims (`claim_resumable`) prioritized over fresh claims.
   - Verify responsive sleep and graceful shutdown interruption.
3. **`tests/unit/test_lease_reaper.py`**:
   - Verify detection and reaping of dead worker PIDs.
   - Verify recovery of expired TTL leases.
   - Verify transition of abandoned runs and stories to `RETRYABLE_FAILED` with `lease_expired`.

### 7.2 Integration Smoke Testing Strategy
- **`tests/integration/test_daemon_multi_lane_turn.py`**:
  - Seeds synthetic stories across `horror-scp-shorts`, `horror-horror-long`, `drama-aita-long`, `drama-drama-shorts`.
  - Runs `LaneDaemonOrchestrator` in offline test mode for 2 ticks.
  - Asserts that:
    1. Lanes are dispatched concurrently up to thread pool capacity.
    2. Atomic leases are recorded in `lane_leases` with valid owner signatures.
    3. Cadence ceilings advance upon completion.
    4. Child processes are reaped and the orchestrator shuts down cleanly within $\le 5$ seconds.
    5. Zero external network requests or Playwright subprocesses are emitted.

### 7.3 Anti-Regression Guardrail Verification
Execute `./scripts/verify_integrity.sh` and fast anti-regression test suite:
```bash
.venv/bin/pytest tests/unit/test_anti_regression_guardrails.py -v
```
Verifying invariants `REG-01` through `REG-14`.

---

## 8. Threat Matrix & Operational Mitigations

| Threat / Failure Mode | Likelihood | Impact | Detection Mechanism | Automated Mitigation Strategy |
| :--- | :--- | :--- | :--- | :--- |
| **SQLite WAL Lock Contention** | Medium | Medium | `sqlite3.OperationalError: database is locked` in logs. | Use `BEGIN IMMEDIATE` transactions, short transaction scopes, 30s busy timeout (`PRAGMA busy_timeout = 30000`), and passive checkpoints (`wal_checkpoint_passive`). |
| **Worker Subprocess Freeze (FFmpeg Hang)** | Medium | High | Monotonic timer exceeds `_turn_timeout_seconds()`. | Watchdog in `_await_future_responsive` cancels future, executes `terminate_hung_ffmpeg(max_age=0, parent_pid=os.getpid(), grace=1.0)`, and records `RETRYABLE_FAILED`. |
| **Orphan Leases from Crashed Workers** | Low | High | Active lease in `lane_leases` blocking lane dispatch. | `LeaseReaper.reap_once()` checks `os.kill(pid, 0)` for dead local PIDs and reaps expired TTL leases on every tick, resetting runs to `RETRYABLE_FAILED`. |
| **Zombie Child Process Accumulation** | Medium | Medium | Defunct processes visible in `ps aux`. | `_reap_zombies_safe()` executes non-blocking `os.waitpid(-1, os.WNOHANG)` on every daemon tick and future await slice. |
| **Catch-up Bursts After Outage** | Low | High | Burst of concurrent renders saturating CPU/LLM quotas. | Pure-forward cadence commitment: `next_due_at = fired_at + min_gap_seconds`. Missed intervals are permanently discarded. |
| **Resource Target Ceiling Breach (> 2 Cores / > 2 GB RAM)** | Low | High | Process resident memory > 2,048 MiB or CPU > 200%. | Semaphores `_SHORT_RENDER_SEMAPHORE = 2` and `_LONG_RENDER_SEMAPHORE = 1` strictly serialize heavy operations. FFmpeg threads bounded to 2 and 4. |
| **Duplicate Telegram Poller Conflict (HTTP 409)** | Low | Medium | Telegram API returns 409 Conflict error. | Singleton lock file `_acquire_telegram_poller_lock()` with active PID validation ensures only one poller thread runs. |

---

## 9. Rollback & Disaster Recovery Plan

If unexpected regressions, deadlocks, or resource ceiling breaches occur upon deployment:

1. **Immediate Execution Fallback**:
   - Set environment variable `YT_USE_LEGACY_DAEMON=1` to revert to legacy single-channel loop execution.
   - Lower parallel concurrency to serialized single-worker mode via `YT_MAX_PARALLEL_LANES=1`.
2. **Database Recovery (Zero Schema Rollback Required)**:
   - Clear stuck leases and reconcile state safely without schema modification:
     ```bash
     python3 -c "from src.core.lease_reaper import LeaseReaper; LeaseReaper().reap_once(startup=True)"
     ```
   - All database tables (`lane_leases`, `scheduler_state`, `channel_controls`, `runs`) remain 100% backward-compatible.
3. **Code Reversion**:
   - Revert commit deltas cleanly via `git revert <commit-sha>`. All orchestrator changes are strictly decoupled in `src/orchestrator/scheduler.py` without modifying core stage business logic.
