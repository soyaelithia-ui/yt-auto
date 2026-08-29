# Proposal: Resource Leak Prevention

## Intent
Subprocess pipe chains in 4 render modules lack `try/finally` guards, allowing crashes to orphan FFmpeg/browser processes and leak OS resources. Defense-in-depth `atexit` reaper covers catastrophic failures where `finally` cannot execute.

## Scope

### In Scope
- `try/finally` subprocess + browser cleanup in `proc_engine.py`, `subtitles.py`, `stream_renderer.py`, `web_renderer.py`
- New `atexit` orphan reaper module (`src/core/lifecycle.py`)
- Performance impact documentation (per config requirement)

### Out of Scope
- `db.py` `_get_connection()` legacy fix (separate change — different domain)
- MagicMock DB test debris / `conftest.py` fixture (test hygiene — separate change)
- Refactoring render modules to use `run_ffmpeg` (covered by `media-pipeline-hardening`)

## Capabilities

### New Capabilities
- `process-lifecycle-reaper`: Lightweight `atexit`-registered reaper that tracks spawned child PIDs and terminates orphans at interpreter exit. Safety net for `SIGKILL` / interpreter crash scenarios.

### Modified Capabilities
- `media-pipeline-hardening`: Delta — subprocess cleanup guards for direct `Popen` pipe chains in render modules not covered by centralized `run_ffmpeg`.

## Approach
Per exploration Approach 3 (Targeted Hardening + Atexit Sweep):

1. **Render module fixes** — Wrap dual-Popen pipe chains and browser sessions in `try/finally` blocks that `kill()` + `wait()` subprocesses and `close()` browsers on any exception.
2. **Atexit reaper** — New `src/core/lifecycle.py` registers child PIDs on spawn, deregisters on clean exit, and walks remaining PIDs at `atexit` to `SIGTERM` → `SIGKILL` orphans.
3. **Integration** — Render modules register their Popen PIDs with the reaper; reaper auto-activates on first import.

## Affected Areas
| Area | Impact | Description |
|------|--------|-------------|
| `src/media/proc_engine.py` L276-297 | HIGH | Dual Popen pipe chain needs `try/finally` |
| `src/media/subtitles.py` L328-353 | HIGH | Same dual Popen pattern, no cleanup on exception |
| `src/compositing/stream_renderer.py` L165-211 | MEDIUM | FFmpeg + browser cleanup gaps in exception handler |
| `src/media/web_renderer.py` L211-240 | MEDIUM | Missing kill/cleanup for FFmpeg + browser |
| `src/core/lifecycle.py` (new) | LOW | New module, no existing code affected |

## Risks
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `finally` block masks original exception | Low | Re-raise after cleanup; use `suppress()` only for cleanup errors |
| Atexit reaper kills unrelated PIDs | Low | Track only PIDs spawned by our modules; verify PID ownership |
| `kill()` on already-exited process raises | Low | Guard with `poll()` check + `OSError` catch |

## Performance Impact
The `try/finally` guards wrap the **outer Popen lifecycle** (one per render call), not per-frame operations. Overhead is a single extra stack frame per render invocation — **zero measurable impact** on frame throughput or encoding latency. The atexit reaper runs only at interpreter shutdown, outside any render path.

## Rollback Plan
1. Revert the 4 render module files to their pre-change state (pure additive `try/finally` wrappers — no logic changes)
2. Remove `src/core/lifecycle.py` and its import registrations
3. No database migrations, config changes, or external dependencies involved

## Dependencies
- None (all changes use stdlib `atexit`, `os`, `signal` — no new packages)

## Success Criteria
- [ ] All 4 render modules have `try/finally` guards covering every `Popen` and browser instance
- [ ] No orphaned FFmpeg/browser processes after simulated crash in each render path (test)
- [ ] Atexit reaper terminates tracked orphan PIDs on interpreter exit (test)
- [ ] Existing test suite passes with no regressions
- [ ] No measurable performance degradation in render benchmarks
