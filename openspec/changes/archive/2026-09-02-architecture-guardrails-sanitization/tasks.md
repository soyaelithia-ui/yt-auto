# Tasks: Architecture Guardrails, Path Validation & Test Isolation Sanitization

This document details the actionable, hierarchically numbered engineering tasks required to implement the architecture guardrails, database path validation, and lock isolation sanitization defined in `openspec/changes/architecture-guardrails-sanitization/`.

---

## Phase 1: Setup & Tests (TDD First)

- [x] **1.1 Add unit tests for database path validation and mock rejection**
  - [x] 1.1.1 Implement unit tests in `tests/unit/test_repository.py` (or dedicated `tests/unit/test_repository_path_validation.py`) asserting `validate_db_path()` accepts valid `str`, `pathlib.Path`, `os.PathLike`, and `":memory:"`.
  - [x] 1.1.2 Assert `validate_db_path()` raises `TypeError` when passed `unittest.mock.MagicMock`, `unittest.mock.Mock`, or `None`.
  - [x] 1.1.3 Assert `validate_db_path()` raises `ValueError` when passed empty string, strings starting with `"<MagicMock"` / `"<Mock"`, or strings containing `"MagicMock name="`.
  - [x] 1.1.4 Assert `src.core.repository.connect(MagicMock())` raises `TypeError` and creates zero files or directories in the project root.
  - [x] 1.1.5 Assert `src.core.repository.connect("<MagicMock name='mock.db_path' ...>")` raises `ValueError` and creates zero files on disk.
  - [x] 1.1.6 Add unit tests in `tests/unit/test_review_db.py` asserting `ReviewStateStore(MagicMock())`, `init_review_db(MagicMock())`, and `get_db_connection(MagicMock())` raise `TypeError`.
  - [x] 1.1.7 Add unit tests in `tests/unit/test_review_db.py` asserting `ReviewStateStore("<MagicMock...>")`, `init_review_db("<MagicMock...>")`, and `get_db_connection("<MagicMock...>")` raise `ValueError` with zero disk side-effects.

- [x] **1.2 Add unit tests for `ChannelLock` directory isolation and `YT_LOCK_DIR` precedence**
  - [x] 1.2.1 Add unit tests in `tests/unit/test_channel_lock.py` verifying `ChannelLock(channel_name="global", lock_dir=tmp_path)` resolves path to `<tmp_path>/youtube_automation.lock`.
  - [x] 1.2.2 Verify `ChannelLock(channel_name="aelithia", lock_dir=tmp_path)` resolves path to `<tmp_path>/youtube_automation.lock.aelithia`.
  - [x] 1.2.3 Verify `ChannelLock(channel_name="moku", lock_file_path=tmp_path / "custom.lock")` resolves path to `<tmp_path>/custom.lock.moku`.
  - [x] 1.2.4 Verify `YT_LOCK_DIR` environment variable override: setting `os.environ["YT_LOCK_DIR"]` resolves lock file inside the configured environment directory.
  - [x] 1.2.5 Test concurrent lock isolation: verify two `ChannelLock` instances targeting different `lock_dir` directories acquire simultaneously without `ChannelLockError` collisions.
  - [x] 1.2.6 Test lock lifecycle: verify clean acquisition, context manager entry, release (`LOCK_UN`), and PID-verified file unlinking within `tmp_path`.
  - [x] 1.2.7 Test legacy `acquire_lock(channel_name, lock_dir=..., lock_file_path=...)` wrapper kwargs propagation.

- [x] **1.3 Clean up stray `<MagicMock...>` SQLite files from workspace root**
  - [x] 1.3.1 Purge all residual `<MagicMock*>` database, `-shm`, and `-wal` files from the repository root directory.
  - [x] 1.3.2 Confirm with `git status --porcelain` that no untracked mock database artifacts remain.

---

## Phase 2: Implementation

- [x] **2.1 Implement `validate_db_path` and integrate across `src/core/repository.py`**
  - [x] 2.1.1 Implement `validate_db_path(db_path: Any) -> Path | str` helper:
    - Reject `None` with `TypeError("db_path cannot be None")`.
    - Reject `unittest.mock.Base` or mock module instances with `TypeError("Mock objects are not valid database paths")`.
    - Reject non-path instances (`int`, `list`, `dict`) with `TypeError("db_path must be str, Path, or os.PathLike")`.
    - Strip and check stringified path: reject empty string with `ValueError("db_path cannot be empty string")`.
    - Reject strings starting with `"<MagicMock"` / `"<Mock"` or containing `"MagicMock name="` with `ValueError("Stringified mock representation detected in db_path")`.
    - Return `":memory:"` if input equals `":memory:"` or starts with `"file::memory:"`.
    - Return `Path(db_path)` for valid filesystem paths.
  - [x] 2.1.2 Integrate `validate_db_path` into `src/core/repository.py:connect()` before `path.parent.mkdir()` or `sqlite3.connect()`.
  - [x] 2.1.3 Integrate `validate_db_path` into `src/core/repository.py:wal_checkpoint_passive()`.

- [x] **2.2 Integrate `validate_db_path` into `review/db.py`**
  - [x] 2.2.1 Import or expose `validate_db_path` in `review/db.py`.
  - [x] 2.2.2 Integrate `validate_db_path` into `review/db.py:init_review_db()` before directory creation or database connection.
  - [x] 2.2.3 Integrate `validate_db_path` into `review/db.py:get_db_connection()`.
  - [x] 2.2.4 Integrate `validate_db_path` into `review/db.py:ReviewStateStore.__init__()` when resolving `self.db_path`.

- [x] **2.3 Update `src/core/lock.py` for directory isolation and `YT_LOCK_DIR` precedence**
  - [x] 2.3.1 Update `ChannelLock.__init__()` signature to accept `lock_file_path: Optional[str | Path] = None` and `lock_dir: Optional[str | Path] = None`.
  - [x] 2.3.2 Implement path resolution cascade:
    1. Explicit `lock_file_path`
    2. Explicit `lock_dir`
    3. `os.environ["YT_LOCK_DIR"]`
    4. Default `LOCK_FILE_PATH` / `_get_default_lock_path()`
  - [x] 2.3.3 Update `acquire_lock()` signature to accept optional `lock_dir` and `lock_file_path` arguments and pass them to `ChannelLock`.

- [x] **2.4 Update `docs/ARQUITECTURA.md` Section 9 to express positive native visual principles**
  - [x] 2.4.1 Purge all legacy browser engine names (e.g. `Playwright`, `Chromium`) from `docs/ARQUITECTURA.md`.
  - [x] 2.4.2 Reformulate Section 9 positively around native technologies:
    - **Native Procedural Rendering**: 100% native GPU-accelerated graphics pipeline using `wgpu-py` with WGSL fragment shaders, supported by CPU fallback via Mesa Lavapipe.
    - **Vectorized Typography & Dynamic Overlays**: High-performance SVG rasterization via `resvg-py` and zero-copy overlay compositing.
    - **Atomic Native Subtitles**: Direct `.ass` generation with karaoke timings (`{\kf}`) and mobile UI safe margin enforcement ($\ge 240\text{px}$) rendered natively via `libass` / FFmpeg filter chains.
    - **Unified Single-Pass Transcoding**: Atomic FFmpeg encoding (`-filter_complex`) with asynchronous `stderr` stream draining.
    - **Deterministic Memory Compositor**: Contiguous pre-allocated NumPy array buffers ($\le 140\text{ MB RAM}$) preventing memory leaks.

---

## Phase 3: Verification & Anti-Regression

- [x] **3.1 Verify documentation synchronization test passes 100%**
  - [x] 3.1.1 Run `pytest tests/e2e/test_tier1_features.py -k test_f15_docs_arquitectura_synchronized -v`.
  - [x] 3.1.2 Verify zero assertion errors and clean pass.

- [x] **3.2 Verify AST anti-regression guardrails (REG-01 to REG-09) pass 100%**
  - [x] 3.2.1 Run `pytest tests/unit/test_anti_regression_guardrails.py -v`.
  - [x] 3.2.2 Ensure all 9 AST guardrails pass without violations.

- [x] **3.3 Run full pytest suite across `tests/unit`, `tests/integration`, `tests/e2e`**
  - [x] 3.3.1 Execute complete test suite: `pytest tests/unit tests/integration tests/e2e -v`.
  - [x] 3.3.2 Confirm zero test regressions across all test suites.
  - [x] 3.3.3 Confirm zero `<MagicMock*>` files exist in workspace root after running tests (`git status --porcelain`).

