# Proposal: Streamline Integrity Verification Engine & Guardrail Architecture

## Intent

The repository's integrity and governance validation currently relies on `scripts/verify_integrity.sh`, a 192-line Bash script that serves as the mandatory pre-run and 25-commit kill switch. While its governance policies are critical to repository health, the current implementation suffers from significant architectural defects:

1. **High Latency & Process Churn**:
   A single run of `scripts/verify_integrity.sh` takes 8–11 seconds. It repeatedly boots the Python runtime in separate subprocesses:
   - Subprocess 1: `pytest --collect-only -q` (scans all test files and loads heavy test plugins like `anyio`, `xdist`, `timeout`, `asyncio`).
   - Subprocess 2: `pytest tests/unit/test_anti_regression_guardrails.py -q` (re-initializes pytest from scratch to run guardrails).
   - Subprocess 3: `python3 scripts/verify_mcp_sync.py` (boots Python again to check MCP parity).

2. **Crude Regex Text-Matching (False Positives & False Negatives)**:
   The script relies on `grep -rn` to inspect code files. This text-based heuristic frequently flags false positives on comments, docstrings, and historical notes (e.g. mentioning `playwright` or `src.rendering` in documentation), while remaining blind to dynamic or aliased Python imports.

3. **Triplicated Governance Rules**:
   Repository invariants are duplicated across three independent implementations:
   - `.githooks/pre-commit` (Bash string filters).
   - `scripts/verify_integrity.sh` (Bash regex grep).
   - `tests/unit/test_anti_regression_guardrails.py` (Python AST parsing).
   Whenever a policy is added or modified, developers must update all three files in lockstep, creating maintenance overhead and drift risk.

4. **Brittle String-Scraping in MCP Tool**:
   The MCP server tool `src/mcp/tools/verify_integrity.py` executes the Bash script and parses human-oriented stdout by matching literal emoji lines (`✅ [PASS]`, `❌ [FAIL]`). If formatting, wording, or locale changes slightly, the MCP tool fails silently or misreports status.

This proposal refactors the integrity verification architecture into a centralized, high-performance Python engine (`src/verification/guardrails.py` and `scripts/verify_integrity.py`) executing all invariant checks in a single process in under 1 second. It supports bimodal output (rich CLI formatting and `--json` for MCP/CI), introduces `--staged` mode for instant (< 50ms) pre-commit validation, and preserves `scripts/verify_integrity.sh` as a 1-line shim for complete backward compatibility.

---

## Scope

### In Scope
- **Centralized Guardrail Library (`src/verification/guardrails.py`)**:
  - Implement a dedicated Python module encapsulating all repository invariants:
    - Git worktree hygiene (detecting prunable and unlinked worktrees).
    - Architecture blueprint hygiene (blocking resurrection of `docs/architecture/0*.md`).
    - Subsystem isolation (blocking legacy `src/rendering`, `src/compositing`, `src/export` directories and imports via Python AST).
    - Zero-Browser policy (blocking Playwright outside `src/youtube/uploader.py` via Python AST).
    - Zero-Procedural-Math policy (blocking `*.wgsl`, `src/media/_legacy/`, `proc_engine.py`, `wgpu`, `pygfx`).
    - Git hooks configuration (`core.hooksPath` validation).
    - Anti-bloat policy (detecting minified JavaScript bundles, vendored skills, or third-party bloat).
    - Agent homedir and secret hygiene (local-only agent dirs, secret-shaped files like unquoted `.env` and `cookies.json`).
    - Test suite collectability (in-process pytest collection check).
    - In-process MCP synchronization (invoking `verify_mcp_sync` directly without subprocess overhead).
- **Unified High-Performance Runner (`scripts/verify_integrity.py`)**:
  - Provide a single-process entrypoint executing all checks in < 1s.
  - Implement `--fast` mode (skips heavy pytest collection).
  - Implement `--staged` mode (filters AST and path checks strictly to `git diff --cached --name-only` files in < 50ms).
  - Implement `--json` mode (emits structured schema for MCP tools, CI pipelines, and automated reporting).
- **Backward Compatibility Shim (`scripts/verify_integrity.sh`)**:
  - Replace the 192-line Bash script with a thin 1-line delegation shim:
    `exec python3 "${BASH_SOURCE[0]%/*}/verify_integrity.py" "$@"`
  - Preserves exact exit codes, CLI arguments, and backward compatibility with `AGENTS.md`, system instructions, and operator workflows.
- **Git Pre-Commit Hook Streamlining (`.githooks/pre-commit`)**:
  - Refactor `.githooks/pre-commit` to invoke `python3 scripts/verify_integrity.py --staged` directly, eliminating duplicated Bash grep logic and reducing hook latency to < 50ms.
- **Structured MCP Tool Integration (`src/mcp/tools/verify_integrity.py`)**:
  - Update the MCP tool to invoke `scripts/verify_integrity.py --json` (or import `src.verification.guardrails` directly) and consume structured JSON dictionaries, eliminating emoji string scraping.
- **Test Suite Alignment (`tests/unit/test_anti_regression_guardrails.py`)**:
  - Verify that the test suite validates `src/verification/guardrails.py` and confirms all REG-01 through REG-14 invariants pass.

### Out of Scope
- Altering media generation DSP, FFmpeg video encoding, or audio mastering logic.
- Relaxing or changing any existing governance rule or security policy (the rules remain identical in effect, executed via AST and structured Python).
- Modifying remote CI workflows beyond supporting the new `--json` flag.

---

## Capabilities

### New Capabilities
- `unified-integrity-engine`: Centralized in-process Python verification engine (`src/verification/guardrails.py` and `scripts/verify_integrity.py`) providing sub-second full repository invariant auditing, staged file inspection mode for pre-commit hooks, and bimodal human CLI and structured JSON output for MCP and CI consumers.

### Modified Capabilities
None

---

## Approach

1. **Construct `src/verification/guardrails.py`**:
   Build modular check functions using standard library `ast`, `pathlib`, `json`, and `subprocess`:
   - `check_worktrees()`: Executes `git worktree list --porcelain` and checks for stale or unlinked directories.
   - `check_architecture_docs(paths=None)`: Checks for forbidden `docs/architecture/0*.md` files.
   - `check_legacy_subsystems(paths=None)`: Validates that retired directories do not exist and uses `ast.NodeVisitor` to detect forbidden `src.rendering`, `src.compositing`, `src.export` imports.
   - `check_zero_browser_imports(paths=None)`: Uses AST parsing on Python files outside `src/youtube/` to flag Playwright imports.
   - `check_zero_procedural_math(paths=None)`: Checks for `*.wgsl` files, legacy procedural directories, and `wgpu`/`pygfx` imports via AST.
   - `check_git_hooks()`: Validates `core.hooksPath == .githooks` and executable permissions.
   - `check_anti_bloat(paths=None)`: Checks for `.min.js` files, `.github/skills`, and `assets/vendor`.
   - `check_agent_homes_and_secrets(paths=None)`: Enforces that agent directories (`.claude`, `.gemini`, `.cursor`, `.hermes`, etc.) and secret files (`.env`, `cookies.json`) are not committed.
   - `check_test_collectability()`: Executes an in-process or lightweight collect-only check.
   - `check_mcp_sync()`: Directly imports `verify_mcp_sync` from `scripts.verify_mcp_sync` and executes the verification in-process without spawning a child Python interpreter.

2. **Implement `scripts/verify_integrity.py`**:
   - Provide an argument parser supporting `--fast`, `--staged`, and `--json`.
   - In standard CLI mode, output formatted terminal status lines with emojis (`✅ [PASS]`, `❌ [FAIL]`) matching existing conventions.
   - In `--json` mode, output a structured JSON document:
     ```json
     {
       "healthy": true,
       "status": "HEALTHY",
       "exit_code": 0,
       "checks_passed": [...],
       "checks_failed": [...],
       "commit_count": 325,
       "duration_ms": 320
     }
     ```
   - In `--staged` mode, query `git diff --cached --name-only --diff-filter=ACM` and pass staged file paths to path-specific check functions, terminating in < 50ms.

3. **Convert `scripts/verify_integrity.sh` to Shim**:
   - Replace `scripts/verify_integrity.sh` with:
     ```bash
     #!/usr/bin/env bash
     set -euo pipefail
     SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
     PYTHON_BIN="python3"
     if [ -x "$SCRIPT_DIR/../.venv/bin/python3" ]; then
         PYTHON_BIN="$SCRIPT_DIR/../.venv/bin/python3"
     fi
     exec "$PYTHON_BIN" "$SCRIPT_DIR/verify_integrity.py" "$@"
     ```

4. **Update `.githooks/pre-commit`**:
   - Delegate validation to `scripts/verify_integrity.py --staged`, removing redundant regex text scanning.

5. **Update `src/mcp/tools/verify_integrity.py`**:
   - Invoke `scripts/verify_integrity.py --json` and parse the JSON response directly, or import `src.verification.guardrails` directly, returning structured status to MCP clients.

6. **Validate Behavioral Parity**:
   - Run `pytest tests/unit/test_anti_regression_guardrails.py`.
   - Verify that running `./scripts/verify_integrity.sh` produces identical terminal output and passes with code 0.

---

## Media Processing Performance Impact

- **Zero Video DSP Degradation**: Media rendering hot-paths remain 100% native FFmpeg (stream-copy `-c:v copy`, EBU R128 audio normalization, and libass subtitle rasterization). No media processing code is touched.
- **10x Faster Verification Cadence**: Full integrity verification runtime drops from ~11 seconds to < 1 second. Pre-commit hook runtime drops from ~800ms to < 50ms.
- **Subprocess & Memory Reduction**: Eliminating 3 redundant Python interpreter boots saves ~150MB of transient RAM churn and prevents process fork spikes during agent operations and git commits.

---

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/verification/guardrails.py` | New | Centralized SSOT for repository invariant AST checks and hygiene validators |
| `scripts/verify_integrity.py` | New | High-performance single-process verification engine with bimodal CLI and JSON output |
| `scripts/verify_integrity.sh` | Modified | Thin backward-compatible 1-line shim delegating to `verify_integrity.py` |
| `.githooks/pre-commit` | Modified | Streamlined to invoke `verify_integrity.py --staged` (< 50ms execution) |
| `src/mcp/tools/verify_integrity.py` | Modified | Updated to consume structured JSON directly from the verification engine |
| `tests/unit/test_anti_regression_guardrails.py` | Modified | Synchronized to test `src/verification/guardrails.py` and behavioral contracts |
| `docs/MCP.md` | Modified | Document structured JSON output format and options for `verify_integrity` |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Differences in AST import detection vs. old regex grep | Low | AST parsing is strictly more accurate than regex, eliminating false positives on comments while accurately catching all import statements. |
| Missing virtualenv Python when executing shim | Low | Shim checks for `.venv/bin/python3` and falls back to `python3` in `PATH`. |
| MCP tool breaking due to output change | Low | `verify_integrity.py` supports standard human CLI output identical to the old script, while `--json` provides a stable schema for MCP. |
| Pre-commit hook latency regression | Low | `--staged` inspects only git-cached filenames and changed files, executing in < 50ms. |

---

## Rollback Plan

If regressions occur:
1. Revert commits on the branch cleanly via `git revert`.
2. The legacy `scripts/verify_integrity.sh` and `.githooks/pre-commit` Bash implementations can be restored instantly from git history.
3. Because no database schemas, media assets, or build containers are modified, rollback is instantaneous and risk-free.
4. Verify baseline with `.venv/bin/pytest tests/unit/test_anti_regression_guardrails.py`.

---

## Dependencies

- Python 3.12+ standard library (`ast`, `sys`, `pathlib`, `json`, `subprocess`).
- Existing workspace dependencies (`pytest`, `verify_mcp_sync.py`).

---

## Success Criteria

- [ ] `src/verification/guardrails.py` provides centralized, AST-based implementations for all repository invariants.
- [ ] `python3 scripts/verify_integrity.py` runs all checks in < 1.0 second on local workstations.
- [ ] `python3 scripts/verify_integrity.py --json` outputs compliant structured JSON with exit code 0 on healthy repos.
- [ ] `python3 scripts/verify_integrity.py --staged` executes in < 50ms.
- [ ] `./scripts/verify_integrity.sh` acts as a transparent shim, exiting 0 when healthy and exiting 1 on violations.
- [ ] `.githooks/pre-commit` successfully rejects forbidden commits via `--staged` mode.
- [ ] `src/mcp/tools/verify_integrity.py` consumes structured JSON without scraping stdout emojis.
- [ ] `pytest tests/unit/test_anti_regression_guardrails.py` passes 100%.
- [ ] `scripts/verify_mcp_sync.py` verifies 100% parity across tools, resources, and docs.
