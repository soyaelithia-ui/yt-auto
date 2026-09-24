# Unified Integrity Engine Specification

## Purpose

The `unified-integrity-engine` capability defines a centralized, high-performance in-process Python verification engine (`src/verification/guardrails.py` and `scripts/verify_integrity.py`) that enforces all repository governance invariants, architectural boundaries, and hygiene rules. It provides sub-second full repository auditing, rapid staged file inspection (< 50ms) for git pre-commit hooks, bimodal human-readable CLI and machine-readable JSON output formats, and backward-compatible shell delegation shims.

## Requirements

### Requirement: Single-Process Python Integrity Runner
The verification engine SHALL execute all repository invariants in a single Python process in under 1.0 second without spawning redundant Python interpreter subprocesses for individual checks. The engine SHALL evaluate Git worktree hygiene, architecture blueprint hygiene, subsystem isolation, Zero-Browser policy compliance, Zero-Procedural-Math compliance, Git hooks configuration, anti-bloat rules, agent homedir and secret hygiene, test suite collectability, and in-process MCP synchronization.

#### Scenario: Full Repository Verification Passes on Compliant Codebase (Happy Path)
- **Given** a compliant repository state satisfying all architectural invariants
- **When** the verification engine executes full repository verification (`python3 scripts/verify_integrity.py`)
- **Then** all invariant checks SHALL pass
- **And** the engine SHALL terminate with exit code 0
- **And** total execution wall-clock time SHALL be under 1.0 second
- **And** the engine SHALL NOT spawn external Python interpreter subprocesses to evaluate MCP synchronization or guardrail tests.

#### Scenario: Verification Detects and Rejects Forbidden Legacy Imports via AST (Edge Case)
- **Given** a Python source file containing an active import of `src.rendering`, `src.compositing`, `src.export`, or unauthorized `playwright`
- **When** the verification engine executes invariant checks
- **Then** the AST parser SHALL identify the forbidden import with line number and file path
- **And** the check SHALL be marked as failed
- **And** the engine SHALL terminate with exit code 1.

#### Scenario: Fast Mode Execution Bypassing Heavy Pytest Collection (Happy Path)
- **Given** a developer running verification during rapid iteration with `--fast`
- **When** the verification engine executes with the `--fast` flag
- **Then** all static AST, filesystem, and hygiene invariant checks SHALL execute
- **And** the test suite collectability check SHALL be skipped
- **And** total execution wall-clock time SHALL be significantly reduced.

---

### Requirement: Bimodal Output Formats
The verification engine SHALL support human-friendly CLI terminal output by default and machine-readable JSON via the `--json` flag. The default CLI format SHALL present colorized status lines with explicit pass/fail indicators (`✅ [PASS]`, `❌ [FAIL]`). When invoked with `--json`, the engine SHALL emit a single structured JSON object to standard output containing health status, exit code, execution duration, and lists of passed and failed checks.

#### Scenario: CLI Default Formatted Output (Happy Path)
- **Given** standard terminal execution without the `--json` flag
- **When** `scripts/verify_integrity.py` completes execution
- **Then** human-readable lines with status indicators SHALL be written to stdout
- **And** summary metrics including commit count and duration SHALL be displayed.

#### Scenario: Machine-Readable Structured JSON Output (Happy Path)
- **Given** invocation with the `--json` flag on a healthy repository
- **When** `scripts/verify_integrity.py --json` completes execution
- **Then** stdout SHALL contain a valid JSON payload conforming to the verification schema:
  - `healthy`: boolean `true`
  - `status`: `"HEALTHY"`
  - `exit_code`: integer `0`
  - `checks_passed`: array of check identifier strings
  - `checks_failed`: empty array
  - `commit_count`: integer commit count
  - `duration_ms`: integer duration in milliseconds
- **And** the process SHALL exit with code 0.

#### Scenario: JSON Output Reports Structured Failure Details (Edge Case)
- **Given** an invariant violation present in the repository
- **When** `scripts/verify_integrity.py --json` completes execution
- **Then** stdout SHALL contain a valid JSON payload where:
  - `healthy`: boolean `false`
  - `status`: `"UNHEALTHY"`
  - `exit_code`: integer `1`
  - `checks_failed`: non-empty array detailing the failed check names and violation messages
- **And** the process SHALL exit with code 1.

---

### Requirement: Staged File Inspection for Pre-Commit
The verification engine SHALL support a `--staged` mode that inspects only files currently cached in the Git index (`git diff --cached --name-only`). The staged check SHALL evaluate AST imports and path hygiene rules exclusively against the staged changeset in under 50ms, enabling instantaneous pre-commit hook gating.

#### Scenario: Clean Staged Commit Passes Verification (Happy Path)
- **Given** staged changes containing only compliant source code and documentation
- **When** `scripts/verify_integrity.py --staged` executes in a pre-commit hook
- **Then** only the staged files SHALL be evaluated
- **And** the check SHALL pass with exit code 0
- **And** total execution duration SHALL be under 50ms.

#### Scenario: Forbidden File or Import in Staged Changes Rejected (Edge Case)
- **Given** a developer stages a forbidden file (e.g. `docs/architecture/01_legacy.md`, `.min.js`, or a file importing `wgpu`)
- **When** `scripts/verify_integrity.py --staged` executes
- **Then** the engine SHALL flag the violation in the staged changeset
- **And** emit the specific offending filename and violation reason
- **And** terminate with exit code 1, aborting the commit.

#### Scenario: Staged Mode With Empty Git Index (Edge Case)
- **Given** no files are currently staged in Git
- **When** `scripts/verify_integrity.py --staged` executes
- **Then** the engine SHALL detect that zero files are staged
- **And** complete immediately with exit code 0 without raising errors.

---

### Requirement: Backward-Compatible Shell Shim
The legacy script path `scripts/verify_integrity.sh` SHALL act as an executable delegation shim to `scripts/verify_integrity.py`. The shim SHALL forward all command-line arguments, preserve identical exit codes (0 for pass, 1 for fail), and automatically resolve the active Python interpreter preferring `.venv/bin/python3` if available.

#### Scenario: Shell Shim Invocation Without Arguments (Happy Path)
- **Given** existing workflows, CI pipelines, or documentation invoking `./scripts/verify_integrity.sh`
- **When** `./scripts/verify_integrity.sh` is executed with no arguments
- **Then** it SHALL delegate execution to `scripts/verify_integrity.py`
- **And** exit with the exact return code of the Python verification engine
- **And** display standard formatted CLI output.

#### Scenario: Shell Shim Invocation With Arguments (Happy Path)
- **Given** an invocation passing CLI arguments such as `./scripts/verify_integrity.sh --fast` or `./scripts/verify_integrity.sh --json`
- **When** the shell shim executes
- **Then** all arguments SHALL be passed through unchanged to `scripts/verify_integrity.py`
- **And** the requested operational mode SHALL take effect.

#### Scenario: Shell Shim Preserves Non-Zero Exit Code on Failure (Edge Case)
- **Given** an integrity violation in the workspace
- **When** `./scripts/verify_integrity.sh` runs
- **Then** the underlying Python engine SHALL fail with exit code 1
- **And** the shell shim SHALL exit with code 1.

---

### Requirement: Structured MCP Integration
The MCP server tool `verify_integrity` (`src/mcp/tools/verify_integrity.py`) SHALL consume structured JSON directly from the verification engine (either by invoking `scripts/verify_integrity.py --json` or importing `src.verification.guardrails` directly) without parsing or regex-matching terminal stdout strings or emojis.

#### Scenario: Healthy System Returns Structured Dictionary to MCP Client (Happy Path)
- **Given** an MCP client invoking the `verify_integrity` tool on a healthy repository
- **When** the tool executes the verification engine
- **Then** the tool SHALL parse the structured JSON payload directly into a typed dictionary
- **And** return a structured result with `healthy: True`, check names, and metrics
- **And** the tool SHALL NOT perform string scraping or emoji regex matching.

#### Scenario: Unhealthy System Returns Structured Failures to MCP Client (Edge Case)
- **Given** a repository state failing one or more invariant checks
- **When** the `verify_integrity` MCP tool executes
- **Then** the tool SHALL receive structured error details from the JSON payload
- **And** return `healthy: False` with the list of specific failing checks and error messages.

#### Scenario: Execution Failure Handled Gracefully in MCP Tool (Edge Case)
- **Given** a catastrophic execution error or unhandled exception during verification execution
- **When** the `verify_integrity` MCP tool runs
- **Then** the tool SHALL capture stderr and process return codes
- **And** return a structured failure response without crashing the MCP server process.
