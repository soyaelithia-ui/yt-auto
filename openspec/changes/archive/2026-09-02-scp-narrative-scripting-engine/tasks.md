# Tasks: SCP Narrative Scripting & High-Retention Engine

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 280 - 360 lines |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | single-pr |
| Chain strategy | single-pr |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: single-pr
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | High-retention narrative curating and engine pacing | PR 1 | `pytest tests/unit/test_narrative_scripting.py` | N/A (pure Python narrative engine) | `src/curators/moku_horror.py`, `src/agents/script_curator.py`, `src/narrative/` |

## Phase 1: Test Harness & TDD Specifications (RED)

- [x] 1.1 Create `tests/unit/test_narrative_scripting.py` with failing tests asserting 120-145 word count boundaries and seamless loop continuity for Shorts.
- [x] 1.2 Add unit tests for dynamic LaloBeRoth/JOMOSU hook synthesis, incident crossovers (Clef-Kondraki, 096-1-A), and D-Class 3-stage test logs.
- [x] 1.3 Add contract validation tests for `CinematicScriptCuratorAgent.curate()` against `schemas/script_curator.schema.json`.

## Phase 2: Narrative Curator & Voice Stances Implementation (GREEN)

- [x] 2.1 Refactor `src/curators/moku_horror.py` to replace static boilerplate with dynamic LaloBeRoth/JOMOSU hooks and seamless loop connectors.
- [x] 2.2 Update `src/agents/script_curator.py` to support `moku-scp-shorts` with dual voice stances (Institutional Archivist vs Conversational Incident Narrator).
- [x] 2.3 Implement anti-cliché filters in `src/agents/script_curator.py` to strip dead phrases and enforce 7-10s scene durations.

## Phase 3: Narrative Engine & SFX Synchronization (GREEN)

- [x] 3.1 Update `src/narrative/archetypes.py` with calibrated 34-48 Hz drone frequencies, Rec.709 palettes, and tension-mapped shader presets.
- [x] 3.2 Update `src/narrative/engine.py` to enforce 7-10s scene slicing bounds and seamless loop continuity phrase validation.
- [x] 3.3 Synchronize `_build_sfx_timeline` in `src/narrative/engine.py` with tension spikes (sub-drops, geiger clicks, radio static bursts).

## Phase 4: Verification & Schema Integrity (REFACTOR)

- [x] 4.1 Run full unit test suite via `pytest tests/unit/test_narrative_scripting.py -v`.
- [x] 4.2 Validate end-to-end output against `schemas/script_curator.schema.json` and ensure offline zero-quota execution.
