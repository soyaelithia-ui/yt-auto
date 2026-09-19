# Agent Directives and Inviolable Project Governance

## 1. Project Invariants and Mandatory Cadence Check
- Every **25 commits** or before starting any major work or pipeline execution, you MUST execute `./scripts/verify_integrity.sh`.
- **Mandatory Work Refusal (Kill Switch)**: If `./scripts/verify_integrity.sh` returns any failure (code 1), you MUST REFUSE TO PROCEED with feature work or video generation. Stop, alert the user, and resolve the regression.
- **Zero-Browser Policy**: Absolutely zero `playwright` or `chromium` imports in `src/media/`, `src/cli/`, `src/narrative/`, or `src/core/`. Playwright is restricted to `src/youtube/` exclusively for fallback session uploads.
- **Zero Resurrected Docs**: Absolutely zero legacy architecture blueprints in `docs/architecture/0*.md` or retired modules (`src/rendering/`, `src/compositing/`, `src/export/`).

## 2. Product Value Priority vs. Premature Refactoring
- **Ship Production Value First**: Prioritize functional video publishing and measurable audience quality over cosmetic code slimming or aesthetic refactors.
- **Refactoring Prohibition**: Never undertake massive rewrites or module mergers in working `src/` code solely to decrease line count if tests pass and performance contracts are met.
- **Anti-Bloat Policy**: Never commit minified libraries (`*.min.js`), third-party tools, or vendored skills (e.g. dozens of `.mjs` files) to this repository. The pre-commit hook (`.githooks/pre-commit`) will strictly reject them.

## 3. Security, Credentials & Memory Governance
- **Zero Secrets in Memory**: Never persist credentials, OAuth tokens, API keys, cookies, cookie jars, `.env` values, or secrets into Engram, agent notes, session summaries, or logs. Always redact (`[REDACTED]`).
- **Zero Live Literals**: Never commit real credentials in source, tests, fixtures, mocks, or audit scripts. Do not use live secrets as regex needles. Use generic format signatures or runtime-built synthetic tokens. Never print matched secrets in logs or assertion messages.
- **Zero Agent Homedirs in Git**: Never add `.codex/`, `.claude/`, `.gemini/`, `.agents/`, `.opencode/`, `.cursor/`, `.hermes/`, or similar agent homes (including `hooks.json`). They are local-only; `.gitignore` and the pre-commit hook must reject them.
- **Residual History Risk**: Rotated literals MAY remain in git objects and stale refs. History rewrite is not required.
- **Strict Project Isolation**: Keep agent context, memory operations, and commands bound strictly to this project (`yt-auto`). Never read, write, or leak files outside the yt-auto workspace root (including `~/.ssh`, `~/.config`, sibling repositories, and unrelated directories).
- **Environment Isolation**: `.env`, `cookies.json`, and database state files remain local, untracked, and strictly non-extractable.
- **Leak Response**: If credentials leak, do not file a public issue. Make the GitHub repository private, invalidate the affected GCP project/APIs, rotate every credential, and keep scanners green before resuming production.

## 4. Concurrent Agent Worktrees
- Use `scripts/agent_worktree.sh` for create, force-remove, list, and prune. It MUST NOT delete or alter the primary repository checkout under any cleanup flag or argument error.
- `scripts/setup_worktree_env.sh` MUST idempotently link `.venv`, `.agents`, and `.env` into derived worktrees using safe relative (fallback absolute) paths. Never print secret file contents.
- Prefer shipping production video value over cosmetic refactors; do not rewrite working `src/` solely to slim line count when tests and performance contracts already pass.

## 5. Strict Resource Target & Performance Budget (2 Cores, 2 GB RAM)
- **Hard Target Ceiling (Meta Objetivo)**: All pipeline workflows, background daemons, and media processing MUST operate within a target ceiling of **≤ 2 CPU Cores** (≤ 200% across all concurrent threads) and **≤ 2.0 GiB RAM** (2,048 MiB peak memory). Docker cgroups maintain an emergency margin (`cpus: 4.0`, `mem_limit: 6g`) solely to prevent premature OOM-kills, but software design and agents must treat 2 Cores and 2 GB RAM as the inviolable operational envelope.
- **Monotonic Optimization Directive**: Resource consumption must only decrease or remain stable over time; it must NEVER spike or climb across commits. Agents must actively seek lower CPU and memory footprints where logically possible and viable without degrading output quality.
- **Mandatory Resource Guardrails**:
  - FFmpeg execution must strictly bound threads (`-threads 2` on QA probes, max `-threads 4` on renders).
  - Video composition must prioritize Stream-Copy (`-c:v copy`) to avoid CPU-intensive re-encoding.
  - Media analysis and loudness probes must skip decoding video frames using `-vn`.
  - In-memory video/audio buffers or raw image loops (e.g. unconstrained Pillow loops) are strictly prohibited; stream assets from disk.
  - Concurrency is bounded by semaphores (`_SHORT_RENDER_SEMAPHORE = 2`, `_LONG_RENDER_SEMAPHORE = 1`).
- **Resource Work Refusal**: If any architectural change, library, dependency, or feature causes steady-state or peak resource usage to exceed the 2 Cores / 2 GB RAM target ceiling, agents MUST REFUSE the change and optimize the implementation before merging.

## 6. Architecture & Directory Responsibility Map (Single Line per Directory)
- `src/`: Root application source containing entrypoints and shared subsystems.
- `src/agents/`: Multi-agent orchestration for script curation, art direction, and scene planning.
- `src/analytics/`: Channel performance tracking, viewer retention metrics, and publication logs.
- `src/audio/`: Voice synthesis (Edge TTS), ambient drones, SFX catalog, and audio ducking chains.
- `src/cli/`: Command-line interface parsers, argument dispatchers, and subcommands (`main.py`).
- `src/core/`: Domain models, SQLite queue repositories, concurrency locks, and scheduling budgets.
- `src/curators/`: Editorial beat algorithms, horror/drama curation rules, and topic adapters.
- `src/mcp/`: Model Context Protocol server exposing tools, resources, and prompts for AI agents.
- `src/media/`: Video composition engines (stream-copy, loops, multi-act renderers, ASS subtitles).
- `src/narrative/`: Story generation archetypes, JSON schemas, and narrative coherence evaluation.
- `src/observability/`: System metrics, structured events, alert dispatching, and crash bundles.
- `src/orchestrator/`: Multi-channel batch scheduling, queue dispatching, and daemon lifecycle coordination.
- `src/telegram/`: Telegram notifications, status webhooks, and HITL review bot integration.
- `src/templates/`: Script prompt templates, narrative archetypes, and story generators.
- `src/verification/`: Video quality assurance probes, black frame detectors, and audio loudness checks.
- `src/visuals/`: Scene asset tracking and image metadata validation.
- `src/youtube/`: YouTube Data API v3 client, OAuth lifecycle, and fallback session uploader.
- `review/`: Telegram HITL review bot, approval state machine, proxy video generation, and publication gate.
- `tests/`: Automated test suites categorized by scope (unit, integration, e2e, live).
- `scripts/`: Shell and Python maintenance, integrity gates, worktree managers, and pre-commit hooks.
- `config/`: Channel profiles, editorial rules, lane matrices, and voice configs.
- `data/`: Local SQLite databases, loop catalogs, locks, and temporary run state.
- `assets/`: Physical loops, backgrounds, music stems, fonts, and SVG overlays.
- `docs/`: Technical specifications, architecture blueprints, operations manuals, and MCP references.
- `deploy/`: Headless background service runners, tmux session orchestrators, and production process supervision.
- `schemas/`: JSON schemas for configuration, story formats, and validation contracts.

## 7. Exact Operational Commands
- **Environment Setup**:
  ```bash
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements-dev.txt -c constraints.txt
  git config core.hooksPath .githooks && chmod +x .githooks/pre-commit
  ```
- **Integrity & Guardrail Validation (Mandatory)**:
  ```bash
  ./scripts/verify_integrity.sh
  ```
- **MCP Parity & Drift Check**:
  ```bash
  .venv/bin/python3 scripts/verify_mcp_sync.py
  ```
- **Fast Anti-Regression Suite (REG-01 to REG-14)**:
  ```bash
  .venv/bin/pytest tests/unit/test_anti_regression_guardrails.py -v
  ```
- **Security & Secret Hygiene Suite**:
  ```bash
  .venv/bin/pytest tests/unit/test_security_policies.py -v
  ```
- **Targeted Unit Test Execution**:
  ```bash
  .venv/bin/pytest tests/unit/test_mcp_server.py -v
  .venv/bin/pytest tests/unit/test_domain.py tests/unit/test_security_policies.py -v
  .venv/bin/pytest tests/unit/ -q
  ```
- **Formatting / Lint Check**:
  ```bash
  .venv/bin/python3 -m py_compile src/**/*.py
  ```

## 8. Immutable Agent-Native Coding Rules
1. **Granularity & Function Line Budget (~100 lines)**:
   - Every module should focus on a single responsibility (SRP).
   - Functions and methods MUST NOT exceed ~100 lines of executable logic. Break complex workflows into discrete pipeline stages or helper functions.
2. **Strict Static Typing & Data Contracts**:
   - All public interfaces, pipeline stages, and MCP tool handlers MUST include explicit type hints (`typing`, `Pydantic` models, or `@dataclass(slots=True)`).
   - Prohibit untyped generic dictionaries (`dict[str, Any]`) for inter-stage data transfer; use strongly-typed schemas (`PipelineContext`, `StoryRecord`, `RenderSpec`).
3. **Zero Blocking / Interactive Logic**:
   - The system must execute 100% autonomously and non-interactively in headless daemon/agent environments.
   - Prohibit `input()`, unbuffered blocking `sys.stdin.read()`, or interactive terminal prompts in `src/`.
   - All subprocess calls (FFmpeg, Playwright, curl) MUST define explicit timeouts and non-zero exit handlers.
4. **Deterministic Self-Verification Cycles**:
   - Every code modification must be verified using `./scripts/verify_integrity.sh` and targeted unit tests.
   - If tests fail, agents must roll back changes or fix regressions deterministically before declaring completion.

## 9. Canonical Entrypoints & Key Data Contracts
- **CLI Entrypoints**:
  - `main.py`: Unified CLI entrypoint with profile preparsing, signal handlers, and command dispatching (`main.py run --lane <id>`, `main.py daemon`, `main.py mcp`).
  - `manage.py`: Compatibility forwarding facade delegating directly to `main.py`.
- **MCP Server Harness (`src/mcp/`)**:
  - Entrypoint: `python3 -m src.mcp` or `create_mcp_server()`.
  - Canonical Tools (9): `system_preflight`, `list_lanes`, `get_lane_info`, `query_loop_catalog`, `audit_loop_catalog`, `run_pipeline_dry_run`, `get_system_status`, `manage_queue`, `verify_integrity`.
  - Canonical Resources (3): `channels://{channel_name}/config`, `lanes://catalog`, `system://health`.
  - Canonical Prompts (3): `preflight_diagnostics`, `channel_incident_analysis`, `video_qa_review`.
- **Review & HITL Entrypoints**:
  - `review/telegram_bot.py`: `TelegramReviewBot` handling review notifications, video proxy delivery, and operator callbacks.
  - `src/telegram/approval.py`: `ReviewJobManager` and auto-publish sweeps with 2-hour rejection windows.
- **Key Domain Contracts**:
  - `src/core/domain.py`: `Story`, `StoryStatus`, `JobStatus`, `ChannelConfig`.
  - `src/core/repository.py`: `QueueRepository` managing database operations, queue state, and worker leases.
  - `src/core/db_reconciler.py`: `DBReconciler` coordinating two-phase transactions across `shorts_queue.db` and `review_state.db`.
  - `src/core/lanes.py`: `LaneProfile`, cadence configs, visual layout specs, and duration targets.
  - `src/media/interface.py`: `BaseVideoCompositor` abstraction enforcing stream-copy or low-CPU composition.
  - `review/domain.py`: `ReviewJob`, `ReviewStatus`, `DeliveryResult`.
