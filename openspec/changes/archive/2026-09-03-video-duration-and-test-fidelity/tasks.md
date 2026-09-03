# Tasks: Video Duration Calibration and Test Suite Fidelity

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 140–180 lines |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Isolate `MultiSceneCompositor` in unit tests for fast hermetic execution | PR 1 | `.venv/bin/pytest tests/unit/test_daemon.py tests/unit/test_directed_story_safety.py -v` | N/A (unit tests) | `tests/unit/test_daemon.py`, `tests/unit/test_directed_story_safety.py` |
| 2 | Expand narrative templates to $\ge 2,800$ words and enforce directed $\ge 600\text{s}$ gate | PR 1 | `.venv/bin/pytest tests/unit/test_narrative_refinement.py -v` | `python main.py run --channel aelithia --topic "Test" --dry-run` | `src/templates/narratives.py`, `src/curators/aelithia_drama.py`, `src/pipeline.py` |

## Phase 1: Unit Test Compositor Isolation (TDD)

- [x] 1.1 RED: Verify `tests/unit/test_daemon.py` and `tests/unit/test_directed_story_safety.py` trigger heavy render when unmocked.
- [x] 1.2 GREEN: Patch `src.media.compositor.MultiSceneCompositor.composite_from_manifest` in `tests/unit/test_daemon.py`.
- [x] 1.3 GREEN: Patch `src.media.compositor.MultiSceneCompositor.composite_from_manifest` in `tests/unit/test_directed_story_safety.py`.
- [x] 1.4 REFACTOR: Confirm both test suites run in under 4 seconds total without spawning ffmpeg rendering processes.

## Phase 2: Longform Narrative Expansion & Calibration

- [x] 2.1 RED: Update `tests/unit/test_narrative_refinement.py` to assert `len(script.split()) >= 2800` for longform templates.
- [x] 2.2 GREEN: Expand `build_aelithia_longform_narrative` in `src/templates/narratives.py` with multi-case dialogue beats ($\ge 2,800$ words).
- [x] 2.3 GREEN: Expand `build_moku_longform_narrative` in `src/templates/narratives.py` with tactical log entries ($\ge 2,800$ words).
- [x] 2.4 GREEN: Update `AelithiaDramaCurator.target_words = 2600` in `src/curators/aelithia_drama.py`.

## Phase 3: Directed Duration Enforcement

- [x] 3.1 RED: Write unit test in `tests/unit/test_daemon_lanes.py` verifying directed run on longform lane validates `duration >= 600.0`.
- [x] 3.2 GREEN: Update `src/pipeline.py` to enforce minimum longform duration check even when `directed=True`.

## Phase 4: Full Suite Verification & Quality Gate

- [x] 4.1 Run unit test suite: `.venv/bin/pytest tests/unit/ -q`.
- [x] 4.2 Run integration test suite: `.venv/bin/pytest tests/integration/ -q`.
- [x] 4.3 Run e2e test suite: `.venv/bin/pytest tests/e2e/ -q`.
- [x] 4.4 Verify zero ffmpeg leaks or orphan processes: `pgrep -f ffmpeg || true`.
