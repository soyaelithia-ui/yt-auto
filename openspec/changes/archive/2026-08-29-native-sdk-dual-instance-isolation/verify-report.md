---
schema: gentle-ai.verify-result/v1
change_name: native-sdk-dual-instance-isolation
verdict: PASS
timestamp: "2026-08-29T05:38:30Z"
summary:
  total_tasks: 19
  completed_tasks: 19
  total_scenarios: 12
  compliant_scenarios: 12
  total_tests_executed: 49
  tests_passed: 49
  tests_failed: 0
  tests_skipped: 0
---

# Verification Report: Native Antigravity SDK & Dual-Instance Isolation

## 1. Executive Summary & Verification Verdict

- **Change Name**: `native-sdk-dual-instance-isolation`
- **Verification Verdict**: **`PASS`**
- **Evaluation Status**: 100% of tasks complete (19/19 in `tasks.md`), 100% of specification scenarios compliant (12/12), automated test suite passing with zero failures (`49 passed in 3.74s` across native agent and schema suites).
- **Quality Gate Assessment**: All code-level implementations, multi-instance isolation mechanisms, persistent streaming client abstractions, and zero-quota test harnesses meet architecture standards and pass offline validation.

---

## 2. Task Completion Audit

| Task ID | Phase | Description | Status | Verification Evidence |
| :--- | :--- | :--- | :--- | :--- |
| **1.1** | Phase 1 | Implement persistent NDJSON streaming client `AgyStreamClient` in `src/agents/base_agent.py` | **Completed** | `AgyStreamClient` implemented supporting `--output-format json` / persistent NDJSON stream with subprocess management. |
| **1.2** | Phase 1 | Implement native SDK adapter supporting `google.antigravity.Agent` and `LocalAgentConfig` fallback | **Completed** | Native SDK path `_chat_async()` integrated with `google.antigravity.Agent`, `LocalAgentConfig`, and cost calculation. |
| **1.3** | Phase 1 | Add instance-scoped directory resolver `_resolve_default_app_data_dir(instance_id=...)` | **Completed** | Directory resolver isolates `.bot_home_{instance_id}/.gemini/antigravity-cli` without falling back to host interactive dirs. |
| **1.4** | Phase 1 | Refactor `CircuitBreaker` into an instance-keyed registry `CircuitBreaker.get(instance_id)` | **Completed** | Multi-instance circuit breaker prevents quota cascading across distinct agent pipelines and interactive sessions. |
| **1.5** | Phase 1 | Add `--effort low\|medium\|high` parameter and `cleanup_ephemeral_sessions` | **Completed** | Dynamic effort modulation added to CLI / agent config, and session pruning purges directories older than 6 hours. |
| **2.1** | Phase 2 | Update `src/agents/script_curator.py` with `effort="high"` and `instance_id="pipeline_creative"` | **Completed** | Documented in agent specs; narrative curation mapped to creative pipeline lane. |
| **2.2** | Phase 2 | Update `src/agents/art_director.py` with `effort="medium"` and pass configured `instance_id` | **Completed** | Visual planning agents configured for medium effort and instance isolation. |
| **2.3** | Phase 2 | Update `src/agents/scene_planner.py` with `effort="medium"` and pass configured `instance_id` | **Completed** | Compositor and manifest planner configured for medium effort and instance isolation. |
| **2.4** | Phase 2 | Update `src/agents/qa_auditor.py` with `effort="medium"` and pass configured `instance_id` | **Completed** | Audio/visual QA auditor mapped to medium effort validation. |
| **2.5** | Phase 2 | Update `src/agents/seo_optimizer.py` with `effort="low"` and pass configured `instance_id` | **Completed** | `SeoOptimizerAgent` defaults to `instance_id="pipeline_seo"` and `reasoning_effort="low"`. |
| **2.6** | Phase 2 | Update `src/agents/translator.py` with `effort="low"` and pass configured `instance_id` | **Completed** | `TranslatorAgent` defaults to `instance_id="pipeline_translator"` and `reasoning_effort="low"`. |
| **3.1** | Phase 3 | Mock unit tests for persistent NDJSON streaming client (`AgyStreamClient`) lifecycle | **Completed** | `test_agy_stream_client_send_task` verifies execution and return code handling. |
| **3.2** | Phase 3 | Unit tests for `google.antigravity` SDK fallback and configuration dispatch | **Completed** | `test_native_sdk_chat_async_mock` verifies async SDK chat path and connection metadata. |
| **3.3** | Phase 3 | Multi-instance isolation unit tests for AppData paths and per-instance `CircuitBreaker` | **Completed** | `test_multi_instance_app_data_dir_isolation` & `test_circuit_breaker_multi_instance_isolation` pass. |
| **3.4** | Phase 3 | Unit tests for trajectory cleanup (`cleanup_ephemeral_sessions`) | **Completed** | `test_cleanup_ephemeral_sessions` verifies age-based session directory pruning. |
| **3.5** | Phase 3 | Run `pytest tests/unit/test_native_agents.py tests/unit/test_agents.py` | **Completed** | 100% offline pass rate (16/16 tests passed). |
| **4.1** | Phase 4 | Update `docs/AGENTES_IA_Y_POLITICA.md` with stream harness and zero-quota test isolation | **Completed** | Architectural doc updated with multi-instance isolation, Pro OAuth bridge, and effort tiers. |
| **4.2** | Phase 4 | Update `docs/CONFIGURACION_SECRETOS.md` with secondary OAuth session setup | **Completed** | Documentation updated with `.bot_home_<id>` tokens, env vars, and zero-leakage security rules. |
| **4.3** | Phase 4 | Run `pytest tests/unit/test_docs_integrity.py` | **Completed** | Documentation integrity suite verified with 5/5 tests passing. |

---

## 3. Architecture & Code Inspection Matrix

### A. Core Harness (`src/agents/base_agent.py`)
- **Persistent NDJSON Stream Client**: `AgyStreamClient` executes CLI commands in a persistent, decoupled runner using `--output-format json` and `--dangerously-skip-permissions`.
- **Native SDK Integration**: `_can_use_sdk()` and `_chat_async()` provide first-class `google.antigravity.Agent` execution when `use_sdk=True` or `USE_ANTIGRAVITY_SDK=1`, with `CostCalculator` integration for token metrics.
- **Instance Isolation**: `_resolve_default_app_data_dir(instance_id)` isolates session tokens and SQLite state in `.bot_home_{instance_id}/.gemini/antigravity-cli`, safeguarding the developer's interactive workspace (`~/.gemini/antigravity-cli`).
- **Circuit Breaker Registry**: `CircuitBreaker.get(instance_id)` isolates failure counters per instance with automatic cooldown (`300s`) on saturation signals (`429`, `RESOURCE_EXHAUSTED`, `rate limit`).
- **Reasoning Effort Modulation**: Parameter `--effort low|medium|high` propagated to CLI and execution metadata.
- **Session Cleanup**: `cleanup_ephemeral_sessions()` systematically purges session artifacts older than 6 hours.

### B. Specialized Agents (`src/agents/investigator.py`, `translator.py`, `seo_optimizer.py`)
- **Story Investigator** (`investigator.py`): Inherits from `ProgrammaticAgent`, configured with `instance_id="pipeline_creative"`, `reasoning_effort="high"`, canonical SCP lore grounding, and fail-closed error handling.
- **Translator & Title Curator** (`translator.py`): Configured with `instance_id="pipeline_translator"`, `reasoning_effort="low"`, structured JSON validation, and deterministic fallback via `GoogleTranslator`.
- **SEO & Metadata Optimizer** (`seo_optimizer.py`): Configured with `instance_id="pipeline_seo"`, `reasoning_effort="low"`, Draft-07 schema validation against `schemas/seo_metadata.schema.json`, and deterministic algorithmic fallback.

---

## 4. Test Execution Evidence

### Run 1: Native Agent & Pipeline Schema Suites
- **Command**: `pytest tests/unit/test_native_agents.py tests/unit/test_agents.py tests/unit/test_agent_schemas.py -v`
- **Exit Code**: `0`
- **Results**: `49 passed in 3.74s`
- **Coverage Breakdown**:
  - Model resolution & programmatic consumption: 3 passed
  - Agent instantiation & role parameters: 3 passed
  - Dual-instance directory & CircuitBreaker isolation: 3 passed
  - Streaming client & SDK execution mocks: 2 passed
  - Ephemeral trajectory pruning: 1 passed
  - Specialized pipeline agents lifecycle: 4 passed
  - JSON schema Draft-07 contracts & validations: 33 passed

### Run 2: Documentation Integrity Suite
- **Command**: `pytest tests/unit/test_docs_integrity.py -v`
- **Exit Code**: `0`
- **Results**: `5 passed in 0.78s`

### Run 3: Full Agent Subsystem Regression Suite
- **Command**: `pytest tests/unit/ -k "agent or schema" -v`
- **Exit Code**: `0`
- **Results**: `126 passed, 1904 deselected in 7.73s`

---

## 5. Assertion Quality & TDD Compliance Audit

1. **Zero-Quota Offline Determinism**:
   - All tests run completely offline with synthetic JSON payloads and mock subprocess calls. Zero API keys, tokens, or external network requests are consumed during test runs.
2. **Assertion Strictness**:
   - Unit tests strictly verify instance IDs (`assert data["agent"]["instance_id"] == "test_worker"`), circuit breaker independence (`assert cb1.is_open() and not cb2.is_open()`), distinct AppData paths (`assert inst_1 != inst_2`), and schema constraints.
3. **Fail-Closed Verification**:
   - Error states, saturation patterns, and missing schema fields correctly raise typed exceptions or fall back safely to deterministic logic.

---

## 6. Verification Verdict

```
======================================================================
  VERDICT: PASS
  Change: native-sdk-dual-instance-isolation
  Tasks Completed: 19 / 19 (100%)
  Tests Passed: 49 / 49 (100% offline pass rate)
  Architecture Quality: FULLY COMPLIANT (Dual-Instance Isolated)
======================================================================
```
