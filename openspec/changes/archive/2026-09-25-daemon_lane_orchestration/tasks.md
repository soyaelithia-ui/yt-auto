# Tasks: Hardened Autonomous Multi-Lane Daemon Orchestration Engine

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~1,250 - 1,550 lines (~650 lines source, ~650 lines tests, ~100 lines contracts/config) |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | 5 Chained PRs (discrete work units aligned with feature-branch-chain) |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Foundation, Data Contracts & Concurrency Semaphores | PR 1 | `.venv/bin/pytest tests/unit/test_daemon_concurrency.py -v` | In-memory threading lock simulator and data contract validation harness | Revert `src/core/contracts/daemon.py`, `src/core/concurrency.py`, `src/core/render_guard.py` |
| 2 | Decoupled LaneDaemonOrchestrator Lifecycle Engine | PR 2 | `.venv/bin/pytest tests/unit/test_lane_daemon_orchestrator.py -v` | Standalone orchestrator lifecycle simulator with mocked thread pool, SQLite WAL queue, and watchdog timers | Revert `src/orchestrator/scheduler.py`, `tests/unit/test_lane_daemon_orchestrator.py` |
| 3 | Daemon Integration & Compatibility Forwarding | PR 3 | `.venv/bin/pytest tests/unit/test_lane_daemon_orchestrator.py tests/unit/test_cli.py -k "daemon" -v` | CLI handler dispatcher and backward-compatible daemon facade runner | Revert `src/daemon.py`, `src/cli/handlers/daemon.py` |
| 4 | Test Suite Modernization & Canonical Channel Alias Eradication | PR 4 | `.venv/bin/pytest tests/unit/test_daemon_lanes.py tests/unit/test_lane_scheduler.py -v` | Local SQLite database test fixture with canonical channel queues (`horror`, `drama`) | Revert `tests/unit/test_daemon_lanes.py`, `tests/unit/test_lane_scheduler.py` |
| 5 | Synthetic Offline Multi-Lane Integration Turn & Anti-Regression Guardrails | PR 5 | `.venv/bin/pytest tests/integration/test_daemon_multi_lane_turn.py tests/unit/test_anti_regression_guardrails.py -v && ./scripts/verify_integrity.sh` | Multi-lane offline execution runner with simulated pipeline stages, process watcher, and repository integrity gate | Revert `tests/integration/test_daemon_multi_lane_turn.py`, `tests/unit/test_anti_regression_guardrails.py` |

---

## Phase 1: Foundation, Data Contracts & Concurrency Semaphores

- [x] 1.1 **[RED]** Create new test module `tests/unit/test_daemon_concurrency.py` defining concurrency and contract assertions:
  - `test_concurrency_policy_defaults`: Validate default capacity (`max_parallel_lanes = 3`, `_SHORT_RENDER_SEMAPHORE = 2`, `_LONG_RENDER_SEMAPHORE = 1`, `ffmpeg_probe_threads = 2`, `ffmpeg_encode_max_threads = 4`, `cpu_cores_hard_ceiling = 2.0`, `ram_gib_hard_ceiling = 2.0`).
  - `test_render_semaphore_isolation`: Validate `_SHORT_RENDER_SEMAPHORE` has capacity 2, `_LONG_RENDER_SEMAPHORE` has capacity 1, and token acquisitions are completely independent.
  - `test_long_render_semaphore_blocks_second_caller`: Test that acquiring `_LONG_RENDER_SEMAPHORE` blocks a second caller when non-blocking acquire is tried, guaranteeing horizontal longform renders are serialized.
  - `test_short_render_semaphore_allows_two_blocks_third`: Test that acquiring `_SHORT_RENDER_SEMAPHORE` twice succeeds and the third non-blocking acquire fails.
  - `test_lane_daemon_config_contract_validation`: Verify `LaneDaemonConfig` dataclass slots, immutability, default arguments (`interval_seconds = 60`, `max_parallel = 3`, `apply_offsets = True`, `enable_sweeps = True`).
  - `test_turn_result_typed_dict_keys`: Verify `TurnResult` TypedDict structure and field types (`status`, `lane`, `channel`, `error`, `error_code`, `run_id`, `work_dir`).
  - `test_acquire_render_guard_context_manager`: Verify context manager cleanly acquires and releases respective short/long semaphores even when exceptions are raised.
  - Concrete edit target: `tests/unit/test_daemon_concurrency.py` (new test file).
  - Concrete inspection targets: `src/core/render_guard.py` (read-only), `AGENTS.md` (read-only).

- [x] 1.2 **[GREEN]** Implement daemon data contracts in `src/core/contracts/daemon.py`:
  - Implement `LaneDaemonConfig` (`@dataclass(frozen=True, slots=True)`): `db_path: str`, `interval_seconds: int = 60`, `max_picks: Optional[int] = None`, `lanes_filter: Optional[Set[str]] = None`, `max_parallel: int = 3`, `generate_only: bool = False`, `max_ticks: Optional[int] = None`, `apply_offsets: bool = True`, `enable_sweeps: bool = True`.
  - Implement `ConcurrencyPolicy` (`@dataclass(frozen=True, slots=True)`): `max_parallel_lanes: int = 3`, `short_render_semaphore: threading.Semaphore`, `long_render_semaphore: threading.Semaphore`, `ffmpeg_probe_threads: int = 2`, `ffmpeg_encode_max_threads: int = 4`, `cpu_cores_hard_ceiling: float = 2.0`, `ram_gib_hard_ceiling: float = 2.0`.
  - Implement `TurnResult` TypedDict: `status: str`, `lane: Optional[str]`, `channel: str`, `error: Optional[str]`, `error_code: Optional[str]`, `run_id: Optional[str]`, `work_dir: Optional[str]`.
  - Re-export in `src/core/contracts/__init__.py`.
  - Concrete edit targets: `src/core/contracts/daemon.py` (new file), `src/core/contracts/__init__.py`.

- [x] 1.3 **[GREEN]** Centralize concurrency governance in `src/core/concurrency.py`:
  - Centralize render semaphores as single sources of truth (SSOT):
    - `_LONG_RENDER_SEMAPHORE = threading.Semaphore(1)`
    - `_SHORT_RENDER_SEMAPHORE = threading.Semaphore(2)`
    - `_SYNTHESIS_SEMAPHORE = threading.Semaphore(2)`
  - Codify FFmpeg thread bounding constants: `FFMPEG_PROBE_THREADS: Final[int] = 2`, `FFMPEG_ENCODE_MAX_THREADS: Final[int] = 4`.
  - Codify Section 5 resource ceiling invariants: `RESOURCE_CPU_CEILING_CORES: Final[float] = 2.0`, `RESOURCE_RAM_CEILING_GIB: Final[float] = 2.0`.
  - Implement `@contextmanager def acquire_render_guard(is_longform: bool, timeout: Optional[float] = None)`.
  - Update `src/core/render_guard.py` to re-export semaphores and context managers from `src/core/concurrency.py` for 100% backward compatibility.
  - Concrete edit targets: `src/core/concurrency.py` (new file), `src/core/render_guard.py`.

- [x] 1.4 **[VERIFY]** Run Phase 1 foundation test suite:
  - Command: `.venv/bin/pytest tests/unit/test_daemon_concurrency.py -v`.
  - Assert 100% pass across all concurrency semaphore and contract checks.

---

## Phase 2: Decoupled LaneDaemonOrchestrator Lifecycle Engine

- [x] 2.1 **[RED]** Create new test module `tests/unit/test_lane_daemon_orchestrator.py` defining lifecycle and execution contracts:
  - `test_orchestrator_initialization_flow`: Preflight checks, `LaneScheduler.initialize(apply_offsets=...)`, startup stale lease reaping (`LeaseReaper.reap_once(startup=True)`), and temp cleanup execution.
  - `test_orchestrator_tick_reaps_zombies_and_stale_leases`: Verifies `_reap_zombies_safe` and `LeaseReaper.reap_once` execute deterministically on each tick.
  - `test_orchestrator_tick_dispatches_due_lanes_up_to_capacity`: Mocks `take_due_lanes` and verifies picks are submitted to worker thread pool without exceeding `max_parallel`.
  - `test_orchestrator_tick_excludes_currently_running_lanes`: Ensures currently running lanes in `active_jobs` are excluded from subsequent pick queries to prevent duplicate execution of the same lane.
  - `test_orchestrator_watchdog_timeout_cancels_and_records_failed`: Simulates a worker exceeding `_turn_timeout_seconds()`, cancels future, triggers `terminate_hung_ffmpeg`, and records `RETRYABLE_FAILED` with `error_code="timeout"`.
  - `test_orchestrator_drain_futures_commits_cadence_and_releases_leases`: Verifies successful future completion calls `commit_fire` advancing `next_due_at = fired_at + min_gap_seconds` and releases database leases.
  - `test_orchestrator_drain_futures_empty_commits_adaptive_backoff`: Verifies `LANE_EMPTY` calls `commit_empty` applying linear backoff ramp (60s–120s) without advancing cadence ceiling.
  - `test_orchestrator_sweeps_execution_cadence`: Verifies HITL auto-publish sweep runs every 30s, and 24h maintenance sweep triggers every 86,400s (or every N ticks).
  - `test_orchestrator_graceful_shutdown_drains_futures`: Verifies `request_shutdown()` sets shutdown event, terminates loop, and drains active futures within bounded timeout without leaking threads.
  - `test_orchestrator_responsive_sleep_aborts_immediately_on_shutdown`: Verifies `_responsive_sleep` exits immediately ($\le 1.0\text{s}$) when shutdown is requested.
  - Concrete edit target: `tests/unit/test_lane_daemon_orchestrator.py` (new test file).
  - Concrete inspection targets: `src/daemon.py` (read-only), `src/core/scheduler.py` (read-only), `src/core/lease_reaper.py` (read-only).

- [x] 2.2 **[GREEN]** Implement `LaneDaemonOrchestrator` in `src/orchestrator/scheduler.py`:
  - Implement `LaneDaemonOrchestrator` adhering strictly to Single Responsibility Principle and ~100 line method budgets:
    - `__init__(self, config: LaneDaemonConfig)`: Store config, initialize thread pool, locks, shutdown event, and state trackers.
    - `initialize(self) -> None`: Preflight checks, database migrations, initial lane offset seeding, and startup stale lease recovery via `LeaseReaper`.
    - `tick(self, pool: ThreadPoolExecutor, active_jobs: dict[Any, tuple[LanePick, float]]) -> list[TurnResult]`: Single evaluation cycle running zombie reaping, lease recovery, background sweeps, future draining, watchdog timeout evaluation, and lane dispatching.
    - `_drain_completed_futures(self, active_jobs: dict[Any, tuple[LanePick, float]]) -> list[TurnResult]`: Non-blocking collection of finished futures, error handling, cadence commitment (`commit_fire` / `commit_empty`), and lease releases.
    - `_watchdog_check(self, active_jobs: dict[Any, tuple[LanePick, float]]) -> list[TurnResult]`: Watchdog inspection against `_turn_timeout_seconds()`, future cancellation, `terminate_hung_ffmpeg`, and timeout result recording.
    - `_dispatch_due_lanes(self, pool: ThreadPoolExecutor, active_jobs: dict[Any, tuple[LanePick, float]]) -> int`: Query `LaneScheduler.take_due_lanes` with exclusions for running lanes and submit into thread pool up to capacity.
    - `_run_sweeps_if_due(self, ticks: int) -> None`: 30-second HITL auto-publish sweep and periodic 24-hour maintenance sweeps.
    - `_reap_zombies_safe(self) -> int`: Non-blocking `os.waitpid(-1, os.WNOHANG)` loop safely catching `ECHILD`.
    - `_responsive_sleep(self, seconds: float, tick: float = 1.0) -> bool`: Sliced wait loop checking `_shutdown_event` every 1.0s.
    - `run_loop(self) -> list[TurnResult]`: Main 24/7 autonomous loop coordinating thread pool execution, signal interception, and clean final draining.
    - `request_shutdown(self) -> None`: Set shutdown event and trigger graceful draining.
  - Re-export `LaneDaemonOrchestrator` and `LaneDaemonConfig` in `src/orchestrator/__init__.py`.
  - Concrete edit targets: `src/orchestrator/scheduler.py` (new file), `src/orchestrator/__init__.py`.

- [x] 2.3 **[VERIFY]** Run Phase 2 orchestrator test suite:
  - Command: `.venv/bin/pytest tests/unit/test_lane_daemon_orchestrator.py -v`.
  - Assert 100% pass across all orchestrator lifecycle and concurrency tests.

---

## Phase 3: Daemon Integration & Compatibility Forwarding

- [x] 3.1 **[RED]** Extend `tests/unit/test_lane_daemon_orchestrator.py` to cover daemon delegation and CLI dispatch:
  - `test_daemon_start_daemon_lanes_delegates_to_orchestrator`: Verify that calling `src.daemon.start_daemon_lanes(...)` creates a `LaneDaemonOrchestrator` and executes `run_loop()`, forwarding all parameters (`interval_seconds`, `max_picks`, `db_path`, `lanes_filter`, `max_parallel`, `generate_only`, `max_ticks`).
  - `test_daemon_shutdown_flags_and_hooks_synchronized`: Ensure `daemon.request_shutdown()`, `daemon.reset_shutdown()`, and `daemon.is_shutdown_requested()` synchronize with `LaneDaemonOrchestrator`.
  - `test_cli_handler_daemon_invocation`: Verify `handle_daemon(args)` correctly constructs configuration, acquires channel locks, and delegates execution to `LaneDaemonOrchestrator`.
  - Concrete edit target: `tests/unit/test_lane_daemon_orchestrator.py`.
  - Concrete inspection targets: `src/daemon.py` (read-only), `src/cli/handlers/daemon.py` (read-only).

- [x] 3.2 **[GREEN]** Refactor `src/daemon.py` to forward to `LaneDaemonOrchestrator`:
  - Refactor `start_daemon_lanes()` to instantiate `LaneDaemonConfig` and delegate execution directly to `LaneDaemonOrchestrator(config).run_loop()`.
  - Preserve public test hooks (`scheduler_commit_fire`, `scheduler_commit_empty`) and re-export them from the orchestrator instance.
  - Preserve public utility functions (`_responsive_sleep`, `_reap_zombies_safe`, `request_shutdown`, `reset_shutdown`, `is_shutdown_requested`, `run_lane_once`, `run_pipeline_once`).
  - Maintain `run_daemon_loop = start_daemon_lanes` alias.
  - Concrete edit target: `src/daemon.py`.

- [x] 3.3 **[GREEN]** Refactor CLI daemon handler in `src/cli/handlers/daemon.py`:
  - Update `handle_daemon(args)` to construct `LaneDaemonConfig` from CLI flags (`--interval`, `--lanes`, `--max-parallel`, `--generate-only`, `--db-path`).
  - Delegate execution directly to `LaneDaemonOrchestrator` while maintaining transactional channel lock acquisition (`acquire_lock(channel)` / `release_lock(channel)` in `try...finally`).
  - Concrete edit target: `src/cli/handlers/daemon.py`.

- [x] 3.4 **[VERIFY]** Run Phase 3 integration tests:
  - Command: `.venv/bin/pytest tests/unit/test_lane_daemon_orchestrator.py tests/unit/test_cli.py -k "daemon" -v`.
  - Assert 100% pass across daemon facade and CLI handler tests.

---

## Phase 4: Test Suite Modernization & Canonical Channel Alias Eradication

- [x] 4.1 **[RED]** Analyze and reproduce failures in daemon and scheduler unit tests:
  - Run `.venv/bin/pytest tests/unit/test_daemon_lanes.py tests/unit/test_lane_scheduler.py -v` and document all 6 failures:
    - `test_most_overdue_first`: assertion mismatch (`drama-aita-long` vs `horror-horror-long`) due to legacy offset ordering.
    - `test_seconds_until_due_returns_earliest_wait`: assertion mismatch (`assert 60 == 1800`).
    - `test_no_catchup_after_long_outage`: `StopIteration` querying non-existent legacy lane `moku-scp-shorts`.
    - `test_failure_feeds_channel_breaker`: `lanes_filter=["moku-scp-shorts"]` yields empty lane set.
    - `test_resume_claim_preferred_over_fresh`: `lanes_filter=["moku-scp-shorts"]` causes story to remain `PENDING`.
    - `test_singleton_lock_bypass_ctl_concurrent_invocation`: `deploy/ctl.sh` rejects execution because Docker container `yt-automation` is running without `YT_FORCE_HOST=1`.
  - Concrete inspection targets: `tests/unit/test_daemon_lanes.py` (read-only), `tests/unit/test_lane_scheduler.py` (read-only).

- [x] 4.2 **[GREEN]** Modernize scheduler unit tests in `tests/unit/test_lane_scheduler.py`:
  - Eradicate legacy fantasy lane identifiers (`moku-scp-shorts`, `aelithia-aita-long`) in favor of canonical lane IDs (`horror-scp-shorts`, `horror-horror-long`, `drama-aita-long`, `drama-drama-shorts`).
  - Update `test_no_catchup_after_long_outage` to inspect canonical lane `horror-scp-shorts`.
  - Align `test_most_overdue_first` and `test_seconds_until_due_returns_earliest_wait` with the canonical cadence and initial offset configuration in `config/lanes.json`.
  - Preserve all forward cadence progression and adaptive empty backoff assertions.
  - Concrete edit target: `tests/unit/test_lane_scheduler.py`.

- [x] 4.3 **[GREEN]** Modernize daemon unit tests in `tests/unit/test_daemon_lanes.py`:
  - Eradicate legacy aliases (`moku`, `aelithia`, `moku-scp-shorts`, `aelithia-aita-long`). Replace with canonical channels (`horror`, `drama`) and canonical lanes (`horror-scp-shorts`, `horror-horror-long`, `drama-aita-long`, `drama-drama-shorts`).
  - Update `test_failure_feeds_channel_breaker` to use canonical `lanes_filter=["horror-scp-shorts"]` and channel `"horror"`.
  - Update `test_resume_claim_preferred_over_fresh` to use canonical `horror-scp-shorts`.
  - Update `test_singleton_lock_bypass_ctl_concurrent_invocation` to supply `env["YT_FORCE_HOST"] = "1"`, ensuring test robustness regardless of local Docker container status.
  - Concrete edit target: `tests/unit/test_daemon_lanes.py`.

- [x] 4.4 **[VERIFY]** Run Phase 4 modernized unit test suite:
  - Command: `.venv/bin/pytest tests/unit/test_daemon_lanes.py tests/unit/test_lane_scheduler.py -v`.
  - Assert 100% GREEN (all 24 tests passing).

---

## Phase 5: Synthetic Offline Multi-Lane Integration Turn & Anti-Regression Guardrails

- [x] 5.1 **[RED]** Create synthetic offline multi-lane integration turn test in `tests/integration/test_daemon_multi_lane_turn.py`:
  - `test_synthetic_offline_multi_lane_turn_concurrent_execution`:
    - Seed synthetic story records across all four enabled production lanes (`horror-scp-shorts`, `horror-horror-long`, `drama-aita-long`, `drama-drama-shorts`).
    - Run `LaneDaemonOrchestrator` in offline test mode for 2 ticks.
    - Verify concurrent dispatch up to thread pool capacity (`YT_MAX_PARALLEL_LANES = 3`).
    - Verify atomic lane lease acquisition in `lane_leases` with valid worker owner signatures (`lane-{lane_id}:{hostname}:{pid}:{thread_id}`).
    - Verify pure-forward cadence advancement (`next_due_at = fired_at + min_gap_seconds`) upon completion.
    - Verify adaptive empty backoff (60s–120s) when lanes have no pending stories.
    - Verify clean shutdown within $\le 5$ seconds with zero residual threads.
  - `test_multi_lane_turn_enforces_render_semaphores`:
    - Simulate simultaneous video render stages across horizontal longform and vertical short lanes.
    - Verify `_LONG_RENDER_SEMAPHORE` strictly serializes longform renders (N=1) while `_SHORT_RENDER_SEMAPHORE` permits up to 2 short renders.
  - `test_multi_lane_turn_offline_network_and_browser_isolation`:
    - Patch network sockets and verify zero external HTTP/HTTPS network calls and zero Playwright browser launches occur during daemon execution.
  - Concrete edit target: `tests/integration/test_daemon_multi_lane_turn.py` (new test file).
  - Concrete inspection targets: `src/orchestrator/scheduler.py` (read-only), `config/lanes.json` (read-only).

- [x] 5.2 **[RED]** Extend anti-regression guardrails in `tests/unit/test_anti_regression_guardrails.py`:
  - `test_reg14_daemon_concurrency_semaphores_and_worker_bounds`:
    - Verify `_SHORT_RENDER_SEMAPHORE._value == 2` and `_LONG_RENDER_SEMAPHORE._value == 1`.
    - Verify default worker thread pool capacity does not exceed 3 (`YT_MAX_PARALLEL_LANES <= 3`).
    - Verify `ConcurrencyPolicy` enforces hard target ceilings of $\le 2.0$ CPU Cores and $\le 2.0$ GiB RAM.
  - `test_reg10_zero_legacy_channel_names_in_daemon_and_scheduler_tests`:
    - Inspect AST/text of `tests/unit/test_daemon_lanes.py` and `tests/unit/test_lane_scheduler.py` to guarantee zero occurrences of legacy string literals `"moku-scp-shorts"` or `"aelithia-aita-long"`.
  - `test_reg01_zero_playwright_in_orchestrator`:
    - Verify `src/orchestrator/scheduler.py` contains zero imports of `playwright` or `chromium`.
  - Concrete edit target: `tests/unit/test_anti_regression_guardrails.py`.

- [x] 5.3 **[GREEN]** Wire multi-lane integration turn and anti-regression guardrails:
  - Implement full test bodies in `tests/integration/test_daemon_multi_lane_turn.py` with synthetic offline mocks.
  - Verify all new assertions in `tests/unit/test_anti_regression_guardrails.py` pass cleanly.
  - Verify all functions in `src/orchestrator/scheduler.py` and new modules remain strictly within ~100 line budget.
  - Concrete edit targets: `tests/integration/test_daemon_multi_lane_turn.py`, `tests/unit/test_anti_regression_guardrails.py`.

- [x] 5.4 **[VERIFY]** Run full verification suite and repository integrity gate:
  - Command: `.venv/bin/pytest tests/integration/test_daemon_multi_lane_turn.py tests/unit/test_anti_regression_guardrails.py -v`.
  - Command: `./scripts/verify_integrity.sh`.
  - Assert 100% green across all anti-regression invariants (`REG-01` through `REG-14`) and integration turn tests.
