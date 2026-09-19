# Project: yt-auto MCP Server Implementation & SSOT Synchronization

## Architecture
- **Framework**: Official Python MCP SDK (`mcp` v2.2.0) utilizing `from mcp.server.mcpserver import MCPServer` (or `from mcp.server import MCPServer`).
- **Transports**: Primary `stdio` transport via `server.run_stdio_async()` (with OS file descriptor diversion) and modular SSE readiness (`server.sse_app`).
- **Core Package**: `src/mcp/` containing:
  - `server.py`: `MCPServer` factory and entrypoint.
  - `tools.py`: 8 core tools (`system_preflight`, `list_lanes`, `get_lane_info`, `query_loop_catalog`, `audit_loop_catalog`, `run_pipeline_dry_run`, `get_system_status`, `manage_queue`) + `verify_integrity`.
  - `resources.py`: 3 resources (`channels://{channel_name}/config`, `lanes://catalog`, `system://health`).
  - `prompts.py`: 3 operational prompts (`preflight_diagnostics`, `channel_incident_analysis`, `video_qa_review`).
  - `sanitizer.py`: Recursive output sanitization enforcing `[REDACTED]` and zero secret leaks.
  - `__main__.py`: Module entrypoint enabling `python3 -m src.mcp`.
- **CLI Integration**: Subcommand `mcp` in `main.py` delegating to `src.cli.handlers.mcp`.
- **Automated Drift Verification**: `scripts/verify_mcp_sync.py` integrated into `./scripts/verify_integrity.sh` as Check #9.
- **SSOT Documentation**: `docs/MCP.md` (standalone technical guide), updated `README.md`, `docs/OPERACION.md`, and client configurations (`mcp_config.json`, `.mcp.json.example`).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | MCP Server Core & Lifecycle | `MCPServer` instantiation with name, version, instructions, and stdio/SSE runner | M1 | Survey |
| 2 | Tool: system_preflight | Preflight environment, disk, binary, and token checks with fail-closed errors | M1 | Survey |
| 3 | Tool: list_lanes | Production lane listing with scheduling state and resolved voice profile | M1 | Survey |
| 4 | Tool: get_lane_info | Deep lane specification, cadence, duration, and visual pipeline specs | M1 | Survey |
| 5 | Tool: query_loop_catalog | Filter video loop records by category, orientation, and channel compatibility | M1 | Survey |
| 6 | Tool: audit_loop_catalog | Audit physical MP4 files vs SQLite DB and verify bank_manifest.json metrics | M1 | Survey |
| 7 | Tool: run_pipeline_dry_run | Synthetic dry run (--lane -t) with zero API quota and stream-copy | M1 | Survey |
| 8 | Tool: get_system_status | System health, queue counts, process locks, and recent failure logs | M1 | Survey |
| 9 | Tool: manage_queue | Story queue listing, review pending inspection, channel pause/resume, auto-publish sweep | M1 | Survey |
| 10 | Tool: verify_integrity | Execute repository integrity script and anti-regression suite | M1 | Survey |
| 11 | Resource: channels://{channel_name}/config | Sanitized channel profile via `public_dict()`, no secret paths leaked | M1 | Survey |
| 12 | Resource: lanes://catalog | Expose canonical production lane specifications (config/lanes.json) | M1 | Survey |
| 13 | Resource: system://health | Real-time health metrics, disk headroom, and lock status | M1 | Survey |
| 14 | Prompt: preflight_diagnostics | Step-by-step preflight diagnosis and GO/NO-GO workflow | M1 | Survey |
| 15 | Prompt: channel_incident_analysis | Guided triage workflow for channel failures, error spikes, and paused lanes | M1 | Survey |
| 16 | Prompt: video_qa_review | In-depth QA review checklist against 10-stage pipeline gatekeeper | M1 | Survey |
| 17 | Security: Credential Sanitizer | Mask secrets with `[REDACTED]`, sanitize exceptions and output payloads | M1 | Survey |
| 18 | Drift Detection: verify_mcp_sync.py | Script verifying parity between MCPServer registrations, client configs, and docs | M2 | Survey |
| 19 | Integrity Integration: verify_integrity.sh | Check #9 in verify_integrity.sh running verify_mcp_sync.py | M2 | Survey |
| 20 | SSOT Documentation: docs/MCP.md | Comprehensive technical guide for tools, resources, prompts, and governance | M3 | Survey |
| 21 | Client Configs: mcp_config.json | Ready-to-use client config for Antigravity, Claude Desktop, and CLI | M3 | Survey |
| 22 | Docs SSOT Updates & Line Budget | Update README.md, docs/OPERACION.md with pruning to keep active docs <= 1000 lines | M3 | Survey |
| 23 | E2E Opaque-Box Test Suite | Tier 1-4 tests in tests/unit/test_mcp_server.py testing full protocol | E2E-Track | Survey |
| 24 | Final Verification & Quality Gate | 100% E2E tests passing, drift verification, and verify_integrity.sh exit 0 | M4 | Survey |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | E2E Testing Track | Requirement-driven test suite (Tiers 1-4) in `tests/unit/test_mcp_server.py`, TEST_INFRA.md & TEST_READY.md | none | IN_PROGRESS |
| 1 | MCP Core Server & Capability Layer | `src/mcp/` package with 9 tools, 3 resources, 3 prompts, sanitizer, CLI handler | none | IN_PROGRESS |
| 2 | Automated Sync & Drift Detection | `scripts/verify_mcp_sync.py` and integration into `scripts/verify_integrity.sh` Check #9 | M1 | PENDING |
| 3 | SSOT Policy, Docs & Client Configs | `docs/MCP.md`, `mcp_config.json`, `.mcp.json.example`, updates to `README.md` & `docs/OPERACION.md` adhering to line budget | M1, M2 | PENDING |
| 4 | Final Milestone: E2E & Hardening | Phase 1 (100% E2E tests pass) + Phase 2 (Adversarial coverage hardening & full integrity audit) | E2E, M1, M2, M3 | PENDING |

## Interface Contracts
### `src.mcp.server:create_mcp_server() -> MCPServer`
- Creates, configures, and registers all tools, resources, and prompts on an `MCPServer` instance.
- Canonical name: `"yt-auto"`, version: `"2.2.0"`.

### `src.mcp.sanitizer:sanitize_payload(data: Any) -> Any`
- Recursively inspects data structures (dicts, lists, strings) and replaces any tokens matching secret patterns with `"[REDACTED]"`.
- Replaces secret path fields (`cookies_path`, `youtube_token_path`) with boolean flags.

### `scripts.verify_mcp_sync:main() -> int`
- Imports `create_mcp_server()`, extracts registered tool names, resource URI patterns, and prompt names.
- Parses `docs/MCP.md` and validates 100% bidirectional parity.
- Validates `mcp_config.json` and `.mcp.json.example`.
- Exits 0 on success, 1 on drift.

## Code Layout
- `src/mcp/__init__.py`: Package export `create_mcp_server`.
- `src/mcp/server.py`: MCPServer factory and transport runners (`run_stdio`, `run_sse`).
- `src/mcp/tools.py`: Tool definitions and handlers wrapping core subsystems.
- `src/mcp/resources.py`: Resource definitions for channels, lanes, and system health.
- `src/mcp/prompts.py`: Prompt templates and operational diagnostic guides.
- `src/mcp/sanitizer.py`: Interceptor and redaction helper functions.
- `src/mcp/__main__.py`: Direct CLI execution entrypoint (`python3 -m src.mcp`).
- `src/cli/handlers/mcp.py`: CLI command handler for `main.py mcp`.
- `scripts/verify_mcp_sync.py`: Automated parity validator.
- `docs/MCP.md`: Complete MCP documentation and tool reference.
- `mcp_config.json` / `.mcp.json.example`: Client configuration files.
- `tests/unit/test_mcp_server.py`: Complete E2E and unit test suite.
