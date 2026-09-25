# Specification: Model Context Protocol (MCP) Server Health Monitoring

## Capability Overview
The `mcp-server-health-monitoring` capability provides an automated, self-diagnostic health assessment module (`src/observability/mcp_health.py`) for the `yt-auto` Model Context Protocol (MCP) server. It validates server factory importability, monitors tool registration and runtime tool crashes, and executes programmatic Single-Source-of-Truth (SSOT) drift checks against `scripts/verify_mcp_sync.py`, categorizing overall MCP operational status into `HEALTHY`, `DEGRADED`, or `BROKEN`.

## Requirements

### Requirement 1: MCP Server Import and Factory Initialization Validation
The MCP health checker MUST verify that MCP server components are importable and that the factory function `create_mcp_server()` instantiates without exceptions.

1. `check_mcp_import_and_registration()` MUST attempt to import `create_mcp_server` from `src.mcp.server`.
2. The health check MUST instantiate an `MCPServer` instance and enumerate all registered tools, resources, and prompts.
3. If importing `src.mcp.server` raises `ImportError` or any syntax/dependency error, the check MUST immediately return status `BROKEN` with the exact stack trace and missing module details.
4. If factory instantiation fails due to schema validation or missing tool definitions, the check MUST record status `BROKEN`.

#### Scenario: Clean MCP server factory instantiation (Happy Path)
- **Given** all MCP dependencies and modules in `src/mcp/` are correctly installed and syntax-valid
- **When** `check_mcp_import_and_registration()` is executed
- **Then** the check MUST return `import_ok = True`
- **And** all registered tools, resources, and prompts MUST be listed without exceptions.

#### Scenario: Broken MCP server import due to syntax error or missing package (Failure State)
- **Given** an invalid import or broken dependency introduced into `src/mcp/server.py`
- **When** `check_mcp_import_and_registration()` is executed
- **Then** the check MUST catch the exception safely
- **And** `import_ok` MUST be `False`
- **And** the health check MUST categorize server status as `BROKEN`.

---

### Requirement 2: Tool and Resource Runtime Health and Crash Tracking
The MCP server runtime MUST track invocation outcomes and runtime exceptions across registered MCP tools and resources.

1. When any MCP tool invocation in `src/mcp/tools/` raises an unhandled exception:
   - The error MUST be caught, logged, and an event of type `mcp_tool_failure` MUST be recorded into `system_events`.
   - The event MUST include the tool name, input arguments, and error diagnostic traceback.
2. The MCP health checker MUST compute tool execution success rate over the past 24 hours.
3. If the tool error rate exceeds 20% or if critical tools (`manage_queue`, `get_system_status`, `get_tube_status`) fail continuously, tool runtime health MUST be flagged as `DEGRADED`.

#### Scenario: Recording an MCP tool execution failure
- **Given** an invocation of MCP tool `manage_queue` with malformed arguments that raises an uncaught error
- **When** the error handler intercepts the failure
- **Then** an `mcp_tool_failure` event MUST be emitted to `system_events`
- **And** the recent error counter for `manage_queue` MUST be incremented.

---

### Requirement 3: Automated SSOT Parity Drift Check Integration
The health checker MUST programmatically execute the bidirectional parity checks established in `scripts/verify_mcp_sync.py` without requiring shell invocation.

1. The health checker MUST import or execute `verify_mcp_sync(repo_root)`:
   - Validating code registrations vs `CANONICAL_TOOLS`, `CANONICAL_RESOURCES`, and `CANONICAL_PROMPTS`.
   - Validating documentation parity between code registrations and `docs/MCP.md`.
   - Validating client configuration files (`mcp_config.json`, `.mcp.json.example`).
2. If any drift or mismatch is detected, the health check MUST return `parity_ok = False` and populate `drift_errors` with the discrepancy list.

#### Scenario: MCP sync check verifies zero drift (Happy Path)
- **Given** code, docs, and canonical definitions are in complete alignment
- **When** `check_mcp_ssot_sync()` is evaluated
- **Then** `parity_ok` MUST be `True`
- **And** `drift_errors` MUST be empty.

#### Scenario: MCP sync check catches undocumented tool or missing canonical definition
- **Given** a new tool registered in `create_mcp_server()` that is absent from `docs/MCP.md` or `CANONICAL_TOOLS`
- **When** `check_mcp_ssot_sync()` is evaluated
- **Then** `parity_ok` MUST be `False`
- **And** `drift_errors` MUST specify the undocumented tool name.

---

### Requirement 4: MCP Server Tri-State Health Evaluation
The overall MCP health assessment MUST synthesize import checks, runtime crash rates, and SSOT drift verification into a consolidated tri-state enum (`HEALTHY`, `DEGRADED`, `BROKEN`).

1. **`BROKEN`**: Assigned if import fails, server instantiation throws, or core database connectivity is unavailable.
2. **`DEGRADED`**: Assigned if SSOT parity drift is detected, client configuration is missing/invalid, or recent tool error rate exceeds threshold.
3. **`HEALTHY`**: Assigned when import succeeds, all tools/resources instantiate, zero SSOT drift is present, and tool error rates are nominal.
4. The resolved health state MUST be exposed in `system://health` and `system://tube`.

#### Scenario: Resolving consolidated MCP health status
- **Given** MCP import succeeds and zero tool runtime errors occurred
- **But** an SSOT drift failure is detected against `docs/MCP.md`
- **When** `get_mcp_health_status()` is called
- **Then** the overall status MUST be `DEGRADED`
- **And** the reason MUST state `"MCP documentation/canonical drift detected"`.
