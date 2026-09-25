# Tasks: Documentation Coherence, Accuracy, and Compact Optimization

## Review Workload Forecast

| Field | Value |
| :--- | :--- |
| Estimated changed lines | ~850 - 1,150 lines across 16 documentation and tracking files (net line reduction: -188 lines in `ACTIVE_DOCS` to achieve ~806 lines, establishing a ~194-line safety buffer below the 1000-line budget ceiling) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Chain strategy | feature-branch-chain |
| Delivery strategy | ask-on-risk |
| Decision needed before apply | No |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Core Architecture, Navigation & Pipeline Flow Docs | PR 1 | `.venv/bin/pytest tests/unit/test_docs_integrity.py -k "test_all_relative_links_resolve or test_code_blocks_are_tagged"` | Documentation link checker & markdown parser harness | Revert `docs/README.md`, `docs/ARQUITECTURA.md`, `docs/FLUJO_VIDEOS.md`, `docs/MULTICHANNEL_PIPELINE.md` |
| 2 | Agent Subsystem, Governance & Operations Compaction | PR 2 | `.venv/bin/pytest tests/unit/test_docs_integrity.py -v` | In-memory line counter & ast-based agent import verifier | Revert `docs/AGENTES_IA_Y_POLITICA.md`, `docs/POLITICA_GOBERNANZA_ANTI_REGRESION.md`, `docs/OPERACION.md`, `docs/CONFIGURACION_SECRETOS.md`, `docs/INTEGRACIONES_Y_SERVICIOS.md`, `docs/TROUBLESHOOTING.md`, `docs/REFERENCIAS_Y_VERSIONES.md` |
| 3 | Visual Architecture Plans & Low-CPU Compaction | PR 3 | `.venv/bin/pytest tests/unit/test_architectural_specs.py tests/unit/test_anti_regression_guardrails.py -k "TestResourceTargetGovernanceGuardrails or test_plan_maestro" -v` | Architectural specification regex validator & REG-14 invariant test fixture | Revert `docs/PLAN_MAESTRO_PIPELINE_VISUAL.md`, `docs/PROPUESTA_EVOLUCION_PIPELINE_VISUAL.md`, `docs/FFMPEG_LOW_CPU.md` |
| 4 | Root Documentation & Project Roadmap Alignment | PR 4 | `.venv/bin/pytest tests/unit/test_docs_integrity.py tests/unit/test_architectural_specs.py -k "test_root_project_and_test_infra_docs_exist or test_total_lines_budget_under_1000" -v` | Root markdown validator & line budget accumulator | Revert `README.md`, `PROJECT.md` |
| 5 | Full Repository Verification & Integrity Hardening Gate | PR 5 | `.venv/bin/pytest tests/unit/test_docs_integrity.py tests/unit/test_anti_regression_guardrails.py tests/unit/test_architectural_specs.py -v && python3 scripts/verify_mcp_sync.py && ./scripts/verify_integrity.sh` | Full verification suite, MCP sync checker, and repository integrity gate | Revert verification scripts / test fixtures |

---

## Implementation Tasks

### Phase 1: Core Architecture, Navigation & Pipeline Flow Docs

- [x] 1.1 **[DOC]** Reconcile canonical lane catalog and guardrail scope in `docs/ARQUITECTURA.md`:
  - Update the Section 2 Production Lanes catalog table to enumerate all 6 canonical lanes declared in `config/lanes.json`:
    - `horror-scp-shorts`: Channel `horror`, vertical 9:16 (`1080x1920`), story type `scp`, enabled `true`.
    - `horror-horror-long`: Channel `horror`, horizontal 16:9 (`1920x1080`), story type `horror`, enabled `true`.
    - `drama-drama-shorts`: Channel `drama`, vertical 9:16 (`1080x1920`), story type `reddit_aita`, enabled `true`.
    - `drama-aita-long`: Channel `drama`, horizontal 16:9 (`1920x1080`), story type `reddit_aita`, enabled `true`.
    - `scifi-singularity-shorts`: Channel `scifi`, vertical 9:16 (`1080x1920`), story type `scifi`, enabled `false` (pre-configured).
    - `scifi-singularity-long`: Channel `scifi`, horizontal 16:9 (`1920x1080`), story type `scifi`, enabled `false` (pre-configured).
  - Eliminate deprecated lane identifiers (`horror-long`, `drama-shorts`).
  - Update Section 5 Agent Subsystem summary to cite the 6 active canonical modules in `src/agents/`.
  - Update Section 9 Anti-Regression Suite citation from REG-13 to `"REG-01 a REG-14"` in parity with `tests/unit/test_anti_regression_guardrails.py`.
  - Compact prose and table wrapping to reduce line count from 117 to $\le 92$ lines.
  - Concrete target: `docs/ARQUITECTURA.md`.

- [x] 1.2 **[DOC]** Reorder execution stages into sequential ascending order in `docs/FLUJO_VIDEOS.md`:
  - Reorganize both the Mermaid execution flowchart and the descriptive specification table to strictly adhere to ascending sequential stages 01 through 13 in `src/pipeline/stages/`:
    - Stage 01: Adjudicación y Lease (`stage_01_lease.py`)
    - Stage 02: Ingesta y Curación (`stage_02_ingest.py`)
    - Stage 03: Sanitización Editorial (`stage_03_editorial.py`)
    - Stage 04: Configuración Visual & Categoría de Loop (`stage_04_mood.py`)
    - Stage 05: Síntesis TTS y Audio (`stage_05_tts.py`)
    - Stage 06: Alineación de Duración (`stage_06_alignment.py`)
    - Stage 07: Subtítulos Karaoke ASS (`stage_07_subtitles.py`)
    - Stage 08: Resolución de Loop de Catálogo (`stage_08_loop.py`)
    - Stage 09: Composición Lineal & Render Stream-Copy (`stage_09_render.py`)
    - Stage 10: Compuerta QA Integral Pre-publicación (`stage_10_qa.py`)
    - Stage 11: Miniatura Local Determinista & Metadatos (`stage_11_metadata.py`)
    - Stage 12: Deduplicación Criptográfica & SimHash (`stage_12_simhash.py`)
    - Stage 13: Veredicto Técnico & Publicación YouTube (`stage_13_publish.py`)
  - Ensure Stage 04 strictly precedes Stage 05, Stage 10 strictly precedes Stage 11, and Stage 12 strictly precedes Stage 13.
  - Compact table formatting and transitions to reduce line count from 56 to $\le 52$ lines.
  - Concrete target: `docs/FLUJO_VIDEOS.md`.

- [x] 1.3 **[DOC]** Modernize longform composition architecture in `docs/MULTICHANNEL_PIPELINE.md`:
  - Replace outdated single-clip repetition claims for horizontal longform with the Hybrid Multi-Act Director architecture implemented in `src/media/director_assembly.py` and specified in `docs/DIRECTOR_SINGLE_PASS.md`.
  - Document 4 to 8 act narrative pacing, tension-curve thematic loop matching from `assets/loops/`, and modulo fallback.
  - Specify stream-copy concat demuxer assembly (`-c:v copy`) for homogeneous loop segments sharing geometry, codec, pixel format, and time base.
  - Explicitly document strict performance constraints: composition turnaround ceiling of $\le 45$s under $\le 2$ CPU Cores and $\le 2.0$ GiB RAM budget.
  - Preserve YouTube Shorts (9:16) rendering specifications utilizing `LoopVideoEngine` (10s catalog loops, sub-2s stream-copy assembly, soft subtitle muxing `mov_text` with bottom safe margin `MarginV >= 240`).
  - Compact prose to reduce line count from 50 to $\le 46$ lines.
  - Concrete target: `docs/MULTICHANNEL_PIPELINE.md`.

- [x] 1.4 **[DOC]** Expand central index to cover all 19 active technical documents in `docs/README.md`:
  - Expand document catalog from 12 to all 19 active technical markdown files in `docs/`:
    1. `ARQUITECTURA.md`: Core system architecture, multiformat lanes, SQLite WAL persistence.
    2. `FLUJO_VIDEOS.md`: 13 canonical production stages from lease to YouTube publication.
    3. `MULTICHANNEL_PIPELINE.md`: Multi-channel visual pipeline, multi-act director, stream-copy performance.
    4. `DIRECTOR_SINGLE_PASS.md`: Single-pass FFmpeg assembly, encode count matrix, stream-copy constraints.
    5. `FFMPEG_LOW_CPU.md`: Low-CPU production defaults, performance budgets, resource envelope.
    6. `CANALES.md`: Modular channel profiles, generic variables, multi-channel taxonomy.
    7. `OPERACION.md`: Operations manual, unified CLI, Systemd daemons, Docker Compose.
    8. `CONFIGURACION_SECRETOS.md`: Environment variables inventory, runtime profiles, preflight checks.
    9. `INTEGRACIONES_Y_SERVICIOS.md`: External API contracts (Telegram Bot API, YouTube Data API/session, Drive, FFmpeg).
    10. `AGENTES_IA_Y_POLITICA.md`: AI-First policy, canonical Gemini models, active agent manifest and contracts.
    11. `MCP.md`: Model Context Protocol server specification, tools, resources, and prompts.
    12. `PLAN_MAESTRO_PIPELINE_VISUAL.md`: Visual pipeline master plan, component matrix, transition milestones.
    13. `PROPUESTA_EVOLUCION_PIPELINE_VISUAL.md`: Visual evolution roadmap, narrative act structures.
    14. `POLITICA_CATALOGO_CI.md`: CI vs production catalog policy, synthetic seed containment, disk verification.
    15. `visual-assets-policy.md`: Clean scenery loop standards, quarantine procedures, asset eligibility guards.
    16. `POLITICA_GOBERNANZA_ANTI_REGRESION.md`: 6 quality invariants, verification cadence, mandatory work refusal.
    17. `TROUBLESHOOTING.md`: Rapid error diagnostics, root cause triage, mitigation playbooks.
    18. `REFERENCIAS_Y_VERSIONES.md`: Pinned binary versions, runtime environments, external references.
    19. `README.md`: Central documentation knowledge base index and navigation hub.
  - Group catalog entries by functional domains (Core Pipeline, Operations, Agents, Visual Plans, Governance, Troubleshooting).
  - Verify every markdown link resolves to a valid relative path.
  - Maintain net line count at $\le 52$ lines.
  - Concrete target: `docs/README.md`.

- [x] 1.5 **[VERIFY]** Phase 1 Verification Checkpoint:
  - Run `.venv/bin/pytest tests/unit/test_docs_integrity.py -k "test_all_relative_links_resolve or test_code_blocks_are_tagged" -v`.
  - Confirm all relative links across Phase 1 docs resolve without error and all code fences have syntax identifiers.
  - Verify aggregate line reduction for Phase 1 documents is at least -30 lines.

---

### Phase 2: Agent Subsystem, Governance & Operations

- [x] 2.1 **[DOC]** Synchronize agent manifest with active modules in `docs/AGENTES_IA_Y_POLITICA.md`:
  - Eradicate all references to obsolete agent files (`script_curator.py`, `art_director.py`, `scene_planner.py`, `qa_auditor.py`, `image_auditor.py`, `investigator.py`).
  - Map the agent architecture exclusively to the 6 canonical modules in `src/agents/`:
    - `src/agents/base_agent.py`: `ProgrammaticAgent` base class, `CircuitBreaker` fault isolation, `AgyStreamClient` streaming transport, and `AgentSaturationError` backpressure management.
    - `src/agents/story_director.py`: `StoryDirectorAgent` narrative curation and `StoryInvestigatorAgent` Reddit source extraction and tension-curve structuring.
    - `src/agents/atmospheric_director.py`: `AtmosphericDirectorAgent` visual mood classification, thematic loop category resolution, and archetype token mapping.
    - `src/agents/seo_optimizer.py`: `SeoOptimizerAgent` YouTube algorithm packaging, high-CTR metadata generation, and tag taxonomy.
    - `src/agents/video_qa.py`: `VideoQAAgent` automated quality inspection, black frame detection, and perceptual luminance validation.
    - `src/agents/translator.py`: `TranslatorAgent` cross-locale adaptation and script translation.
  - Document programmatic roles and interfaces with high-density bullet points.
  - Compact prose to reduce line count from 85 to $\le 65$ lines.
  - Concrete target: `docs/AGENTES_IA_Y_POLITICA.md`.

- [x] 2.2 **[DOC]** Reconcile invariant counts and guardrail scope in `docs/POLITICA_GOBERNANZA_ANTI_REGRESION.md`:
  - Retitle Section 2 to `"## 2. Los 6 Invariantes Innegociables de Calidad"` (reconciling heading arithmetic with the 6 rules).
  - Update Section 1 to cite "los 6 invariantes del sistema" and reaffirm the mandatory Work Refusal (Kill Switch) obligation upon violation of any invariant.
  - Update Rule 5 to cite anti-regression test suite range `"REG-01 a REG-14"` in exact parity with `tests/unit/test_anti_regression_guardrails.py`, eradicating references to `"REG-01 a REG-30"`.
  - Formally articulate all 6 quality invariants:
    - Invariant 1: Aislamiento Absoluto de Medios (Zero-Browser Policy)
    - Invariant 2: Higiene de Árbol Git (Single SSOT)
    - Invariant 3: Candado Pre-Commit Activo (`.githooks/pre-commit`)
    - Invariant 4: Cero Documentos Resucitados (`docs/architecture/0*.md`, retired directories)
    - Invariant 5: Certificación de Suite de Anti-Regresión (REG-01 a REG-14)
    - Invariant 6: Cero Vías Procedurales o Matemáticas de Video (100% Asset-Based Pipeline)
  - Compact prose to reduce line count from 80 to $\le 78$ lines.
  - Concrete target: `docs/POLITICA_GOBERNANZA_ANTI_REGRESION.md`.

- [x] 2.3 **[DOC]** Compact operations manual and enforce path hygiene in `docs/OPERACION.md`:
  - Streamline CLI command tables, Systemd daemon service configurations, and Docker Compose recipes into concise code blocks with inline comments.
  - Enforce strict path hygiene by replacing all foreign or local `/home/...` paths with generic `<repo_root>` or absolute workspace paths.
  - Maintain all operational procedures: daemon lifecycle, queue management, pipeline execution, manual QA gate override, and preflight checks.
  - Compact prose to reduce line count from 154 to $\le 110$ lines.
  - Concrete target: `docs/OPERACION.md`.

- [x] 2.4 **[DOC]** Compact secrets and environment configuration matrix in `docs/CONFIGURACION_SECRETOS.md`:
  - Streamline environment variable reference tables, runtime profiles, and preflight check definitions.
  - Preserve all security invariants, mandatory API keys (`GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `YOUTUBE_CLIENT_SECRETS_FILE`), and fallback strategies.
  - Compact prose to reduce line count from 131 to $\le 95$ lines.
  - Concrete target: `docs/CONFIGURACION_SECRETOS.md`.

- [x] 2.5 **[DOC]** Compact supporting Active Docs to secure aggregate line budget buffer:
  - In `docs/INTEGRACIONES_Y_SERVICIOS.md`: Compact API integration contracts for Telegram, YouTube Data API v3, Google Drive, and FFmpeg; eliminate redundant narrative blocks while preserving endpoints, error handling, and rate-limiting rules (reduce from 78 to $\le 65$ lines).
  - In `docs/TROUBLESHOOTING.md`: Compact failure mode diagnosis table and mitigation playbooks; preserve all error codes, root causes, and CLI recovery commands (reduce from 39 to $\le 35$ lines).
  - In `docs/REFERENCIAS_Y_VERSIONES.md`: Compact pinned runtime dependencies table (Python 3.12/3.13, FFmpeg 6.1+, SQLite 3.45+) and upstream documentation links (reduce from 33 to $\le 30$ lines).
  - Concrete targets: `docs/INTEGRACIONES_Y_SERVICIOS.md`, `docs/TROUBLESHOOTING.md`, `docs/REFERENCIAS_Y_VERSIONES.md`.

- [x] 2.6 **[VERIFY]** Phase 2 Verification Checkpoint:
  - Run `.venv/bin/pytest tests/unit/test_docs_integrity.py -k "test_no_foreign_moku_paths_in_active_docs or test_code_blocks_are_tagged" -v`.
  - Confirm path hygiene compliance across `docs/OPERACION.md` and related docs.
  - Verify cumulative line reduction across Phase 2 docs achieves at least -100 lines.

---

### Phase 3: Visual Architecture Plans & Low-CPU Compaction

- [x] 3.1 **[DOC]** Compact visual master plan preserving all 7 mandatory section titles in `docs/PLAN_MAESTRO_PIPELINE_VISUAL.md`:
  - Eliminate redundant historical retrospectives and verbose retrospective narratives.
  - Strictly preserve verbatim all 7 mandatory section titles tested by `tests/unit/test_architectural_specs.py:test_plan_maestro_pipeline_visual_sections`:
    1. `"Consolidación de Auditorías Previas"`
    2. `"Diagnóstico del Workflow Actual"`
    3. `"Matriz de Componentes"`
    4. `"Estructura del Sistema"`
    5. `"Auditoría y Plan de Saneamiento Documental"`
    6. `"Checklist de Seguridad, Rendimiento"`
    7. `"Hitos Estratégicos de Transición"`
  - In Section 4 ("Estructura del Sistema"), update the embedded repository directory tree to reflect canonical modules in `src/agents/` and remove dead agent filenames.
  - Ensure total document character length remains comfortably above the 1000-character assertion in `test_architecture_doc_exists_and_non_empty`.
  - Compact file size from 373 lines down to $\le 240$ lines.
  - Concrete target: `docs/PLAN_MAESTRO_PIPELINE_VISUAL.md`.

- [x] 3.2 **[DOC]** Streamline visual evolution proposals in `docs/PROPUESTA_EVOLUCION_PIPELINE_VISUAL.md`:
  - Compact repetitive descriptions of the 4 narrative acts (Hook, Tension, Climax, Resolution).
  - Synchronize agent class references with active classes in `src/agents/` (`AtmosphericDirectorAgent`, `StoryDirectorAgent`).
  - Eliminate legacy procedural or shader evolution references, reaffirming the 100% asset-based video bank strategy.
  - Compact file size from 150 lines down to $\le 110$ lines.
  - Concrete target: `docs/PROPUESTA_EVOLUCION_PIPELINE_VISUAL.md`.

- [x] 3.3 **[DOC]** Modernize FFmpeg Low-CPU specification preserving all REG-14 invariant strings in `docs/FFMPEG_LOW_CPU.md`:
  - Replace transient references to PR #11 and feature branches (`perf/director-single-pass-ffmpeg`) with permanent architectural statements citing `director_assembly.py` and `LoopVideoEngine`.
  - Strictly preserve all mandatory invariant strings tested verbatim by `tests/unit/test_anti_regression_guardrails.py:TestResourceTargetGovernanceGuardrails`:
    - `"Target Resource Envelope (≤ 2 Cores CPU, ≤ 2.0 GiB RAM)"`
    - `"turnaround ceiling of ≤ 45s"`
    - `"≤ 2 Cores CPU"` or `"≤ 2 CPU Cores"`
    - `"≤ 2.0 GiB RAM"`
  - Cross-check `AGENTS.md` to confirm all 5 mandatory invariant strings remain intact:
    - `"Strict Resource Target & Performance Budget (2 Cores, 2 GB RAM)"`
    - `"≤ 2 CPU Cores"`
    - `"≤ 2.0 GiB RAM"`
    - `"Resource Work Refusal"`
    - `"turnaround ceiling of ≤ 45s"`
  - Maintain line count at $\le 36$ lines.
  - Concrete targets: `docs/FFMPEG_LOW_CPU.md`, `AGENTS.md`.

- [x] 3.4 **[VERIFY]** Phase 3 Verification Checkpoint:
  - Run `.venv/bin/pytest tests/unit/test_architectural_specs.py -k "test_plan_maestro_pipeline_visual_sections" -v`.
  - Run `.venv/bin/pytest tests/unit/test_anti_regression_guardrails.py -k "TestResourceTargetGovernanceGuardrails" -v`.
  - Confirm 100% pass across all 7 section titles and all REG-14 invariant strings.

---

### Phase 4: Root Documentation & Project Roadmap

- [x] 4.1 **[DOC]** Modernize milestone states while preserving feature tokens F01–F16 in `PROJECT.md`:
  - Update the milestones status table (M1 through M4) from `IN_PROGRESS` or `PENDING` to `COMPLETED` / `ACTIVE` to reflect production status.
  - Strictly preserve all 16 feature tokens (`F01` through `F16`) tested by `tests/unit/test_architectural_specs.py:test_root_project_and_test_infra_docs_exist`:
    - `F01` (Autonomous Daemon Orchestrator), `F02` (Modular Channel Profiles), `F03` (Multi-Format Production Lanes), `F04` (Audio-First Composition Pipeline), `F05` (Clean Scenery Video Bank), `F06` (100% Asset-Based Stream-Copy Engine), `F07` (Karaoke Subtitles ASS & Soft Mux), `F08` (Local Deterministic Thumbnails), `F09` (Comprehensive Pre-Publish QA Gate), `F10` (YouTube Publication Integration), `F11` (Telegram Bot Operations Interface), `F12` (SimHash Semantic Deduplication), `F13` (Zero-Browser Policy & Headless Architecture), `F14` (Model Context Protocol Server), `F15` (Multi-Act Narrative Director Architecture), `F16` (Low-CPU Performance & Resource Work Refusal).
  - Compact formatting to reduce line count from 77 to $\le 72$ lines.
  - Concrete target: `PROJECT.md`.

- [x] 4.2 **[DOC]** Synchronize root `README.md` with canonical architecture and compact prose:
  - Update the Production Lanes table to reflect all 6 canonical lanes from `config/lanes.json` (`horror-scp-shorts`, `horror-horror-long`, `drama-drama-shorts`, `drama-aita-long`, `scifi-singularity-shorts`, `scifi-singularity-long`).
  - Update the AI Agent Subsystem overview to reflect the 6 active canonical modules in `src/agents/`.
  - Streamline Quickstart and CLI execution examples into compact, dense command blocks.
  - Enforce strict path hygiene (no hardcoded `/home/Moku` paths).
  - Compact prose to reduce line count from 123 to $\le 92$ lines.
  - Concrete target: `README.md`.

- [x] 4.3 **[DOC]** Enforce strict line budget compliance across `ACTIVE_DOCS`:
  - Run line counting probe across all 12 files in `ACTIVE_DOCS`:
    `README.md`, `PROJECT.md`, `docs/README.md`, `docs/ARQUITECTURA.md`, `docs/FLUJO_VIDEOS.md`, `docs/MULTICHANNEL_PIPELINE.md`, `docs/OPERACION.md`, `docs/CONFIGURACION_SECRETOS.md`, `docs/INTEGRACIONES_Y_SERVICIOS.md`, `docs/AGENTES_IA_Y_POLITICA.md`, `docs/TROUBLESHOOTING.md`, `docs/REFERENCIAS_Y_VERSIONES.md`.
  - Assert total lines $\le 1000$ (target $\approx 806$ lines, creating $\ge 150$ lines of durable safety margin).
  - Concrete targets: All 12 files in `ACTIVE_DOCS`.

- [x] 4.4 **[VERIFY]** Phase 4 Verification Checkpoint:
  - Run `.venv/bin/pytest tests/unit/test_docs_integrity.py:TestDocumentationIntegrity::test_total_lines_budget_under_1000 -v`.
  - Run `.venv/bin/pytest tests/unit/test_architectural_specs.py:TestArchitecturalSpecs::test_root_project_and_test_infra_docs_exist -v`.
  - Confirm both line budget ceiling ($\le 1000$) and all feature tokens (`F01` to `F16`) pass cleanly.

---

### Phase 5: Verification & Integrity Hardening

- [x] 5.1 **[VERIFY]** Execute Documentation Integrity Test Suite:
  - Run `.venv/bin/pytest tests/unit/test_docs_integrity.py -v`.
  - Verify all 5 tests pass:
    - `test_all_active_docs_exist`: Confirms all 12 active docs exist on disk.
    - `test_no_foreign_moku_paths_in_active_docs`: Confirms 0 occurrences of `/home/Moku` or foreign paths.
    - `test_all_relative_links_resolve`: Confirms 100% of relative markdown links resolve to valid targets.
    - `test_code_blocks_are_tagged`: Confirms 100% of opening code fences have explicit language syntax tags.
    - `test_total_lines_budget_under_1000`: Confirms aggregate line count is $\le 1000$ lines.
  - Concrete target: `tests/unit/test_docs_integrity.py`.

- [x] 5.2 **[VERIFY]** Execute Architectural Specifications Test Suite:
  - Run `.venv/bin/pytest tests/unit/test_architectural_specs.py -v`.
  - Confirm all 27 tests pass cleanly, specifically:
    - `test_plan_maestro_pipeline_visual_sections`: 7 mandatory section titles present in `PLAN_MAESTRO_PIPELINE_VISUAL.md`.
    - `test_root_project_and_test_infra_docs_exist`: F01 through F16 feature tokens present in `PROJECT.md`.
    - `test_plan_arquitectura_v3_1_is_purged`: Zero resurrected obsolete architecture blueprints.
    - `test_anti_regression_governance_rules_complete`: 6 quality invariants present in `POLITICA_GOBERNANZA_ANTI_REGRESION.md`.
  - Concrete target: `tests/unit/test_architectural_specs.py`.

- [x] 5.3 **[VERIFY]** Execute Anti-Regression Guardrail Suite (REG-01 to REG-14):
  - Run `.venv/bin/pytest tests/unit/test_anti_regression_guardrails.py -v`.
  - Confirm all 35 tests pass cleanly across REG-01 through REG-14, specifically:
    - `test_reg14_agents_governance_contains_resource_target`: Confirms all 4 resource budget and work refusal strings in `AGENTS.md`.
    - `test_reg14_ffmpeg_low_cpu_documents_resource_target`: Confirms target resource envelope in `docs/FFMPEG_LOW_CPU.md`.
    - `test_reg14_multiact_stream_copy_turnaround_ceiling_documented`: Confirms turnaround ceiling of $\le 45$s in both `AGENTS.md` and `docs/FFMPEG_LOW_CPU.md`.
    - `test_reg10_zero_imports_of_retired_legacy_subsystems`: Zero legacy imports.
    - `test_reg13_stream_copy_cmd_muxes_not_libass`: Longform horizontal lanes use stream-copy and soft muxing.
  - Concrete target: `tests/unit/test_anti_regression_guardrails.py`.

- [x] 5.4 **[VERIFY]** Execute MCP Server Synchronization Gate:
  - Run `.venv/bin/python scripts/verify_mcp_sync.py`.
  - Confirm 100% bidirectional parity across:
    - 9 canonical tools: `audit_loop_catalog`, `get_lane_info`, `get_system_status`, `list_lanes`, `manage_queue`, `query_loop_catalog`, `run_pipeline_dry_run`, `system_preflight`, `verify_integrity`.
    - 3 canonical resources: `channels://{channel_name}/config`, `lanes://catalog`, `system://health`.
    - 3 canonical prompts: `channel_incident_analysis`, `preflight_diagnostics`, `video_qa_review`.
  - Confirm `docs/MCP.md`, `src/mcp/server.py`, and `mcp_config.json` are fully in sync with exit code 0 (`STATUS: HEALTHY`).
  - Concrete target: `scripts/verify_mcp_sync.py`, `docs/MCP.md`.

- [x] 5.5 **[VERIFY]** Execute Repository Governance & Invariant Audit:
  - Run `./scripts/verify_integrity.sh`.
  - Confirm complete repository audit passes cleanly with exit code 0 (`STATUS: HEALTHY`), asserting:
    - Git worktree hygiene: 0 stale worktrees.
    - Architecture docs: 0 obsolete blueprints.
    - Subsystem isolation: 0 legacy rendering directories, 0 retired imports.
    - Zero-Browser policy: 0 Playwright imports.
    - Zero-Procedural-Math policy: 0 WGSL shaders, 0 procedural imports.
    - Git pre-commit hook active and enforced.
    - MCP synchronization: 100% bidirectional parity.
  - Concrete target: `./scripts/verify_integrity.sh`.
