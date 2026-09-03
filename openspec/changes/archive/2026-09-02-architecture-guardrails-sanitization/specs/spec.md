# Specification: Architecture Guardrails, Path Validation & Test Isolation Sanitization

## 1. Overview & Context

This specification defines the architectural invariants, path validation contracts, and test isolation mechanisms for `yt-auto`. It establishes positive architecture documentation standards, eliminates unintended mock filesystem artifact creation in database layers, and enables deterministic lock isolation for multi-process and concurrent test execution.

---

## 2. Requirements & Scenarios

### Requirement 1: Positive Architecture Documentation Invariants

The primary architecture specification (`docs/ARQUITECTURA.md`) MUST document the video rendering and processing pipeline positively through its native, GPU-accelerated and compiled dependencies. 

1. `docs/ARQUITECTURA.md` MUST explicitly document:
   - 100% native WebGPU procedural rendering (`wgpu-py`) with WGSL fragment shaders and Mesa Lavapipe software rasterizer fallback.
   - Vectorized typography and dynamic SVG overlays via `resvg-py`.
   - C-level atomic subtitle rendering via `libass` and single-pass FFmpeg filter complex pipelines.
   - Deterministic memory management using pre-allocated contiguous NumPy array buffers ($\le 140\text{ MB RAM}$).
2. `docs/ARQUITECTURA.md` MUST NOT contain legacy browser tool tokens or names (including, but not limited to, `playwright`, `puppeteer`, `selenium`, or browser-driven render engines).
3. Automated AST-based anti-regression guardrails (`REG-01` through `REG-09` in `tests/unit/test_anti_regression_guardrails.py`) MUST remain actively enforced across all codebase modules to prevent reintroduction of deprecated browser dependencies.
4. The documentation synchronization test `test_f15_docs_arquitectura_synchronized` in `tests/e2e/test_tier1_features.py` MUST pass without assertion errors.

#### Scenario 1.1: Architecture documentation verification (Happy Path)
- **Given** the technical documentation file `docs/ARQUITECTURA.md`
- **When** the documentation content is evaluated by `test_f15_docs_arquitectura_synchronized`
- **Then** the content MUST contain references to native procedural rendering (`wgpu` or `procedural`)
- **And** the content MUST NOT contain any case-insensitive occurrence of `playwright`.

#### Scenario 1.2: Positive formulation of rendering invariants (Documentation Standard)
- **Given** Section 9 of `docs/ARQUITECTURA.md`
- **When** reviewing the anti-regression and visual compositor architectural policies
- **Then** all architectural invariants MUST be framed around native WebGPU (`wgpu-py`), Mesa Lavapipe, `resvg-py`, and `libass` capabilities without relying on negative legacy browser terminology.

#### Scenario 1.3: Anti-regression AST guardrail enforcement (Code Analysis)
- **Given** the test suite `tests/unit/test_anti_regression_guardrails.py`
- **When** AST scanners inspect all source files in `src/`, `review/`, and `config/`
- **Then** zero imports, references, or sub-processes invoking legacy browser engines MUST be detected across `REG-01` through `REG-09`.

---

### Requirement 2: Database Path Validation & Mock Sanitization

All database connection and initialization entry points in `src/core/repository.py` and `review/db.py` MUST strictly validate database path arguments before performing any filesystem operations (such as directory creation or SQLite file opening).

1. The functions `src/core/repository.py:connect()`, `review/db.py:init_review_db()`, `review/db.py:get_db_connection()`, and the constructor `review/db.py:ReviewStateStore.__init__()` MUST validate the `db_path` argument:
   - Valid inputs MUST be an instance of `str`, `pathlib.Path`, or `os.PathLike[str]` representing a filesystem path, or the special SQLite identifier `":memory:"` (or SQLite URI).
   - Mock objects (instances of `unittest.mock.Base`, `unittest.mock.Mock`, `unittest.mock.MagicMock`, `unittest.mock.NonCallableMock`, or any object belonging to `unittest.mock`) MUST be rejected immediately with a `TypeError`.
   - String values matching or containing mock string representations (such as strings starting with `"<MagicMock"`, `"<Mock"`, or containing `MagicMock name=`) MUST be rejected immediately with a `ValueError`.
   - `None` or non-path types (integers, lists, dicts) MUST be rejected with a `TypeError` (unless default path resolution applies).
2. Path validation MUST execute prior to invoking `os.makedirs()`, `pathlib.Path.mkdir()`, or `sqlite3.connect()`.
3. Under no circumstances SHALL invoking database functions with mock objects or mock string representations cause SQLite database files (e.g. `<MagicMock...>`, `<MagicMock...>-wal`, `<MagicMock...>-shm`) to be written to the current working directory or disk.

#### Scenario 2.1: Valid path connections (Happy Path)
- **Given** a valid filesystem path string (e.g. `"data/shorts_queue.db"`) or `pathlib.Path` instance
- **When** `connect(db_path)` or `get_db_connection(db_path)` is invoked
- **Then** a valid `sqlite3.Connection` context manager MUST be yielded
- **And** PRAGMA configurations (`busy_timeout`, `foreign_keys`, `journal_mode=WAL`) MUST be applied.

#### Scenario 2.2: In-memory SQLite connection
- **Given** the database path string `":memory:"` or a valid SQLite memory URI
- **When** `connect(":memory:")` or `get_db_connection(":memory:")` is invoked
- **Then** an in-memory SQLite connection MUST be yielded without attempting filesystem directory creation.

#### Scenario 2.3: Rejection of Mock objects in repository `connect()` (Type Error)
- **Given** a `unittest.mock.MagicMock` or `unittest.mock.Mock` instance passed as `db_path`
- **When** `src.core.repository.connect(mock_obj)` is invoked
- **Then** the function MUST raise a `TypeError` with an informative message indicating that mock objects are not valid database paths
- **And** NO directories or files MUST be created on disk.

#### Scenario 2.4: Rejection of stringified Mock representations in repository `connect()` (Value Error)
- **Given** a string representing a stringified mock (e.g. `"<MagicMock name='mock.db_path' id='1400...'>"` or `"<Mock id='123'>"` )
- **When** `src.core.repository.connect(mock_str)` is invoked
- **Then** the function MUST raise a `ValueError` indicating an invalid database path format
- **And** NO files matching `<MagicMock...>` MUST be written to the project working directory.

#### Scenario 2.5: Rejection of Mock objects and mock strings in `ReviewStateStore` and review db helpers
- **Given** a `MagicMock` instance or string starting with `"<MagicMock"` passed to `ReviewStateStore(db_path=...)`, `init_review_db(db_path)`, or `get_db_connection(db_path)`
- **When** any of these functions or initializers is executed
- **Then** `TypeError` MUST be raised for mock objects and `ValueError` MUST be raised for mock string representations
- **And** NO SQLite database files or parent directories MUST be created for the invalid path.

#### Scenario 2.6: Disk hygiene guarantee (Zero side-effects)
- **Given** a test suite executing repository or review state operations
- **When** test assertions fail, unhandled errors occur, or mock objects are injected into database parameters
- **Then** the root working directory MUST remain free of `<MagicMock*>` files, WAL files, or SHM files.

---

### Requirement 3: ChannelLock Isolation & Environment Configurability

The process locking mechanism in `src/core/lock.py` MUST support deterministic isolation across independent test runs, multi-process workers, and parallel test runners (such as `pytest -n`).

1. `ChannelLock.__init__()` and `acquire_lock()` MUST support configurable lock locations:
   - Accept an optional `lock_dir: str | Path | None` parameter, OR an optional `lock_file_path: str | Path | None` parameter.
   - Respect the environment variables `YT_LOCK_DIR` and `LOCK_FILE_PATH` when no explicit directory/path parameter is provided.
   - Fall back to the default `LOCK_FILE_PATH` in `src.config` when neither argument nor environment override is present.
2. When `lock_dir` or `YT_LOCK_DIR` is configured:
   - For channel `"global"` (or default), the lock file path MUST resolve to `<lock_dir>/youtube_automation.lock`.
   - For a specific channel `<channel>`, the lock file path MUST resolve to `<lock_dir>/youtube_automation.lock.<channel>`.
3. Reentrancy and exclusive locking guarantees:
   - `ChannelLock` MUST maintain kernel-level `fcntl.flock` mutual exclusion per unique lock file path.
   - Reentrant acquisition within the same process context MUST succeed without deadlock or double-locking errors.
   - `release()` MUST release `fcntl.flock`, close the file descriptor, and remove the lock file if and only if the current PID matches the recorded holder PID.
4. Test suites exercising channel locking MUST be able to supply `tmp_path` fixtures to ensure total lock isolation between tests without global lock collisions.

#### Scenario 3.1: Default channel lock path resolution (Happy Path)
- **Given** standard runtime environment with no `YT_LOCK_DIR` override
- **When** `ChannelLock(channel_name="moku")` is instantiated without custom paths
- **Then** `lock.path` MUST resolve to the default lock path with suffix `.moku` (e.g. `<project_root>/scratch/youtube_automation.lock.moku`).

#### Scenario 3.2: Explicit `lock_dir` parameter isolation
- **Given** a temporary directory path `tmp_path` (e.g. `/tmp/pytest-123/locks`)
- **When** `ChannelLock(channel_name="aelithia", lock_dir=str(tmp_path))` is instantiated
- **Then** `lock.path` MUST resolve to `/tmp/pytest-123/locks/youtube_automation.lock.aelithia`
- **And** acquiring and releasing the lock MUST operate entirely within `tmp_path`.

#### Scenario 3.3: Environment variable override via `YT_LOCK_DIR`
- **Given** the environment variable `YT_LOCK_DIR` set to `"/tmp/custom_locks"`
- **When** `ChannelLock(channel_name="global")` is instantiated without explicit arguments
- **Then** `lock.path` MUST resolve to `"/tmp/custom_locks/youtube_automation.lock"`.

#### Scenario 3.4: Concurrent lock isolation across separate test directories
- **Given** two separate test processes using isolated `tmp_path` directories `dir_a` and `dir_b`
- **When** Process A acquires `ChannelLock("moku", lock_dir=dir_a)` and Process B acquires `ChannelLock("moku", lock_dir=dir_b)`
- **Then** both locks MUST acquire successfully in parallel without `ChannelLockError` collisions.

#### Scenario 3.5: Clean lock release and deterministic descriptor cleanup
- **Given** an acquired `ChannelLock` instance holding a valid file descriptor
- **When** `lock.release()` is called or the context manager exits
- **Then** `fcntl.flock(LOCK_UN)` MUST be performed, the file descriptor MUST be closed, `_file_handle` MUST be reset to `None`, `is_acquired` MUST return `False`, and the lock file MUST be unlinked if owned by current PID.

---

## 3. Acceptance Criteria & Test Verification

| Requirement ID | Verification Target | Acceptance Test / Method | Expected Result |
|---|---|---|---|
| **AC-REQ-1.1** | Documentation Sync | `pytest tests/e2e/test_tier1_features.py -k test_f15_docs_arquitectura_synchronized` | Passes with 0 legacy browser references and positive WebGPU/libass descriptions. |
| **AC-REQ-1.2** | AST Anti-Regression | `pytest tests/unit/test_anti_regression_guardrails.py` | All AST guardrails `REG-01` to `REG-09` pass cleanly. |
| **AC-REQ-2.1** | Repository Path Validation | `pytest tests/unit/test_repository_path_validation.py` (or repository unit tests) | `connect(MagicMock())` raises `TypeError`; `connect("<MagicMock...>")` raises `ValueError`. |
| **AC-REQ-2.2** | Review DB Path Validation | `pytest tests/unit/test_review_db.py` | `ReviewStateStore(MagicMock())`, `init_review_db`, `get_db_connection` raise `TypeError` / `ValueError`. |
| **AC-REQ-2.3** | Zero Mock Disk Files | `git status --porcelain` and filesystem check | No `<MagicMock...>` files created in root directory during test runs. |
| **AC-REQ-3.1** | Lock Directory Isolation | `pytest tests/unit/test_channel_lock.py` | `ChannelLock(lock_dir=tmp_path)` creates lock files exclusively inside `tmp_path`. |
| **AC-REQ-3.2** | Lock Env Override | `pytest tests/unit/test_channel_lock.py -k test_lock_dir_env` | `YT_LOCK_DIR` takes precedence over default scratch lock directory. |
