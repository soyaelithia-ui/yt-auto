# Spec: Legacy Eradication Guardrails

## Requirements

### Requirement: Zero Retired Subsystem Imports
The system SHALL NOT contain any Python source or test file that imports from retired legacy modules (`src.rendering`, `src.compositing`, or `src.export`).

#### Scenario: Codebase scan for retired namespaces
- **Given** all Python files in `src/` and `tests/`
- **When** an AST import scanner inspects every import statement
- **Then** zero imports of `src.rendering`, `src.compositing`, or `src.export` SHALL be present.

### Requirement: Deterministic Test Suite Collectability
The test suite SHALL be 100% collectable by pytest with zero collection errors.

#### Scenario: Full pytest collection run
- **Given** the active pytest test directory `tests/`
- **When** `pytest --collect-only -q` is executed
- **Then** the exit code SHALL be 0 with 0 errors.

### Requirement: Truthful SDD Context Configuration
The SDD context in `openspec/config.yaml` SHALL reflect only active production dependencies. Production media stack SHALL list FFmpeg and MAY list Pillow for thumbnail SSOT. The context SHALL NOT list Playwright as production media. The context SHALL NOT list wgpu-py or resvg-py as the production stack.

#### Scenario: OpenSpec tech stack validation
- **Given** `openspec/config.yaml`
- **When** the `context:` block is parsed
- **Then** Playwright SHALL NOT be declared as part of the production media stack
- **And** wgpu-py and resvg-py SHALL NOT be declared as the production stack
- **And** Pillow MAY be declared for thumbnail SSOT.

#### Scenario: Pillow thumbs SSOT is not a retired library (Edge Case)
- **Given** thumbnail generation uses Pillow as SSOT
- **When** the `context:` block is validated against this guardrail
- **Then** listing Pillow for thumbs SHALL be allowed
- **And** Playwright SHALL remain forbidden as production media.
### Requirement: Prohibition of Obsolete Architecture Blueprints and Purged Documents
In accordance with the Zero Resurrected Docs policy (AGENTS.md Rule 1), the repository SHALL NOT retain obsolete architecture blueprints or superseded visual design documents. Specifically:
1. `docs/PLAN_ARQUITECTURA_V3_1.md` SHALL be permanently removed from the repository.
2. Architecture test suites (`tests/unit/test_architectural_specs.py`) and documentation indices (`docs/README.md`) SHALL NOT expect or assert the presence of `PLAN_ARQUITECTURA_V3_1.md`.
3. Active visual architecture blueprints (`docs/PLAN_MAESTRO_PIPELINE_VISUAL.md` and `docs/PROPUESTA_EVOLUCION_PIPELINE_VISUAL.md`) SHALL NOT contain obsolete failed audit retrospectives (including SwiftShader CPU saturation, skia-python failures, and ModernGL fallbacks) while retaining all active production architecture specifications and section anchors.

#### Scenario: Rejection of obsolete blueprint PLAN_ARQUITECTURA_V3_1.md (Happy Path)
- **Given** the documentation tree in `docs/`
- **When** an automated integrity check or filesystem scan verifies active architectural documentation
- **Then** `docs/PLAN_ARQUITECTURA_V3_1.md` SHALL NOT exist
- **And** the test runner SHALL NOT fail due to missing legacy blueprints.

#### Scenario: Documentation test suite verification without legacy blueprints (Happy Path)
- **Given** `tests/unit/test_architectural_specs.py` executing `TestArchitecturalDocumentation`
- **When** `EXPECTED_DOCS` is validated against the filesystem
- **Then** `EXPECTED_DOCS` SHALL NOT contain `PLAN_ARQUITECTURA_V3_1.md`
- **And** all specified active documentation files SHALL pass existence and content size checks.

### Requirement: Core Subsystem Function Budget and Granularity Enforcement (~100 Lines)
In accordance with AGENTS.md Rule 8.1, all core subsystems (`src/youtube/`, `src/curators/`, `src/core/`, `src/media/`) MUST adhere to the Single Responsibility Principle (SRP). Individual functions and methods within these subsystems MUST NOT exceed ~100 lines of executable logic (excluding docstrings and comments). Sprawling monolithic orchestrators MUST be decomposed into granular, single-responsibility stage functions and sub-modules.

#### Scenario: Subsystem function line budget audit (Happy Path)
- **Given** Python modules in `src/youtube/`, `src/curators/`, `src/core/`, and `src/media/`
- **When** an AST scanner audits executable line counts for every function and method
- **Then** zero functions or methods SHALL exceed ~100 executable lines of code
- **And** each decomposed helper or stage function SHALL perform a single discrete operational step.

#### Scenario: Playwright upload lifecycle modularization (Happy Path)
- **Given** the browser-based fallback uploader in `src/youtube/uploader/session.py` (or sub-modules)
- **When** `upload_video_via_playwright` executes
- **Then** its workflow MUST be broken into granular sub-functions (context initialization, navigation/auth check, file payload upload, metadata completion, visibility selection, and processing completion)
- **And** no individual sub-function SHALL exceed ~100 executable lines.

### Requirement: Prohibition of Fantasy Channel Identifiers in Default Signatures and Manifests
Public function signatures, CLI entrypoint defaults, and configuration models across the codebase SHALL NOT specify legacy fantasy channel strings (`"moku"`, `"aelithia"`, `"[MOKU]"`) as default parameter values or default watermark stamps. Parameter defaults MUST either specify canonical thematic identifiers (`"horror"`, `"drama"`, `"scifi"`), derive the channel dynamically from context/lane definitions, or require an explicit channel argument.

#### Scenario: Static check for parameter defaults prohibits fantasy identifiers (Happy Path)
- **Given** source files defining CLI parsers, daemon loops, and public interfaces (`src/scene_manifest.py`, `src/daemon.py`, `src/cli/subparsers.py`)
- **When** parameter signatures and dataclass default values are inspected
- **Then** zero function or method default arguments SHALL equal `"moku"` or `"aelithia"`
- **And** `SceneManifest` stamp defaults SHALL NOT contain `"[MOKU]"`.

#### Scenario: Dynamic or canonical channel default resolution (Happy Path)
- **Given** a daemon or worker process invoked without an explicit channel argument
- **When** the channel parameter is resolved
- **Then** the system MUST resolve to canonical `"horror"` or derive the channel identifier dynamically from the target lane ID.
