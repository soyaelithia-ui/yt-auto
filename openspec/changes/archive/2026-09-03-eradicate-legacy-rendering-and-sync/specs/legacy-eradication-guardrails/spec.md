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
The SDD context in `openspec/config.yaml` SHALL reflect only active production dependencies and SHALL NOT list retired or restricted libraries.

#### Scenario: OpenSpec tech stack validation
- **Given** `openspec/config.yaml`
- **When** the `context:` block is parsed
- **Then** neither `Playwright` nor `Pillow` SHALL be declared as part of the production media stack.
