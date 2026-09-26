# Specification: Agentic Harness for Antigravity SDK Agents

## Capability Overview
The `agentic-harness` capability provides a robust, autonomous execution and recovery harness for Antigravity SDK programmatic agents (`src/agents/base_agent.py`) and CLI stream backends. It elevates binary retry logic into an adaptive multi-stage agentic loop comprising:
1. **Autonomous Decision Making (`decidir`)**: Declarative error classification and stateful next-step routing (`retry`, `correct`, `adjust`, `stop`).
2. **Autonomous Self-Adjustment (`autoajustarse`)**: Dynamic runtime adaptation of prompt constraints, reasoning effort, sampling temperature, and context payload compaction when encountering structural degradation or semantic drift.
3. **Structured Multi-Attempt Failure Correction (`corregir fallos`)**: Formalized feedback mechanism delivering specific contract and schema failure diagnostics back into subsequent turns to guide self-correction.
4. **Decision Trace Telemetry and Auditing**: Comprehensive auditing persisted in `task_result.json` under `failure_evidence["decision_trace"]` capturing every evaluation, adjustment, rationale, and attempt.
5. **Circuit Breaker Isolation & Saturation Governance**: Instance-keyed circuit breaking that trips on `429` / `RESOURCE_EXHAUSTED` signals to protect provider quotas.

Execution operates strictly within Section 5 of `AGENTS.md` and invariant `REG-14`, enforcing bounded attempt ceilings (`max_attempts: 3`, `max_corrections: 2`) and zero unbounded loops.

---

## Requirements

### Requirement: Autonomous Decision Making (`decidir`)
The agent harness MUST evaluate execution outcomes and errors through a declarative decision engine (`decidir`). Hardcoded blind retries MUST NOT be used.

The decision engine MUST classify any encountered failure into one of four deterministic recovery actions:
1. `retry`: For transient socket, network, or transport disconnects where the prompt remains unchanged and a bounded linear or exponential backoff delay is applied.
2. `correct`: For schema validation errors or domain contract violations where path-specific error diagnostics are synthesized into a targeted correction turn.
3. `adjust`: For semantic drift, formatting degradation, or repeated soft validation errors where execution hyperparameters (temperature, reasoning effort, context compaction) MUST be modified before re-invocation.
4. `stop`: For provider saturation (`429`, `RESOURCE_EXHAUSTED`, rate limits) or exhaustion of attempt and correction budgets.

When a saturation signal is detected, the harness MUST immediately select `stop`, record reason `provider_saturation`, and trip the instance-keyed `CircuitBreaker`.
When the remaining attempt budget (`attempt >= max_attempts`) or correction budget (`correction_count >= max_corrections`) is reached, the harness MUST select `stop` with reason `recovery_budget_exhausted` and fail closed by raising `AIProviderChainExhausted`.

#### Scenario: Transient socket error triggers bounded retry
- **Given** an agent invocation encountering a socket timeout or network disconnect on attempt 1
- **When** `recovery_policy.decide` evaluates the error with `attempt < max_attempts`
- **Then** the decision engine MUST emit `RecoveryDecision(action="retry", reason="transient_execution_failure")`
- **And** the harness MUST pause for `retry_delay_seconds` before re-invoking the provider with the original prompt.

#### Scenario: Schema validation error triggers structured correction
- **Given** an agent response that fails JSON Schema validation on attempt 1 with remaining correction budget
- **When** `recovery_policy.decide` evaluates the error starting with `validation:`
- **Then** the decision engine MUST emit `RecoveryDecision(action="correct", reason="structured_output_validation")`
- **And** the harness MUST proceed to construct a targeted correction turn.

#### Scenario: Provider saturation trips circuit breaker and stops execution
- **Given** an agent call returning HTTP 429 or `RESOURCE_EXHAUSTED`
- **When** `recovery_policy.decide` evaluates the response
- **Then** the decision engine MUST emit `RecoveryDecision(action="stop", reason="provider_saturation")`
- **And** the instance circuit breaker MUST open immediately for `cooldown_seconds`
- **And** no further provider retries MUST be attempted in this execution.

#### Scenario: Budget exhaustion triggers fail-closed termination
- **Given** an agent that has reached the maximum allowed attempts (`attempt == max_attempts`)
- **When** a subsequent error occurs
- **Then** the decision engine MUST emit `RecoveryDecision(action="stop", reason="recovery_budget_exhausted")`
- **And** the agent execution MUST terminate and raise `AIProviderChainExhausted`.

---

### Requirement: Autonomous Self-Adjustment (`autoajustarse`)
When an agent experiences structural validation failures, truncation, or semantic drift, the harness MUST autonomously adjust runtime execution parameters before re-invocation:

1. **Hyperparameter Adaptation**:
   The harness MUST dynamically adjust inference hyperparameters:
   - Decreasing sampling temperature (e.g., from default down to `0.1` or `0.0`) to enforce strict deterministic compliance.
   - Stepping down reasoning effort (e.g., `high` -> `medium` -> `low`) or bounding output token ceilings if timeouts or context limits are approached.
2. **Context Compaction and Focus Framing**:
   The harness MUST compact non-essential context by stripping extraneous conversation history, system preamble, or raw error stack traces, reinforcing only the primary schema constraints.
3. **Parameter Tracking**:
   All adjusted parameters MUST be captured in the `adjustments` mapping of the decision record and applied to the subsequent provider invocation.

#### Scenario: Temperature reduction on repeated schema failure
- **Given** an agent invocation failing strict JSON formatting with available correction budget
- **When** the harness applies self-adjustment (`autoajustarse`)
- **Then** the harness MUST set a reduced `temperature` in `adjustments` (e.g. `0.1`)
- **And** re-invoke the provider with the deterministic hyperparameter setting.

#### Scenario: Context compaction on lengthy prompt drift
- **Given** a multi-turn agent prompt that drifts or approaches token bounds
- **When** self-adjustment is triggered
- **Then** the harness MUST compact input context by stripping non-critical preamble or summarizing prior turn history
- **And** record `compact_context: True` in `adjustments`.

#### Scenario: Restoring default parameters on successful turn
- **Given** an agent turn that completed successfully after a self-adjustment
- **When** the execution completes
- **Then** the circuit breaker and policy MUST record a successful turn
- **And** subsequent independent tasks MUST start from baseline configuration unless explicitly configured.

---

### Requirement: Structured Multi-Attempt Failure Correction (`corregir fallos`)
The harness MUST implement a formalized feedback mechanism that delivers actionable contract diagnostics back to the agent in subsequent turns:

1. **Diagnostic Extraction**:
   When structured validation fails (`jsonschema.ValidationError`, Pydantic error, or domain contract assertion), the harness MUST extract the exact schema path, invalid value, and expected constraint.
2. **Targeted Correction Prompt**:
   The harness MUST synthesize a correction prompt containing:
   - The original task directive.
   - The failure diagnosis: `Correction required: the previous response failed the declared contract ({detail}). Return only a corrected response.`
   - Explicit instructions to avoid the specific identified violation.
3. **Bounded Correction Loop**:
   Correction attempts MUST be strictly bounded by `max_corrections` (default 1, ceiling 2).
4. **Isolated Conversation Turn**:
   Correction turns MUST NOT leak into external state; once the correction succeeds, the validated structured output is accepted as the final artifact.

#### Scenario: JSON schema path error synthesized into correction prompt
- **Given** an atmospheric director response missing the required field `loop_category`
- **When** validation fails with `validation: 'loop_category' is a required property`
- **Then** the harness MUST format a correction task containing the missing property path
- **And** send the correction prompt to the agent backend on the next turn.

#### Scenario: Agent repairs output on correction turn
- **Given** an initial invalid turn followed by a correction prompt
- **When** the agent returns a schema-compliant response on attempt 2
- **Then** `_validate_response` MUST pass cleanly
- **And** the harness MUST accept the response
- **And** `failure_evidence["recovered"]` MUST be set to `True`.

#### Scenario: Correction budget exhausted after failed correction attempt
- **Given** an agent whose correction turn also fails validation and `correction_count >= max_corrections`
- **When** `decide` is called
- **Then** the harness MUST NOT dispatch another correction turn
- **And** MUST transition status to error and terminate.

---

### Requirement: Decision Trace Telemetry and Auditing in task_result.json
Every agent execution MUST record complete chronological decision telemetry under `failure_evidence` within `task_result.json`.

1. **`decision_trace` Record Structure**:
   Each recovery evaluation MUST append a structured record to `failure_evidence["decision_trace"]` (and maintain compatibility with `failure_evidence["attempts"]`):
   - `attempt` (integer): Current attempt index (1-indexed).
   - `action` (string): Decision action (`retry`, `correct`, `adjust`, `stop`).
   - `reason` (string): Error classification reason.
   - `error` (string): Verbatim error string or diagnostic message.
   - `adjustments` (dict): Dictionary of parameter adjustments made in this step (empty if none).
   - `rationale` (string): Human-readable explanation of why the action was taken.
   - `timestamp` (string): ISO 8601 UTC timestamp of the decision.
2. **Policy Snapshot**:
   `failure_evidence["policy"]` MUST persist the active configuration (`max_attempts`, `max_corrections`, `retry_delay_seconds`).
3. **Recovery Status Flag**:
   - `failure_evidence["recovered"]` MUST be `True` if initial attempts failed but a subsequent attempt or correction succeeded.
   - `failure_evidence["recovered"]` MUST be `False` if no failure occurred or if all attempts failed.
4. **Audit Durability**:
   `task_result.json` MUST be atomically written to disk at the path designated by `task_result_path` before returning to the caller.

#### Scenario: Successful recovery persists complete decision trace
- **Given** an agent execution that encounters a contract violation on attempt 1 and recovers on attempt 2
- **When** `_run_async` finishes and writes `task_result.json`
- **Then** `task_result.json` MUST contain `failure_evidence["recovered"] = True`
- **And** `failure_evidence["decision_trace"]` MUST contain at least one entry with `action = "correct"`
- **And** the entry MUST include `attempt`, `reason`, `error`, `adjustments`, and `rationale`.

#### Scenario: Clean execution without failures records empty decision trace
- **Given** an agent execution that succeeds on attempt 1 without errors
- **When** `task_result.json` is generated
- **Then** `failure_evidence["recovered"]` MUST be `False`
- **And** `failure_evidence["decision_trace"]` MUST be an empty list `[]`
- **And** `doc["status"]` MUST be `"success"`.

#### Scenario: Saturated run records saturation decision trace
- **Given** an agent execution that receives a 429 quota error
- **When** `task_result.json` is generated
- **Then** `doc["status"]` MUST be `"saturated"`
- **And** `failure_evidence["decision_trace"]` MUST record `action = "stop"` and `reason = "provider_saturation"`.

---

### Requirement: Circuit Breaker Isolation and Saturation Governance
Agent circuit breaking MUST be strictly isolated per `instance_id` to prevent cross-lane quota cascading.

1. **Instance Isolation**:
   Each `instance_id` (e.g. `default`, `horror`, `drama`, `scifi`, test runners) MUST maintain an independent `CircuitBreaker` instance. Tripping one instance circuit breaker MUST NOT block execution of other instances.
2. **Consecutive Failure Threshold**:
   The circuit breaker MUST open after $N$ consecutive failures (`failure_threshold`, default 3) or immediately upon receiving any provider saturation text (`429`, `RESOURCE_EXHAUSTED`, `rate limit`, `quota`).
3. **Cooldown Enforcement**:
   When open, any attempt to invoke the agent MUST fail immediately without sending network requests until `cooldown_seconds` has elapsed.
4. **Success Reset**:
   Any successful provider invocation MUST reset the consecutive failure counter to 0.

#### Scenario: Independent instance isolation prevents cascade
- **Given** instance `drama` experiences quota exhaustion and trips its circuit breaker
- **When** instance `horror` executes an agent invocation
- **Then** instance `horror` MUST NOT be blocked by `drama`'s open circuit breaker
- **And** `horror`'s invocation MUST proceed normally.

#### Scenario: Immediate trip on saturation signal
- **Given** a closed circuit breaker on instance `test_cb`
- **When** an invocation returns `RESOURCE_EXHAUSTED` on attempt 1
- **Then** `record_failure` MUST open the circuit breaker immediately without waiting for threshold $N$.
