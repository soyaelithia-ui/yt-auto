# Tasks: Resource Leak Prevention

## Review Workload Forecast
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Low

## Phase 1: Lifecycle Reaper Foundation (TDD RED -> GREEN)
- [x] 1.1 [TDD-RED] Create unit test suite `tests/unit/test_lifecycle.py`:
  - Test thread-safe PID registration and deregistration in `register_process()` and `unregister_process()`.
  - Test `cleanup_subprocesses()` pipe draining/closing (`stdin`, `stdout`, `stderr`), `terminate()`, `wait()`, and fallback `kill()`.
  - Test suppression of secondary cleanup errors (`OSError`, `ProcessLookupError`, `BrokenPipeError`).
  - Test `sweep_tracked_processes()` `atexit` sweep signaling `SIGTERM`/`SIGKILL` to active PIDs and ignoring dead PIDs.
- [x] 1.2 [TDD-GREEN] Implement process lifecycle management in `src/core/lifecycle.py`:
  - Implement thread-safe active PID set guarded by `threading.Lock`.
  - Implement `register_process()`, `unregister_process()`, and `cleanup_subprocesses()`.
  - Register `sweep_tracked_processes()` with `atexit.register()`.
  - Verify `pytest tests/unit/test_lifecycle.py` passes.

## Phase 2: Render Subprocess Exception Cleanup (TDD RED -> GREEN)
- [x] 2.1 [TDD-RED] Create unit test suite `tests/unit/test_media_cleanup.py`:
  - Test exception simulation in `src/media/proc_engine.py` verifying child processes are terminated and exception is re-raised.
  - Test exception simulation in `src/media/subtitles.py` verifying dual-Popen cleanup.
  - Test exception simulation in `src/compositing/stream_renderer.py` verifying FFmpeg termination and browser cleanup.
  - Test exception simulation in `src/media/web_renderer.py` verifying FFmpeg and browser cleanup.
- [x] 2.2 [TDD-GREEN] Refactor `src/media/proc_engine.py` dual-Popen rendering to register PIDs and wrap execution in `try/finally` with `cleanup_subprocesses()`.
- [x] 2.3 [TDD-GREEN] Refactor `src/media/subtitles.py` dual-Popen subtitle burning to register PIDs and wrap in `try/finally` with `cleanup_subprocesses()`.
- [x] 2.4 [TDD-GREEN] Refactor `src/compositing/stream_renderer.py` to wrap FFmpeg process and Playwright browser in `try/finally` cleanup.
- [x] 2.5 [TDD-GREEN] Refactor `src/media/web_renderer.py` to wrap FFmpeg process and Playwright browser in `try/finally` cleanup.
- [x] 2.6 Verify `pytest tests/unit/test_media_cleanup.py` passes.

## Phase 3: Integration & Reaper Verification (TDD RED -> GREEN)
- [x] 3.1 [TDD-RED] Create integration test suite `tests/integration/test_lifecycle_reaper.py`:
  - Spawn real child processes and simulate unhandled interpreter termination to verify `atexit` orphan reaping.
  - Verify zero orphaned processes or leaked file descriptors after forced exit.
- [x] 3.2 [TDD-GREEN] Verify `pytest tests/integration/test_lifecycle_reaper.py` passes.
- [x] 3.3 Run complete test suite (`pytest tests/unit tests/integration`) to confirm zero regressions across all modules.
