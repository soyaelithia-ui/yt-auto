# Tasks: Add Antigravity Docker Integration, Official Installer & Pro Quota Harness

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 380–480 lines |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Dockerfile Official Installer & Staging Decommissioning) → PR 2 (Pro Quota Harness & Clean Session) → PR 3 (Graceful Quota Fallback) → PR 4 (Guardrail Tests Modernization) → PR 5 (Documentation & Full Integrity Verification) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Dockerfile Official Installer & Staging Decommissioning (remove `scripts/stage_agy.sh`, install `agy` via `curl -fsSL https://antigravity.google/cli/install.sh`, align `docker-compose.yml`, and update `scripts/docker_entrypoint.sh`) | PR 1 (base: `feature/add_antigravity_docker`) | `.venv/bin/pytest tests/unit/test_docker_isolation.py` | `docker compose config` | `scripts/stage_agy.sh`, `Dockerfile`, `docker-compose.yml`, `scripts/docker_entrypoint.sh` |
| 2 | Pro Quota Harness & Clean Session (maintain `agy` CLI as primary Pro quota engine in `src/agents/base_agent.py`, eliminate binary byte scraping in `scripts/lib/antigravity_auth.py`, verify volume session) | PR 2 (base: PR 1 branch) | `.venv/bin/pytest tests/unit/test_native_agents.py tests/unit/test_antigravity_host_isolation.py` | `python -c "from src.agents.base_agent import ProgrammaticAgent; agent = ProgrammaticAgent(); print(agent.role_name)"` | `src/agents/base_agent.py`, `scripts/lib/antigravity_auth.py` |
| 3 | Resilient Quota Fallback (procedural storytelling and deterministic SEO fallback on HTTP 429 / saturation) | PR 3 (base: PR 2 branch) | `.venv/bin/pytest tests/unit/test_native_agents.py -k "fallback or quota or saturation"` | `python -c "from src.agents.story_director import StoryDirectorAgent; StoryDirectorAgent().circuit_breaker.record_failure('429'); print(StoryDirectorAgent().generate_story('test', 'moku')['status'])"` | `src/agents/story_director.py`, `src/agents/seo_optimizer.py`, `src/llm.py` |
| 4 | Guardrail & Isolation Test Modernization (update isolation assertions, add Threat Matrix RED tests, fix channel aliases, verify 100% pass) | PR 4 (base: PR 3 branch) | `.venv/bin/pytest tests/unit/test_docker_isolation.py tests/unit/test_antigravity_host_isolation.py tests/unit/test_native_agents.py` | `.venv/bin/pytest tests/unit/` | `tests/unit/test_docker_isolation.py`, `tests/unit/test_antigravity_host_isolation.py`, `tests/unit/test_native_agents.py` |
| 5 | Operational Documentation & Verification (update operations, troubleshooting, and agent governance docs; run `./scripts/verify_integrity.sh`) | PR 5 (base: PR 4 branch) | `./scripts/verify_integrity.sh` | `./scripts/verify_integrity.sh` | `docs/OPERACION.md`, `docs/TROUBLESHOOTING.md`, `docs/AGENTES_IA_Y_POLITICA.md` |

---

## Phase 1: Dockerfile Official Installer & Staging Decommissioning

- [x] 1.1 Delete `scripts/stage_agy.sh` to permanently eliminate the host ELF binary staging mechanism and decouple image builds from developer local binaries.
- [x] 1.2 Update `Dockerfile` to install Antigravity CLI via the official bootstrapper `curl -fsSL https://antigravity.google/cli/install.sh | bash -s -- --dir /usr/local/bin && chmod 755 /usr/local/bin/agy`, remove `COPY build/agy /usr/local/bin/agy`, and ensure `google-antigravity==0.1.10` in `requirements.txt` (read-only) is installed into the Python container image.
- [x] 1.3 Update `docker-compose.yml` to preserve `AGY_BIN: /usr/local/bin/agy` pointing to the official installed binary, enforce non-root user `user: "10001:10001"` in `x-yt-base`, verify persistent session volume `yt_agy_home:/home/appuser/.gemini`, pass through `GEMINI_API_KEY: ${GEMINI_API_KEY:-}`, and align channel daemon service aliases (`yt-moku` and `yt-aelithia`).
- [x] 1.4 Update `scripts/docker_entrypoint.sh` to verify `/usr/local/bin/agy` exists from container installation, enforce non-root execution (`uid != 0`), and validate write permissions for required application directories (`/app/data`, `/app/work`, `/app/artifacts`, `/app/logs`, `/app/output`, `/tmp`, `/home/appuser/.gemini`).

---

## Phase 2: Pro Quota Harness & Clean Session Governance

- [x] 2.1 Update `src/agents/base_agent.py` to prioritize `AgyStreamClient` CLI invocation for Antigravity Pro subscription quota consumption, keeping SDK as secondary when `USE_ANTIGRAVITY_SDK=1` and `GEMINI_API_KEY` are explicitly configured.
- [x] 2.2 Fix policy import in `src/agents/base_agent.py` by changing `from google.antigravity import LocalAgentConfig, policy` to `from google.antigravity import LocalAgentConfig` and `from google.antigravity.hooks import policy`.
- [x] 2.3 Decommission binary string parsing and `docker cp` injection in `scripts/lib/antigravity_auth.py`, removing references to `build/agy` (read-only) and host `/home/moku/.local/bin/agy` (read-only) in compliance with Google ToS.
- [x] 2.4 Update `_seed_appdata_from_secrets` in `src/agents/base_agent.py` to allow clean session loading from mounted volumes (`/home/appuser/.gemini`) without crashing when host token secrets are absent.

---

## Phase 3: Graceful Quota Fallback

- [x] 3.1 Update `_run_async` in `src/agents/base_agent.py` to catch CLI and SDK quota exhaustion errors (HTTP 429, `RESOURCE_EXHAUSTED`, `AgentSaturationError`), record failure on `self.circuit_breaker` (300s cooldown), and return a saturated result envelope (`status="saturated"`) instead of raising unhandled exceptions.
- [x] 3.2 Update `generate_story` in `src/agents/story_director.py` to inspect `self.circuit_breaker.is_open()` and handle `"saturated"` status or quota saturation exceptions by gracefully invoking procedural narrative templates (`_procedural_fallback_story`) from `src/templates/narratives.py` (read-only) rather than raising fatal `AIProviderChainExhausted`.
- [x] 3.3 Update `optimize` in `src/agents/seo_optimizer.py` to detect open circuit breaker or quota saturation, seamlessly falling back to `_deterministic_seo` with channel-compliant metadata without aborting on `fail_closed=True`.
- [x] 3.4 Update `curate_script` in `src/llm.py` to catch quota saturation and provider chain exhaustion, falling back to queued narrative content or channel templates when LLM providers fail due to quota limits.

---

## Phase 4: Guardrail & Isolation Test Modernization

- [x] 4.1 (RED Test) Add adversarial test `test_entrypoint_does_not_execute_arbitrary_scripts` in `tests/unit/test_docker_isolation.py` (Threat Matrix boundary: documentation-like paths & executable scripts in volumes) verifying `scripts/docker_entrypoint.sh` (read-only) does not execute arbitrary scripts or documentation files in `/app/work` or `/app/data`.
- [x] 4.2 Update `tests/unit/test_docker_isolation.py` to assert that `scripts/stage_agy.sh` (read-only) is absent, `build/agy` (read-only) is not required, `Dockerfile` (read-only) installs `agy` via `curl -fsSL https://antigravity.google/cli/install.sh`, and channel aliases match service specifications.
- [x] 4.3 Update `tests/unit/test_antigravity_host_isolation.py` to verify container isolation without host binary scraping or hardcoded host paths.
- [x] 4.4 Update `tests/unit/test_native_agents.py` to add unit tests for `ProgrammaticAgent` with CLI Pro harness, mock HTTP 429 / `RESOURCE_EXHAUSTED` tripping `CircuitBreaker`, and verify graceful procedural fallback in `src/agents/story_director.py` (read-only) and `src/agents/seo_optimizer.py` (read-only).
- [x] 4.5 Execute unit tests via `.venv/bin/pytest tests/unit/test_docker_isolation.py tests/unit/test_antigravity_host_isolation.py tests/unit/test_native_agents.py` (read-only) to verify 100% pass rate.

---

## Phase 5: Verification & Documentation

- [x] 5.1 Update `docs/OPERACION.md` to remove Step 3 (`scripts/stage_agy.sh` (read-only)), document the official installer and clean session volume workflow with Antigravity Pro quota, and update channel service profiles.
- [x] 5.2 Update `docs/TROUBLESHOOTING.md` to remove troubleshooting entries for `build/agy: not found`, documenting Antigravity Pro session verification and procedural fallback monitoring.
- [x] 5.3 Update `docs/AGENTES_IA_Y_POLITICA.md` to document Pro quota priority, official CLI installer, and graceful procedural quota fallback policy.
- [x] 5.4 Execute `scripts/verify_integrity.sh` (read-only) and full test suite `.venv/bin/pytest tests/` (read-only) to confirm complete system integrity and compliance with REG-14 production standards.
