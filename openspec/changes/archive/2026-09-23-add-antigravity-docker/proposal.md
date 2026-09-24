# Proposal: Add Antigravity Docker Integration, Official Installer & Pro Quota Harness

## Intent

Production execution and container builds encountered critical halts stemming from three interrelated systemic issues:

1. **Quota / Rate Limits Tripping Circuit Breaker (`RESOURCE_EXHAUSTED` / 429)**:
   When API calls hit provider rate limits, daily quotas, or returned `RESOURCE_EXHAUSTED` (HTTP 429), the `CircuitBreaker` in `src/agents/base_agent.py` tripped open (defaulting to a 300-second cooldown). Under previous `editorial-and-content-policy` specifications, the system enforced strict fail-closed behavior (`AIProviderChainExhausted`). This caused autonomous daemon workers (`daemon.py`) to abort completely instead of gracefully switching to procedural storytelling or deterministic algorithmic SEO, blocking subsequent scheduled video publishing.

2. **Brittle Host Staging Dependency (`scripts/stage_agy.sh` & `build/agy`)**:
   The Docker build pipeline relied on an external host staging script (`scripts/stage_agy.sh`) to copy a pre-compiled Linux ELF binary from the developer's host directory (`/home/moku/.local/bin/agy`) into `build/agy`. The `Dockerfile` contained a hard requirement `COPY build/agy /usr/local/bin/agy`. In headless CI/CD, fresh VPS environments, or clean checkouts where `agy` was not pre-installed on the host, `docker compose build` failed with `build/agy: not found`. Rather than copying from the host, the official installer (`curl -fsSL https://antigravity.google/cli/install.sh | bash -s -- --dir /usr/local/bin`) must be used inside `Dockerfile` to install and auto-update `agy` cleanly.

3. **Preserving Antigravity Pro Quota (No Raw API Billing) Without Dangerous Token Scraping**:
   The fundamental motivation for integrating Antigravity is to access the user's **Antigravity Pro subscription quota** (`gemini-3.8-flash-high`) without paying per-token API costs or hitting strict free API rate limits. However, the system previously attempted to maintain sessions by reverse-engineering client credentials from the binary and running an external PKCE helper (`scripts/lib/antigravity_auth.py`) with `docker cp`. In containerized environments, binary scraping violates Google ToS and breaks on updates. The container must cleanly persist the user's legitimate Antigravity CLI session via the dedicated volume mount (`yt_agy_home:/home/appuser/.gemini`), allowing `agy` to consume Pro quotas safely and update its own tokens natively.

This change permanently decouples container execution from host files, installs the Antigravity CLI natively in Docker via the official installation script (`https://antigravity.google/cli/install.sh`), standardizes `agy` as the primary harness for Antigravity Pro quota, retains the Python SDK (`google-antigravity`) as an optional secondary path, and integrates seamless procedural fallback for storytelling and SEO when API/Pro quotas are exhausted.

---

## Scope

### In Scope
- **Docker & Container Runtime Modernization**:
  - Update `Dockerfile` to install Google Antigravity CLI natively using the official bootstrapper:
    `curl -fsSL https://antigravity.google/cli/install.sh | bash -s -- --dir /usr/local/bin`.
  - Install `google-antigravity==0.1.10` in `requirements.txt` for Python typing and auxiliary SDK support.
  - Remove `COPY build/agy` from `Dockerfile`.
  - Update `scripts/docker_entrypoint.sh` to verify `/usr/local/bin/agy` is installed, permissions are valid, and dropped to UID `10001`.
  - Discard `scripts/stage_agy.sh` and eliminate `build/agy`.
- **Pro Quota Prioritization & Clean Session Governance**:
  - Maintain `agy` CLI as the primary execution engine (`ProgrammaticAgent`) to consume the user's Pro account quota.
  - Decommission binary credential scraping and `docker cp` injection in `scripts/lib/antigravity_auth.py` (strict ToS compliance).
  - Persist legitimate authorized sessions cleanly via `yt_agy_home:/home/appuser/.gemini`.
- **Seamless Procedural & Deterministic Quota Fallback**:
  - Update `ProgrammaticAgent`, `src/agents/story_director.py`, `src/agents/seo_optimizer.py`, and `src/llm.py` so that when saturation/429 occurs or circuit breakers open, the pipeline gracefully falls back to template/procedural script generation and deterministic SEO formulas without crashing the daemon.
- **Guardrail & Isolation Test Suite Alignment**:
  - Update `tests/unit/test_docker_isolation.py` to assert that `scripts/stage_agy.sh` and `build/agy` are NOT required, and that the image installs `agy` via the official installer.
  - Update `tests/unit/test_antigravity_host_isolation.py` to verify container isolation without host binary scraping.
  - Update documentation (`docs/OPERACION.md`, `docs/TROUBLESHOOTING.md`, `docs/AGENTES_IA_Y_POLITICA.md`).

### Out of Scope
- Altering core FFmpeg video rendering or audio mastering pipelines.
- Modifying YouTube data API upload mechanisms or Google Drive backup connectors.

---

## Capabilities

### New Capabilities
- `docker-antigravity-runtime`: Self-contained containerized execution of Google Antigravity in Docker via the official CLI installer (`curl -fsSL https://antigravity.google/cli/install.sh`), non-root isolation (`USER 10001:10001`), Pro quota consumption through clean volume session mounting, and zero host binary staging.

### Modified Capabilities
- `editorial-and-content-policy`: Update the AI-first curation and fail-closed requirement to allow seamless procedural storytelling and deterministic SEO fallback when LLM quotas (`RESOURCE_EXHAUSTED`, 429) or circuit breakers trip, preventing daemon pipeline stalls while maintaining content quality.

---

## Approach

1. **Adopt Official Antigravity CLI Installer in Docker**:
   In `Dockerfile`, replace `COPY build/agy /usr/local/bin/agy` with `curl -fsSL https://antigravity.google/cli/install.sh | bash -s -- --dir /usr/local/bin && chmod 755 /usr/local/bin/agy`. This guarantees the CLI is installed cleanly during image builds, auto-updates on rebuilds, and requires zero host staging.

2. **Prioritize Pro Quota via the CLI Harness**:
   `ProgrammaticAgent` in `src/agents/base_agent.py` uses `AgyStreamClient` / CLI invocation as the primary Provider A engine to execute prompts under the user's Pro account subscription quota without incurring per-token API charges.

3. **Decommission Binary Scraping & Clean Session Governance**:
   Remove `scripts/stage_agy.sh`. In `scripts/lib/antigravity_auth.py`, decommission binary string parsing (`_extract_embedded_credential`). Sessions are cleanly maintained via the Docker volume `yt_agy_home:/home/appuser/.gemini`.

4. **Implement Resilient Procedural & Deterministic Fallback**:
   When API limits, rate limits (HTTP 429), or quota exhaustion occur:
   - Trip the instance `CircuitBreaker` (300-second cooldown).
   - In `StoryDirectorAgent`, fall back to vetted procedural narrative templates (`src/templates/narratives.py`).
   - In `SeoOptimizerAgent`, fall back to `_deterministic_seo(topic, fmt, niche)`.
   - Prevent fatal daemon stops and continue 24/7 autonomous publishing.

5. **Align Guardrail Tests**:
   Update `tests/unit/test_docker_isolation.py` and `tests/unit/test_antigravity_host_isolation.py` to assert the official installer is used, host binaries are never staged, and container isolation is preserved.

---

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `Dockerfile` | Modified | Install `agy` via `curl -fsSL https://antigravity.google/cli/install.sh | bash -s -- --dir /usr/local/bin`; remove `COPY build/agy` |
| `docker-compose.yml` | Modified | Retain `yt_agy_home:/home/appuser/.gemini` volume; ensure `AGY_BIN: /usr/local/bin/agy` points to installed CLI |
| `scripts/docker_entrypoint.sh` | Modified | Verify `/usr/local/bin/agy` exists from container installation; drop root to UID 10001; check volume writability |
| `scripts/stage_agy.sh` | Removed | Eliminate host ELF copying script |
| `scripts/lib/antigravity_auth.py` | Modified | Remove binary byte-scraping and `docker cp` injection; deprecate unsafe PKCE helpers |
| `src/agents/base_agent.py` | Modified | Maintain `agy` CLI as primary Pro quota engine; support optional SDK; catch 429/saturation errors |
| `src/agents/story_director.py` | Modified | Add graceful fallback to template storytelling upon quota saturation |
| `src/agents/seo_optimizer.py` | Modified | Ensure fallback to `_deterministic_seo` when circuit breaker is open or quota exhausted |
| `src/llm.py` | Modified | Allow procedural narrative fallback when LLM quota is exhausted |
| `tests/unit/test_docker_isolation.py` | Modified | Update tests to assert absence of `stage_agy.sh` dependency and clean Dockerfile installer |
| `tests/unit/test_antigravity_host_isolation.py` | Modified | Remove requirements for `antigravity-oauth-token` scraping in secrets |
| `tests/unit/test_native_agents.py` | Modified | Unit tests for CLI Pro harness, SDK path, and graceful quota fallback |
| `docs/OPERACION.md` | Modified | Document official installation and clean session volume workflow |
| `docs/TROUBLESHOOTING.md` | Modified | Update troubleshooting guides for Antigravity Pro quota and session refresh |
| `docs/AGENTES_IA_Y_POLITICA.md` | Modified | Document Pro quota priority and procedural fallback policy |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `antigravity.google` installer temporarily unreachable during Docker build | Low | The official installer endpoint is hosted on Google infrastructure with high availability; layer caching avoids re-downloading on unchanged builds. |
| User session in `yt_agy_home` expires | Low | Document clean re-login command (`docker compose run --rm yt-automation agy auth login`) or session directory mount; fallback seamlessly to procedural narratives if session drops. |
| Procedural fallback producing repetitive narrative formats | Medium | Use diverse template pools (`HORROR_STORIES`, `DRAMA_STORIES`) and dynamic hook variations already present in `src/templates/` and `src/branding.py`. |

---

## Rollback Plan

1. Revert the branch commits cleanly via `git revert`.
2. No SQLite database schema migrations are altered by this change.
3. Execute `.venv/bin/pytest tests/unit/test_docker_isolation.py tests/unit/test_antigravity_host_isolation.py` to verify baseline integrity.

---

## Dependencies

- Python 3.12 / 3.13 runtime.
- Antigravity CLI installed in container via `curl -fsSL https://antigravity.google/cli/install.sh`.
- Antigravity Pro account subscription session mounted in `/home/appuser/.gemini`.

---

## Success Criteria

- [ ] `scripts/stage_agy.sh` is removed and `Dockerfile` builds without requiring `build/agy`.
- [ ] `Dockerfile` installs `agy` via `curl -fsSL https://antigravity.google/cli/install.sh | bash -s -- --dir /usr/local/bin`.
- [ ] `scripts/docker_entrypoint.sh` starts under UID `10001` with valid `/usr/local/bin/agy`.
- [ ] `src/agents/base_agent.py` executes tasks via `agy` CLI to consume the user's Pro quota.
- [ ] No binary credential scraping exists in `scripts/lib/antigravity_auth.py`.
- [ ] Quota exhaustion (429) or open circuit breaker triggers graceful procedural storytelling and deterministic SEO fallback instead of terminating daemon execution.
- [ ] `tests/unit/test_docker_isolation.py` and `tests/unit/test_antigravity_host_isolation.py` pass 100%.
- [ ] `./scripts/verify_integrity.sh` passes completely.
