# Tasks: Native Antigravity SDK & Dual-Instance Isolation

## Review Workload Forecast
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: single-pr
400-line budget risk: Low

## Phase 1: Core Harness & Dual-Instance Isolation
- [x] 1.1 Implement persistent NDJSON streaming client `AgyStreamClient` in `src/agents/base_agent.py` using `--input-format stream-json --output-format stream-json --dangerously-skip-permissions`.
- [x] 1.2 Implement native SDK adapter supporting `google.antigravity.Agent` and `LocalAgentConfig` fallback for Vertex AI / API-key environments in `src/agents/base_agent.py`.
- [x] 1.3 Add instance-scoped directory resolver `_resolve_default_app_data_dir(instance_id=...)` supporting `.bot_home_{instance_id}/.gemini/antigravity-cli` in `src/agents/base_agent.py`.
- [x] 1.4 Refactor `CircuitBreaker` into an instance-keyed registry `CircuitBreaker.get(instance_id)` in `src/agents/base_agent.py` to isolate failure states.
- [x] 1.5 Add `--effort low|medium|high` reasoning parameter support and ephemeral trajectory cleanup `cleanup_ephemeral_sessions(max_age_hours=6)` in `src/agents/base_agent.py`.

## Phase 2: Pipeline Agents & Effort Modulation
- [x] 2.1 Update `src/agents/script_curator.py` to set `effort="high"` and `instance_id="pipeline_creative"`.
- [x] 2.2 Update `src/agents/art_director.py` to set `effort="medium"` and pass configured `instance_id`.
- [x] 2.3 Update `src/agents/scene_planner.py` to set `effort="medium"` and pass configured `instance_id`.
- [x] 2.4 Update `src/agents/qa_auditor.py` to set `effort="medium"` and pass configured `instance_id`.
- [x] 2.5 Update `src/agents/seo_optimizer.py` to set `effort="low"` and pass configured `instance_id`.
- [x] 2.6 Update `src/agents/translator.py` to set `effort="low"` and pass configured `instance_id`.

## Phase 3: Zero-Quota Testing & Unit Test Coverage
- [x] 3.1 Author mock unit tests for persistent NDJSON streaming client (`AgyStreamClient`) lifecycle and pipe handling in `tests/unit/test_native_agents.py`.
- [x] 3.2 Author unit tests for `google.antigravity` SDK fallback and configuration dispatch in `tests/unit/test_native_agents.py`.
- [x] 3.3 Author multi-instance isolation unit tests verifying independent AppData paths and per-instance `CircuitBreaker` states in `tests/unit/test_native_agents.py`.
- [x] 3.4 Author unit tests for trajectory cleanup (`cleanup_ephemeral_sessions`) and process timeout handling in `tests/unit/test_native_agents.py`.
- [x] 3.5 Run `pytest tests/unit/test_native_agents.py tests/unit/test_agents.py` to verify 100% offline pass rate.

## Phase 4: Documentation & Secrets Policy
- [x] 4.1 Update `docs/AGENTES_IA_Y_POLITICA.md` with persistent NDJSON stream harness architecture, Pro OAuth session bridge details, and zero-quota test isolation.
- [x] 4.2 Update `docs/CONFIGURACION_SECRETOS.md` with secondary OAuth session setup, token isolation in `.bot_home/.gemini/antigravity-cli`, and environment variable configuration.
- [x] 4.3 Run `pytest tests/unit/test_docs_integrity.py` to confirm documentation and reference consistency.
