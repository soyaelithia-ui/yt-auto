# Tasks: Streamline Integrity Verification Engine & Guardrail Architecture

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 650–850 lines (net ~+200 lines, replacing ~320 lines of Bash with Python) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR (size-exception: cohesive migration of legacy shell scripts to single-process Python engine) |
| Delivery strategy | exception-ok |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | SSOT Guardrails Core Module (centralize all repository invariant checks and AST scanners into `src/verification/guardrails.py`) | PR 1 (single-pr / size-exception) | `.venv/bin/pytest tests/unit/test_anti_regression_guardrails.py` | `python -c "from src.verification.guardrails import run_integrity_audit; print(run_integrity_audit('.'))"` | `src/verification/` |
| 2 | High-Performance Runner & Staged Mode (build `scripts/verify_integrity.py` with `--staged`, `--fast`, and `--json` support) | PR 1 (single-pr / size-exception) | `python3 scripts/verify_integrity.py --fast && python3 scripts/verify_integrity.py --json` | `python3 scripts/verify_integrity.py --staged` | `scripts/verify_integrity.py` |
| 3 | Backward-Compatible Shell Shim & Pre-Commit Hook (replace `scripts/verify_integrity.sh` with 1-line shim and streamline `.githooks/pre-commit`) | PR 1 (single-pr / size-exception) | `./scripts/verify_integrity.sh --fast` | `.githooks/pre-commit` | `scripts/verify_integrity.sh`, `.githooks/pre-commit` |
| 4 | Structured MCP Tool Integration (update `src/mcp/tools/verify_integrity.py` to consume structured JSON and document in `docs/MCP.md`) | PR 1 (single-pr / size-exception) | `python3 scripts/verify_mcp_sync.py` | `python -m src.mcp` | `src/mcp/tools/verify_integrity.py`, `docs/MCP.md` |
| 5 | Verification & Governance Certification (synchronize `tests/unit/test_anti_regression_guardrails.py` and certify sub-second execution) | PR 1 (single-pr / size-exception) | `./scripts/verify_integrity.sh` | `.venv/bin/pytest tests/unit/test_anti_regression_guardrails.py` | `tests/unit/test_anti_regression_guardrails.py` |

---

## Phase 1: SSOT Guardrails Core Module (`src/verification/guardrails.py`)

- [x] 1.1 (RED Test) Add unit tests in `tests/unit/test_anti_regression_guardrails.py` for `src/verification/guardrails.py` (read-only) `ImportScanner` and `scan_module_imports`, verifying detection of multiline and aliased imports while ignoring comments and docstrings.
- [x] 1.2 Create `src/verification/__init__.py` exporting core data models (`CheckResult`, `IntegrityReport`) and invariant validation functions.
- [x] 1.3 Create `src/verification/guardrails.py` with `CheckResult` and `IntegrityReport` dataclasses and AST inspection utilities (`ImportScanner`, `scan_module_imports`).
- [x] 1.4 Implement Git worktree hygiene (`check_worktrees`) and architecture blueprint hygiene (`check_architecture_docs`) in `src/verification/guardrails.py`, blocking stale worktrees and `docs/architecture/0*.md` (read-only) files.
- [x] 1.5 Implement subsystem isolation (`check_legacy_subsystems`), Zero-Browser policy (`check_zero_browser_policy`), and Zero-Procedural-Math policy (`check_zero_procedural_math`) in `src/verification/guardrails.py` using AST parsing.
- [x] 1.6 Implement Git hooks hygiene (`check_git_hooks`), anti-bloat validation (`check_anti_bloat`), and agent homedir/secrets hygiene (`check_agent_homes_and_secrets`) in `src/verification/guardrails.py`.
- [x] 1.7 Implement test collectability (`check_test_collectability`) and in-process MCP synchronization (`check_mcp_sync`) in `src/verification/guardrails.py`, importing `scripts/verify_mcp_sync.py` (read-only) directly without spawning child Python processes.
- [x] 1.8 Implement `run_integrity_audit(repo_root, staged, fast, staged_paths)` in `src/verification/guardrails.py` consolidating all check executions into a typed `IntegrityReport`.

---

## Phase 2: High-Performance Runner & Staged Mode (`scripts/verify_integrity.py`)

- [x] 2.1 (RED Test) Add unit test in `tests/unit/test_anti_regression_guardrails.py` verifying `scripts/verify_integrity.py` (read-only) safely handles shell metacharacters (`;`, `&&`, `|`) in arguments using `shell=False` (Threat Matrix: subprocess execution boundary).
- [x] 2.2 (RED Test) Add unit test in `tests/unit/test_anti_regression_guardrails.py` verifying `scripts/verify_integrity.py` (read-only) `--staged` mode parses git-cached paths with spaces or non-ASCII characters without crashing (Threat Matrix: git cached path parsing boundary).
- [x] 2.3 (RED Test) Add unit test in `tests/unit/test_anti_regression_guardrails.py` verifying `scripts/verify_integrity.py` (read-only) `--staged` mode with an empty Git index exits immediately with code 0 in < 5ms (Threat Matrix: commit state boundary).
- [x] 2.4 Create `scripts/verify_integrity.py` with `argparse` CLI supporting `--fast`, `--staged`, and `--json` flags.
- [x] 2.5 Implement `--staged` mode in `scripts/verify_integrity.py` querying `git diff --cached --name-only -z --diff-filter=ACM` and filtering path/AST checks to cached files in < 50ms.
- [x] 2.6 Implement bimodal output in `scripts/verify_integrity.py`: ANSI colorized terminal indicators (`✅ [PASS]`, `❌ [FAIL]`) by default, and structured JSON output matching `IntegrityReport` schema when invoked with `--json`.
- [x] 2.7 Ensure robust exit code propagation in `scripts/verify_integrity.py` (0 for clean audit, 1 for invariant violations) and resolve `REPO_ROOT` dynamically from script path.

---

## Phase 3: Backward-Compatible Shell Shim & Pre-Commit Hook (`scripts/verify_integrity.sh`, `.githooks/pre-commit`)

- [x] 3.1 (RED Test) Add integration test in `tests/unit/test_anti_regression_guardrails.py` verifying `scripts/verify_integrity.sh` (read-only) forwards arguments with spaces (`"arg with spaces"`) to Python intact without word splitting (Threat Matrix: shell script arguments boundary).
- [x] 3.2 (RED Test) Add integration test in `tests/unit/test_anti_regression_guardrails.py` asserting that intentional invariant violations cause both `scripts/verify_integrity.py` (read-only) and `scripts/verify_integrity.sh` (read-only) to exit with status code 1 (Threat Matrix: exit code propagation boundary).
- [x] 3.3 Replace `scripts/verify_integrity.sh` with a 1-line Bash delegation shim: auto-detecting `.venv/bin/python3`, invoking `scripts/verify_integrity.py` (read-only) with `exec`, and preserving all arguments (`"$@"`).
- [x] 3.4 Ensure `chmod +x` executable permissions on `scripts/verify_integrity.sh` and `scripts/verify_integrity.py`.
- [x] 3.5 Streamline `.githooks/pre-commit` to invoke `scripts/verify_integrity.py` (read-only) with `--staged`, eliminating duplicated Bash regexes and ensuring pre-commit gating executes in < 50ms.

---

## Phase 4: Structured MCP Tool Integration (`src/mcp/tools/verify_integrity.py`, `docs/MCP.md`)

- [x] 4.1 (RED Test) Add unit test in `tests/unit/test_anti_regression_guardrails.py` for `src/mcp/tools/verify_integrity.py` (read-only), verifying that the tool parses structured JSON payloads and returns structured dictionaries without scraping emoji strings.
- [x] 4.2 Update `src/mcp/tools/verify_integrity.py` to invoke `scripts/verify_integrity.py` (read-only) with `--json`, consuming structured JSON output and populating `checks_passed`, `checks_failed`, `commit_count`, and `duration_ms`.
- [x] 4.3 Update `docs/MCP.md` to document the structured JSON schema, options (`fast`, `fail_closed`), and latency improvements of `verify_integrity`.
- [x] 4.4 Run `scripts/verify_mcp_sync.py` (read-only) to confirm 100% bidirectional parity between MCP registrations, documentation, and client configs.

---

## Phase 5: Verification & Governance Certification

- [x] 5.1 Update `tests/unit/test_anti_regression_guardrails.py` to import and test `src/verification/guardrails.py` (read-only) directly, affirming REG-01 through REG-14 invariants.
- [x] 5.2 Execute `.venv/bin/pytest tests/unit/test_anti_regression_guardrails.py` (read-only) to confirm 100% test pass rate for all guardrail and threat-matrix assertions.
- [x] 5.3 Execute `scripts/verify_integrity.sh` (read-only) on the repository, verifying all checks pass with exit code 0 in < 1.0 second wall-clock time.
- [x] 5.4 Test Git pre-commit hook execution via `.githooks/pre-commit` (read-only) with clean staged changes to confirm sub-50ms execution.
