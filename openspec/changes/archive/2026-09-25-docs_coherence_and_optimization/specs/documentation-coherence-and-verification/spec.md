# Documentation Coherence and Verification Specification

## Purpose

The `documentation-coherence-and-verification` capability defines the normative standards, architectural integrity contracts, and automated verification procedures governing all active documentation across the `yt-auto` repository. It guarantees complete factual accuracy and bidirectional synchronization between documentation and Python codebase implementations, establishes strict line budgets ($\le 1000$ lines aggregate across `ACTIVE_DOCS`), eradicates obsolete or resurrected legacy references, locks inviolable anti-regression invariant strings, and provides an authoritative, navigable Single Source of Truth (SSOT).

---

## Requirements

### Requirement: Agent Manifest and Codebase Parity
The documentation in `docs/AGENTES_IA_Y_POLITICA.md` and related architectural references SHALL map exclusively to the active Python agent modules located in `src/agents/`. Zero references to retired or non-existent agent files (including `script_curator.py`, `art_director.py`, `scene_planner.py`, `qa_auditor.py`, `image_auditor.py`, and `investigator.py`) SHALL appear in any active documentation. The documentation MUST accurately articulate the programmatic responsibilities, base classes, and architectural contracts for all 6 active agent modules:
1. `src/agents/base_agent.py`: `ProgrammaticAgent` base class, `CircuitBreaker` fault isolation, `AgyStreamClient` streaming transport, and `AgentSaturationError` backpressure management.
2. `src/agents/story_director.py`: `StoryDirectorAgent` narrative curation and `StoryInvestigatorAgent` Reddit source extraction and tension-curve structuring.
3. `src/agents/atmospheric_director.py`: `AtmosphericDirectorAgent` visual mood classification, thematic loop category resolution, and archetype token mapping.
4. `src/agents/seo_optimizer.py`: `SeoOptimizerAgent` YouTube algorithm packaging, high-CTR metadata generation, and tag taxonomy.
5. `src/agents/video_qa.py`: `VideoQAAgent` automated quality inspection, black frame detection, and perceptual luminance validation.
6. `src/agents/translator.py`: `TranslatorAgent` cross-locale adaptation and script translation.

#### Scenario: Active Agent Inventory Codebase Synchronization (Happy Path)
- **Given** the 6 active Python agent modules in `src/agents/`
- **When** `docs/AGENTES_IA_Y_POLITICA.md` is inspected
- **Then** every documented agent module SHALL correspond exactly to an existing file in `src/agents/`
- **And** all documented agent classes (`ProgrammaticAgent`, `StoryDirectorAgent`, `StoryInvestigatorAgent`, `AtmosphericDirectorAgent`, `SeoOptimizerAgent`, `VideoQAAgent`, `TranslatorAgent`) SHALL accurately reflect their operational roles
- **And** zero references to obsolete agent filenames SHALL be present.

#### Scenario: Rejection of Dead Agent References (Edge Case)
- **Given** any markdown documentation file referencing deleted agent files such as `script_curator.py` or `art_director.py`
- **When** documentation integrity validation is executed
- **Then** the dead agent references SHALL be identified as parity defects
- **And** the offending references MUST be updated to reference the consolidated canonical modules in `src/agents/`.

---

### Requirement: Production Lane and Channel Model Parity
Architectural documentation in `docs/ARQUITECTURA.md`, `docs/CANALES.md`, and `docs/MULTICHANNEL_PIPELINE.md` SHALL maintain strict parity with the production lane definitions declared in `config/lanes.json`. Documentation MUST enumerate all 6 production lanes with their canonical identifiers, assigned channels, aspect ratios, and operational states:
1. `horror-scp-shorts`: Channel `horror`, vertical (9:16), story type `scp`, enabled `true`.
2. `horror-horror-long`: Channel `horror`, horizontal (16:9), story type `horror`, enabled `true`.
3. `drama-drama-shorts`: Channel `drama`, vertical (9:16), story type `reddit_aita`, enabled `true`.
4. `drama-aita-long`: Channel `drama`, horizontal (16:9), story type `reddit_aita`, enabled `true`.
5. `scifi-singularity-shorts`: Channel `scifi`, vertical (9:16), story type `scifi`, enabled `false` (pre-configured / disabled).
6. `scifi-singularity-long`: Channel `scifi`, horizontal (16:9), story type `scifi`, enabled `false` (pre-configured / disabled).

Furthermore, Section 9 of `docs/ARQUITECTURA.md` MUST explicitly cite the complete anti-regression test suite range spanning REG-01 through REG-14.

#### Scenario: Production Lane Catalog Verification (Happy Path)
- **Given** `config/lanes.json` defining the 6 production lanes across horror, drama, and scifi
- **When** `docs/ARQUITECTURA.md` is inspected
- **Then** all 6 canonical lane identifiers SHALL be explicitly cataloged with their respective channels and aspect ratios
- **And** obsolete lane identifiers (`horror-long`, `drama-shorts`) SHALL NOT appear
- **And** both active and pre-configured disabled lanes (SciFi) SHALL be documented with their exact configuration flags.

#### Scenario: Guardrail Suite Scope Alignment (Happy Path)
- **Given** the guardrail test suite defined in `tests/unit/test_anti_regression_guardrails.py` spanning REG-01 through REG-14
- **When** Section 9 of `docs/ARQUITECTURA.md` is evaluated
- **Then** the documented guardrail scope SHALL cite "REG-01 a REG-14"
- **And** SHALL NOT truncate at REG-13 or refer to non-existent guardrail ranges.

---

### Requirement: Sequential Execution Stage Ordering
In `docs/FLUJO_VIDEOS.md`, the 13 canonical production pipeline stages MUST be presented in strict ascending numerical and chronological execution order matching the implementation files in `src/pipeline/stages/`. Both the Mermaid pipeline flowchart and the detailed stage specification table SHALL reflect the following linear sequence:
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

#### Scenario: Strict Sequential Ordering of Pipeline Stages (Happy Path)
- **Given** the 13 pipeline stage implementation modules in `src/pipeline/stages/`
- **When** `docs/FLUJO_VIDEOS.md` is inspected
- **Then** stages 01 through 13 SHALL be listed in strictly ascending numerical order
- **And** the Mermaid flowchart SHALL route execution linearly from stage 01 through stage 13 without transposition
- **And** stage 04 SHALL strictly precede stage 05, stage 10 SHALL strictly precede stage 11, and stage 12 SHALL strictly precede stage 13.

#### Scenario: Rejection of Out-of-Order Pipeline Documentation (Edge Case)
- **Given** pipeline documentation containing scrambled stage orders (such as stage 04 placed after stage 07, or stage 10 placed after stage 12)
- **When** architectural documentation auditing is performed
- **Then** the sequence discrepancy SHALL be flagged as a structural defect
- **And** the documentation MUST be reordered to match the orchestrator's linear execution chain.

---

### Requirement: Anti-Regression and Invariant Governance Alignment
In `docs/POLITICA_GOBERNANZA_ANTI_REGRESION.md`, the documentation MUST establish perfect coherence between section titles, enumerated invariants, and test suite scopes:
1. Section 2 MUST be titled `"Los 6 Invariantes Innegociables de Calidad"`, reconciling the header with the 6 concrete invariant rules articulated in the document.
2. Section 1 MUST articulate the mandatory work refusal (Kill Switch) obligation triggered upon any violation of the 6 system invariants.
3. Section 2 Rule 5 MUST define the anti-regression test suite scope as `"REG-01 a REG-14"` in exact parity with `tests/unit/test_anti_regression_guardrails.py`.
4. The 6 inviolable invariants MUST be formally specified:
   - Invariant 1: Aislamiento Absoluto de Medios (Zero-Browser Policy)
   - Invariant 2: Higiene de Árbol Git (Single SSOT)
   - Invariant 3: Candado Pre-Commit Activo (`.githooks/pre-commit`)
   - Invariant 4: Cero Documentos Resucitados (`docs/architecture/0*.md`, `src/rendering/`, `src/compositing/`, `src/export/`)
   - Invariant 5: Certificación de Suite de Anti-Regresión (REG-01 a REG-14)
   - Invariant 6: Cero Vías Procedurales o Matemáticas de Video (100% Asset-Based Pipeline)

#### Scenario: Governance Header and Invariant Count Reconciled (Happy Path)
- **Given** `docs/POLITICA_GOBERNANZA_ANTI_REGRESION.md`
- **When** Section 2 is evaluated
- **Then** the heading SHALL read `"Los 6 Invariantes Innegociables de Calidad"`
- **And** exactly 6 distinct numbered invariant rules SHALL be articulated
- **And** Section 1 SHALL mandate immediate work refusal upon violation of any of the 6 invariants.

#### Scenario: Test Suite Scope Citation Alignment (Happy Path)
- **Given** the guardrails test suite executing guardrails REG-01 through REG-14
- **When** Section 2 Rule 5 of `docs/POLITICA_GOBERNANZA_ANTI_REGRESION.md` is inspected
- **Then** the verified scope text SHALL state `"REG-01 a REG-14"`
- **And** erroneous references to `"REG-01 a REG-30"` SHALL be eradicated.

---

### Requirement: Multi-Channel and Hybrid Multi-Act Architecture Alignment
`docs/MULTICHANNEL_PIPELINE.md` MUST specify longform horizontal (16:9) video rendering via the Hybrid Multi-Act Director architecture implemented in `src/media/director_assembly.py` and documented in `docs/DIRECTOR_SINGLE_PASS.md`. The specification SHALL supersede obsolete claims of single-clip 30s repetition for horizontal longform. The document MUST specify:
1. Multi-act narrative curation spanning 4 to 8 distinct narrative acts per longform story.
2. Tension-curve and dramatic-role thematic loop matching from the certified video bank, with deterministic modulo fallback.
3. Stream-copy concat demuxer assembly (`-c:v copy`) for homogeneous loop segments sharing resolution, codec, pixel format, and time base.
4. Compliance with the production turnaround ceiling of $\le 45$s under a resource budget of $\le 2$ CPU cores and $\le 2.0$ GiB RAM.
5. Preservation of YouTube Shorts (9:16) rendering specifications utilizing `LoopVideoEngine` with seamless 10s catalog loops, sub-2s stream-copy assembly, and soft subtitle muxing (`mov_text`) with bottom safe area margin (`MarginV >= 240`).

#### Scenario: Multi-Act Director Architecture Specification for Longform (Happy Path)
- **Given** the multi-act rendering implementation in `src/media/director_assembly.py`
- **When** `docs/MULTICHANNEL_PIPELINE.md` is inspected
- **Then** the longform horizontal (16:9) section SHALL specify the Hybrid Multi-Act Director architecture
- **And** describe multi-act narrative pacing (4 to 8 acts), thematic loop resolution, and stream-copy concat demuxer assembly
- **And** document the performance constraint requiring composition completion within a turnaround ceiling of $\le 45$s under $\le 2$ CPU cores and $\le 2.0$ GiB RAM.

#### Scenario: Shorts Vertical Specification Preservation (Happy Path)
- **Given** the vertical Shorts rendering workflow
- **When** `docs/MULTICHANNEL_PIPELINE.md` is inspected
- **Then** YouTube Shorts (9:16) SHALL specify `LoopVideoEngine` utilizing continuous 10s catalog loops (`assets/videos/shorts/`) with sub-2s stream-copy assembly
- **And** soft subtitle muxing (`mov_text`) preserving the bottom safe area margin (`MarginV >= 240`).

---

### Requirement: Central Documentation Navigation Completeness
`docs/README.md` SHALL serve as the authoritative central navigation index, cataloging all 19 active technical markdown documents in the `docs/` directory with categorized roles, scope summaries, and verified relative links. The catalog MUST encompass:
1. `ARQUITECTURA.md`: Core system architecture, multiformat lanes, SQLite WAL persistence, state machine.
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

#### Scenario: Full Cataloging of All 19 Active Documents (Happy Path)
- **Given** the 19 active technical markdown files in `docs/`
- **When** `docs/README.md` is inspected
- **Then** all 19 documents SHALL be cataloged in the navigation tables or role-based index sections
- **And** every document link SHALL resolve to a valid file in `docs/`
- **And** zero active technical documentation files SHALL remain unreferenced.

#### Scenario: Prevention of Unindexed Active Documentation (Edge Case)
- **Given** any existing or newly introduced active document in `docs/`
- **When** documentation navigation completeness is audited
- **Then** any active markdown file not cataloged in `docs/README.md` SHALL be flagged as a navigation defect
- **And** an index entry MUST be added to `docs/README.md`.

---

### Requirement: Active Docs Line Budget and Formatting Integrity
All active documentation files SHALL comply with strict quality, formatting, path hygiene, and line budget invariants enforced by automated tests in `tests/unit/test_docs_integrity.py` and `tests/unit/test_architectural_specs.py`:
1. **Total Lines Budget**: The consolidated total line count across all 12 documents in `ACTIVE_DOCS` (`README.md`, `PROJECT.md`, `docs/README.md`, `docs/ARQUITECTURA.md`, `docs/FLUJO_VIDEOS.md`, `docs/MULTICHANNEL_PIPELINE.md`, `docs/OPERACION.md`, `docs/CONFIGURACION_SECRETOS.md`, `docs/INTEGRACIONES_Y_SERVICIOS.md`, `docs/AGENTES_IA_Y_POLITICA.md`, `docs/TROUBLESHOOTING.md`, `docs/REFERENCIAS_Y_VERSIONES.md`) MUST NOT exceed 1000 lines, and SHOULD maintain a safety margin with total lines $\le 950$.
2. **Code Block Syntax Tagging**: Every fenced code block (delimited by triple backticks) across all active documents MUST specify an explicit syntax language identifier (e.g. `bash`, `python`, `json`, `mermaid`, `text`). Fences without language tags are strictly prohibited.
3. **Relative Link Resolution**: Every relative markdown link in active documentation MUST resolve to an existing filesystem target. Broken relative links are strictly prohibited.
4. **Path Hygiene**: Hardcoded `/home/Moku` or foreign user paths are strictly prohibited in all active documentation.
5. **Plan Maestro Mandatory Section Anchors**: `docs/PLAN_MAESTRO_PIPELINE_VISUAL.md` MUST preserve all 7 mandatory section titles tested by `test_plan_maestro_pipeline_visual_sections`:
   - `"Consolidación de Auditorías Previas"`
   - `"Diagnóstico del Workflow Actual"`
   - `"Matriz de Componentes"`
   - `"Estructura del Sistema"`
   - `"Auditoría y Plan de Saneamiento Documental"`
   - `"Checklist de Seguridad, Rendimiento"`
   - `"Hitos Estratégicos de Transición"`
6. **Project Feature Inventory Preservation**: `PROJECT.md` MUST preserve all 16 feature tokens (`F01` to `F16`) tested by `test_root_project_and_test_infra_docs_exist`, while modernizing milestone status indicators from `IN_PROGRESS` or `PENDING` to `COMPLETED` / `ACTIVE`.

#### Scenario: Line Budget Compliance Verification (Happy Path)
- **Given** the 12 documents comprising `ACTIVE_DOCS`
- **When** `test_total_lines_budget_under_1000` is executed
- **Then** the aggregate line count SHALL be $\le 1000$ lines
- **And** the test SHALL pass cleanly.

#### Scenario: Code Block Syntax Tag Verification (Happy Path)
- **Given** all code blocks within `ACTIVE_DOCS`
- **When** `test_code_blocks_are_tagged` is executed
- **Then** every opening code fence SHALL contain an explicit language tag
- **And** zero untagged code blocks SHALL be detected.

#### Scenario: Relative Link Integrity Verification (Happy Path)
- **Given** all relative links within `ACTIVE_DOCS`
- **When** `test_all_relative_links_resolve` is executed
- **Then** every relative link SHALL successfully resolve to an existing file
- **And** zero broken links SHALL be reported.

#### Scenario: Mandatory Section Preservation in Plan Maestro (Happy Path)
- **Given** `docs/PLAN_MAESTRO_PIPELINE_VISUAL.md`
- **When** `test_plan_maestro_pipeline_visual_sections` is executed
- **Then** all 7 mandatory section headings SHALL be present in the document
- **And** the test SHALL pass cleanly.

#### Scenario: Feature Tag Retention in Project Milestones (Happy Path)
- **Given** `PROJECT.md` at repository root
- **When** `test_root_project_and_test_infra_docs_exist` is executed
- **Then** all feature tags `F01` through `F16` SHALL be present in `PROJECT.md`
- **And** the milestone table SHALL reflect completed and active feature states.

---

### Requirement: Invariant Preservation Guarantee
No documentation update SHALL alter, delete, or relocate the mandatory invariant text strings asserted by automated anti-regression tests in `tests/unit/test_anti_regression_guardrails.py`, nor disrupt the 100% bidirectional parity between code, configuration, and documentation in `docs/MCP.md`. The documentation MUST preserve the following exact invariant strings:
1. In `AGENTS.md` (asserted by `test_reg14_agents_governance_contains_resource_target` and `test_reg14_multiact_stream_copy_turnaround_ceiling_documented`):
   - `"Strict Resource Target & Performance Budget (2 Cores, 2 GB RAM)"`
   - `"≤ 2 CPU Cores"`
   - `"≤ 2.0 GiB RAM"`
   - `"Resource Work Refusal"`
   - `"turnaround ceiling of ≤ 45s"`
2. In `docs/FFMPEG_LOW_CPU.md` (asserted by `test_reg14_ffmpeg_low_cpu_documents_resource_target` and `test_reg14_multiact_stream_copy_turnaround_ceiling_documented`):
   - `"Target Resource Envelope (≤ 2 Cores CPU, ≤ 2.0 GiB RAM)"`
   - `"turnaround ceiling of ≤ 45s"`
   - `"≤ 2 Cores CPU"` or `"≤ 2 CPU Cores"`
   - `"≤ 2.0 GiB RAM"`
3. In `docs/MCP.md` (asserted by `scripts/verify_mcp_sync.py`):
   - 100% parity across all 9 canonical tools: `audit_loop_catalog`, `get_lane_info`, `get_system_status`, `list_lanes`, `manage_queue`, `query_loop_catalog`, `run_pipeline_dry_run`, `system_preflight`, `verify_integrity`.
   - 100% parity across all 3 canonical resources: `channels://{channel_name}/config`, `lanes://catalog`, `system://health`.
   - 100% parity across all 3 canonical prompts: `channel_incident_analysis`, `preflight_diagnostics`, `video_qa_review`.

Furthermore, modernization of `docs/FFMPEG_LOW_CPU.md` SHALL replace stale branch and PR references (such as PR #11 and `perf/director-single-pass-ffmpeg`) with permanent architectural references to `director_assembly.py` and `LoopVideoEngine`, while keeping all invariant strings completely intact.

#### Scenario: Exact Invariant String Preservation During Modernization (Happy Path)
- **Given** updates to `AGENTS.md` and `docs/FFMPEG_LOW_CPU.md` modernizing branch and PR references
- **When** `test_anti_regression_guardrails.py::TestResourceTargetGovernanceGuardrails` is executed
- **Then** all required invariant strings SHALL be present verbatim in the respective files
- **And** all REG-14 guardrail tests SHALL pass cleanly without failures.

#### Scenario: Continuous 100% Bidirectional MCP Parity (Happy Path)
- **Given** the MCP server implementation in `src/mcp/server.py`, client configuration in `mcp_config.json`, and documentation in `docs/MCP.md`
- **When** `scripts/verify_mcp_sync.py` is executed
- **Then** 100% tool, resource, and prompt parity SHALL be confirmed
- **And** the script SHALL terminate with exit code 0 (`STATUS: HEALTHY`).

#### Scenario: Work Refusal Triggered on Invariant String Corruption (Edge Case)
- **Given** any edit that inadvertently modifies, rephrases, or deletes a mandatory invariant string in `docs/FFMPEG_LOW_CPU.md` or `AGENTS.md`
- **When** `tests/unit/test_anti_regression_guardrails.py` is executed
- **Then** the test suite SHALL fail with an explicit REG-14 VIOLATION error
- **And** the mandatory Work Refusal policy SHALL immediately halt the workflow until the exact invariant string is restored.
