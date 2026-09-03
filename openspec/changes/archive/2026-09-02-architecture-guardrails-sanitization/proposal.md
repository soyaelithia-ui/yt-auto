# Proposal: Architecture Guardrails, Path Validation & Test Isolation Sanitization

## Why

### 1. Invariant Alignment & Positive Architecture Documentation
The official architecture documentation (`docs/ARQUITECTURA.md`, Section 9) currently defines the system's headless rendering principles using negative legacy references (explicitly naming legacy browser tools in negation rules). This causes synchronization tests (`tests/e2e/test_tier1_features.py:test_f15_docs_arquitectura_synchronized`) to fail because test assertions verify zero occurrence of legacy browser tokens in documentation. Modern architectural standards require defining the visual pipeline **positively** around its native foundations: 100% native WebGPU (`wgpu-py`), Mesa Lavapipe software rendering fallback, `resvg-py` SVG vectorization, and C-level atomic `libass` subtitle transcoding. Strict automated AST-based anti-regression guardrails (`REG-01` through `REG-09` in `tests/unit/test_anti_regression_guardrails.py`) remain enforced in test suites to prevent regression into legacy dependencies.

### 2. Mock Path Leakage & Root Disk Hygiene
During test executions where database components (`src/core/repository.py:connect()`, `review/db.py:ReviewStateStore`, `review/db.py:init_review_db`, `review/db.py:get_db_connection`) are invoked with mock objects or unconfigured settings (e.g., `MagicMock` instances representing paths), SQLite creates physical database files named `<MagicMock name='mock.db_path' ...>` (along with `-wal` and `-shm` index files) directly in the project root directory. This causes filesystem pollution, uncommitted test noise, and resource leaks. Database connection entry points must strictly validate `db_path` inputs before performing any filesystem operations.

### 3. Concurrency Lock Contention & Test Isolation
`ChannelLock` in `src/core/lock.py` enforces exclusive execution using `fcntl.flock` against a shared base path (`LOCK_FILE_PATH`, defaulting to `scratch/youtube_automation.lock` or `/tmp/...`). In concurrent test runs (e.g. `pytest -n auto` or test suites touching pipeline execution), lack of isolated lock directories causes intermittent flock collisions, test flakiness, or unreleased lock handles. `src/core/lock.py` and test fixtures must support explicit lock isolation (via `tmp_path` fixtures, configurable lock directories, or environment overrides).

---

## What Changes

### 1. Positive Architecture Documentation (`docs/ARQUITECTURA.md`)
- Update Section 9 of `docs/ARQUITECTURA.md` to express architectural invariants positively:
  - **Native Procedural Rendering**: 100% native GPU-accelerated graphics pipeline using `wgpu-py` with WGSL fragment shaders, supported by CPU fallback via Mesa Lavapipe.
  - **Vectorized Typography & Dynamic Overlays**: High-performance SVG rasterization via `resvg-py` and zero-copy overlay compositing.
  - **Atomic Native Subtitles**: Direct `.ass` generation with karaoke timings (`{\kf}`) and mobile UI safe margin enforcement ($\ge 240\text{px}$) rendered natively via `libass` / FFmpeg filter chains.
  - **Unified Single-Pass Transcoding**: Atomic FFmpeg encoding (`-filter_complex`) with asynchronous `stderr` stream draining.
  - **Deterministic Memory Compositor**: Contiguous pre-allocated NumPy array buffers ($\le 140\text{ MB RAM}$) preventing memory leaks.
- Verify `tests/e2e/test_tier1_features.py:test_f15_docs_arquitectura_synchronized` passes cleanly.
- Maintain strict automated AST-based anti-regression guardrails (`REG-01` to `REG-09` in `tests/unit/test_anti_regression_guardrails.py`).

### 2. Defensive Path Validation & Disk Hygiene (`src/core/repository.py`, `review/db.py`)
- In `src/core/repository.py:connect()`:
  - Add explicit runtime path validation asserting that `db_path` is a valid string, `Path`, or `os.PathLike` representing a filesystem path.
  - Reject `unittest.mock` objects, non-path instances, and strings starting with or containing `<MagicMock` or `<Mock`, raising `TypeError` or `ValueError` immediately before invoking `sqlite3.connect()`.
- In `review/db.py`:
  - Enforce identical path validation in `init_review_db()`, `get_db_connection()`, and `ReviewStateStore.__init__()`.
  - Validate that `db_path` is not a mock or mock string representation.
- Disk Hygiene:
  - Clean up and purge all residual `<MagicMock...>` SQLite files (`.db`, `-shm`, `-wal`) from the repository root.
- Test Coverage:
  - Add unit tests verifying that passing `MagicMock` or invalid path representations to `connect()`, `ReviewStateStore()`, and `init_review_db()` raises `TypeError` / `ValueError` and creates zero files on disk.

### 3. ChannelLock Isolation & Fixture Hygiene (`src/core/lock.py`, `tests/unit/`)
- In `src/core/lock.py`:
  - Ensure `ChannelLock` and `acquire_lock` accept optional custom lock paths or base lock directories (`lock_dir` / `lock_file_path`) and respect `YT_LOCK_DIR` / `LOCK_FILE_PATH` environment variables.
  - Ensure reentrancy handling, stale lock cleanup, and descriptor release remain deterministic.
- In test suites (`tests/unit/test_directed_story_safety.py`, `tests/unit/test_channel_lock.py`, etc.):
  - Ensure all tests that exercise locking explicitly isolate locks to `tmp_path` fixtures or mock lock functions, preventing cross-test flock collisions.

---

## Impact

### Affected Areas
| Component / File | Impact Level | Description |
|---|---|---|
| `docs/ARQUITECTURA.md` | LOW | Expresses visual invariants positively with `wgpu-py`, `Lavapipe`, `resvg-py`, and `libass`. Fixes `test_f15`. |
| `src/core/repository.py` | MEDIUM | Adds strict `db_path` validation in `connect()` preventing mock-path SQLite file creation. |
| `review/db.py` | MEDIUM | Adds strict `db_path` validation in `ReviewStateStore`, `init_review_db`, and `get_db_connection`. |
| `src/core/lock.py` | LOW | Improves lock directory configurability and test fixture isolation. |
| `tests/unit/` | LOW | Tests for path validation and lock isolation; cleans stray mock artifacts. |

### Risk Assessment
- **Risk 1 (Path Validation False Positives)**: Valid `Path` objects, URI paths (e.g. `file:...`), or in-memory SQLite paths (`:memory:`) being rejected.
  - *Mitigation*: Validation logic explicitly allows `:memory:`, standard `Path`, `os.PathLike`, and non-mock strings, while strictly checking `not isinstance(x, unittest.mock.Base)` and ensuring strings do not match `<(Magic)?Mock`.
- **Risk 2 (Lock Path Regression)**: Production runtime resolving wrong lock file location.
  - *Mitigation*: Retain exact default fallback to `LOCK_FILE_PATH` in `src.config` when no explicit directory or override is provided.

### Rollback Plan
1. Revert modifications in `docs/ARQUITECTURA.md`, `src/core/repository.py`, `review/db.py`, and `src/core/lock.py` via Git.
2. No database migrations or schema alterations are required.
