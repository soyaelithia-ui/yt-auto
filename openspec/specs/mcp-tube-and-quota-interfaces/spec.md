# Specification: MCP Tube and Quota Interfaces

## Capability Overview
The `mcp-tube-and-quota-interfaces` capability exposes comprehensive operational observability to AI agents and Model Context Protocol (MCP) clients via standardized MCP resources (`system://tube`, `system://quotas`, enriched `system://health`) and the canonical MCP tool `get_tube_status`. It guarantees 100% Single-Source-of-Truth (SSOT) parity across runtime server registrations, canonical sets in `scripts/verify_mcp_sync.py`, and documentation in `docs/MCP.md`.

## Requirements

### Requirement 1: Canonical MCP Telemetry Resources
The MCP server in `src/mcp/resources.py` and `src/mcp/server.py` MUST register canonical URI endpoints for operational telemetry and quotas.

1. **`system://tube`**:
   - MUST return a JSON payload representing the complete `TubeSnapshot`, including host resources (CPU %, process RSS RAM, free storage), daemon liveness age, active channel controls and locks, circuit breaker states, multi-provider token burn summary, YouTube quota/limits, prompt leak incidents, database backup age, SQLite WAL growth, MCP self-health, and asset rejection tallies.
   - MIME type MUST be `application/json`.
2. **`system://quotas`**:
   - MUST return a JSON payload detailing token burn and quota status across AI providers (Antigravity Pro, Gemini REST, Grok, TTS) and YouTube Data API v3.
   - MUST include token counts (prompt, completion, cached, reasoning), USD costs, saturation events, and remaining quota estimates.
   - MIME type MUST be `application/json`.
3. **Enriched `system://health`**:
   - MUST extend the existing health resource to include daemon heartbeat age, MCP server self-health state (`HEALTHY`, `DEGRADED`, `BROKEN`), proactive cookie decay status, and SQLite WAL status.

#### Scenario: Reading system://tube resource returns full telemetry snapshot
- **Given** an active MCP client connected via standard stdio JSON-RPC
- **When** the client issues a `resources/read` request with URI `system://tube`
- **Then** the server MUST return HTTP 200 / valid JSON response
- **And** the JSON object MUST contain keys `host_resources`, `daemon_liveness`, `channel_controls`, `token_burn`, and `incidents`.

#### Scenario: Reading system://quotas resource returns multi-provider burn and costs
- **Given** token burn events recorded for Antigravity Pro and ElevenLabs
- **When** the client issues a `resources/read` request with URI `system://quotas`
- **Then** the server MUST return valid JSON
- **And** the payload MUST report `total_cost_usd` and provider-specific breakdowns.

---

### Requirement 2: Canonical MCP Operational Tool (get_tube_status)
The MCP server MUST register the tool `get_tube_status` in `src/mcp/tools/` allowing AI agents to query filtered telemetry snapshots.

1. **Tool Definition**:
   - Name: `get_tube_status`
   - Description: Comprehensive operational telemetry hub inspecting host resources, multi-provider token burn, YouTube quota limits, stoppages, and incidents.
2. **Input Parameters**:
   - `channel` (optional string): Filter telemetry to a specific canonical channel (`horror`, `drama`, `scifi`).
   - `window_hours` (optional integer, default 24): Observation window for token burn and incident queries.
   - `include_incidents` (optional boolean, default True): Whether to include the recent operational incident log.
   - `include_burn` (optional boolean, default True): Whether to include multi-provider token burn and USD calculations.
3. **Output**:
   - Structured JSON dictionary formatted as string in tool content.

#### Scenario: Executing get_tube_status with channel filter and 6-hour window
- **Given** an AI agent connected to the MCP server
- **When** the agent invokes `get_tube_status(channel="horror", window_hours=6)`
- **Then** the tool MUST execute cleanly
- **And** the returned JSON MUST contain metrics scoped to the requested channel and timeframe
- **And** execution time MUST be $< 50\text{ ms}$.

---

### Requirement 3: 100% Bidirectional SSOT Parity Across Code, Docs, and Verification Gates
The registration of new MCP resources and tools MUST maintain strict 100% parity across all repository SSOT definitions.

1. `CANONICAL_TOOLS` in `scripts/verify_mcp_sync.py` MUST include `"get_tube_status"`.
2. `CANONICAL_RESOURCES` in `scripts/verify_mcp_sync.py` MUST include `"system://tube"` and `"system://quotas"`.
3. `docs/MCP.md` MUST document the schema, arguments, return formats, and descriptions for `get_tube_status`, `system://tube`, and `system://quotas`.
4. `scripts/verify_mcp_sync.py` MUST execute with exit code 0, asserting zero drift across code, documentation, and configuration.

#### Scenario: SSOT verification script validates parity gate
- **Given** `create_mcp_server()`, `scripts/verify_mcp_sync.py`, and `docs/MCP.md` are updated
- **When** `scripts/verify_mcp_sync.py` is executed
- **Then** exit code MUST be 0
- **And** the output MUST report `[STATUS: HEALTHY] 100% bidirectional parity verified with zero drift.`

---

### Requirement 4: MCP Resource Read and Tool Execution Performance
Telemetry queries executed via MCP MUST adhere strictly to resource budget and execution latency constraints.

1. Sampling host resources and querying SQLite WAL for `system://tube` or `get_tube_status` MUST complete in $< 100\text{ ms}$ wall-clock time.
2. Memory consumed during MCP resource serialization MUST NOT exceed $20\text{ MiB}$ of process RSS memory.
3. Telemetry operations MUST execute with read-only SQLite transactions and MUST NOT acquire exclusive write locks that block media generation or publishing pipelines.

#### Scenario: Tool latency assertion under active pipeline execution
- **Given** a background pipeline run performing video composition
- **When** `get_tube_status` is invoked concurrently via MCP
- **Then** the tool MUST return within 100 ms
- **And** the background video composition MUST proceed without database lock errors.
