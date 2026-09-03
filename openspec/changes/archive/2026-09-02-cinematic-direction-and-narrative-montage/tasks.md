# Tasks: Cinematic Direction and Narrative Montage Pipeline Evolution

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 240–320 lines |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Photometric floor & WebGPU uniform adapter | PR 1 | `pytest tests/unit/test_native_procedural_uniforms.py` | Native render of maritime lighthouse | `src/media/shaders/`, `src/media/native_procedural.py` |
| 2 | Storyboard curation & upstream archetype resolution | PR 1 | `pytest tests/unit/test_cinematic_storyboard.py` | Curation dry-run on longform story | `src/agents/` |
| 3 | Pipeline dispatch & multiscene composition wiring | PR 1 | `pytest tests/integration/test_multiscene_dispatch.py` | End-to-end dry pipeline run | `src/pipeline.py`, `src/media/` |

## Phase 1: Photometric Floor and WebGPU Uniform Bridge (TDD)

- [x] 1.1 Create `tests/unit/test_native_procedural_uniforms.py` with RED tests for 64-byte buffer alignment, BrokenPipe handling, and safe argument lists.
- [x] 1.2 Update `src/media/shaders/maritime_lighthouse.wgsl` to enforce minimum 18% luminance floor and sRGB transfer.
- [x] 1.3 Update `src/media/native_procedural.py` to map art parameters into 16-float uniform struct with `BrokenPipeError` exception guard.

## Phase 2: Narrative Storyboarding and Archetype Resolution (TDD)

- [x] 2.1 Create `tests/unit/test_cinematic_storyboard.py` with RED tests for 5–8 scene acts (60–150s), transition reasons, and explicit archetype propagation.
- [x] 2.2 Modify `src/agents/script_curator.py` to implement semantic storyboard segmentation for longform formats without 11s arithmetic cuts.
- [x] 2.3 Update `src/agents/art_director.py` to assign canonical WGSL archetypes and Kelvin/palette uniforms to curated scenes.
- [x] 2.4 Update `src/agents/scene_planner.py` to ingest upstream archetypes directly and disable 11s sub-shot slicing.

## Phase 3: Engine Wiring and Pipeline Dispatch (TDD)

- [x] 3.1 Create `tests/integration/test_multiscene_dispatch.py` with RED tests for `visual_pipeline: "director"` dispatch and invalid engine error handling.
- [x] 3.2 Update `src/media/proc_engine.py` to pass art uniform parameters into `NativeProceduralEngine`.
- [x] 3.3 Update `src/media/compositor.py` to inject `NativeProceduralEngine` into `ProceduralVideoEngine`.
- [x] 3.4 Update `src/pipeline.py` to resolve `visual_pipeline: "director"` to multiscene engine and reject unrecognized modes without silent fallback.

## Phase 4: Verification and Quality Gate

- [x] 4.1 Run test suite: `pytest tests/unit/test_native_procedural_uniforms.py tests/unit/test_cinematic_storyboard.py tests/integration/test_multiscene_dispatch.py`.
- [x] 4.2 Verify full E2E pipeline dry run with mock longform lane and confirm zero fallback to loop mode.
