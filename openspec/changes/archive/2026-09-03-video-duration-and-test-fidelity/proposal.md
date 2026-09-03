# Proposal: Video Duration Calibration and Test Suite Fidelity

## Motivation
Testing longform channels (`aelithia-aita-long`, `moku-horror-long`) produced 1-to-3 minute videos in test runs or directed runs, falling short of the required $\ge 10$ minute ($600\text{s} \le \text{duration} \le 1800\text{s}$) target. Concurrently, unit tests involving daemon and pipeline safety ran heavy live software WebGPU (Mesa Lavapipe) and FFmpeg renders of 18,150 frames (605s), consuming excessive CPU and taking 8-15 minutes, violating `pytest.ini` unit test constraints.

## Goals
1. **Calibrate Longform Word Budget**: Expand narrative templates (`build_aelithia_longform_narrative`, `build_moku_longform_narrative`) to $\ge 2,800$ words across structured dramatic beats to ensure $\ge 600\text{s}$ narration at Spanish speech cadence.
2. **Directed Duration Enforcement**: Enforce minimum longform duration ($\ge 600\text{s}$) in `src/pipeline.py` for all runs, including directed runs (`--topic`/`--story-id`).
3. **Unit Test Compositor Isolation**: Mock `MultiSceneCompositor.render` in unit tests (`test_daemon.py`, `test_directed_story_safety.py`) to keep unit tests fast (<4s) without CPU-heavy software rasterization.
4. **Lane Curation Consistency**: Align `script_curator` tension curves and scene count boundaries with `LANE_CURATION_CONFIGS`.

## Capabilities

### Modified Capabilities
- `adaptive-narrative-curation`: Enforce $\ge 2,800$ word templates and 5–8 scene bounds for longform productions.
- `media-pipeline-hardening`: Enforce duration gates on directed executions and isolate compositor rendering in unit suites.

## Non-Goals
- Modifying short-form video pipelines (vertical 60s shorts remain unchanged).
- Modifying audio mastering (EBU R128) or subtitle rendering.

## Performance Impact
Sub-second execution for all unit tests; eliminates CPU spikes during test runs.

## Rollback Plan
Revert template expansions and compositor mock patches via git.
