# Implementation Tasks: Visual Diversity & QA Guardrails

## Phase 1: Pacing Calculator (TDD)
- [x] 1.1 Create unit test `tests/unit/test_scene_pacing.py` with scenarios for short and longform pacing bounds (RED).
- [x] 1.2 Implement `src/media/pacing.py` with `compute_dynamic_shot_pacing()` to satisfy tests (GREEN).

## Phase 2: QA Scene Diversity Gate (TDD)
- [x] 2.1 Create unit test `tests/unit/test_qa_scene_diversity.py` verifying rejection of 4-scene longform and single-asset dominance (RED).
- [x] 2.2 Implement `lib/qa/diversity_gate.py` with `SceneDiversityGate` (GREEN).

## Phase 3: QA Luminance & Contrast Gate (TDD)
- [x] 3.1 Create unit test `tests/unit/test_qa_luminance.py` with near-black and chiaroscuro test frames (RED).
- [x] 3.2 Implement `LuminanceContrastGate` in `lib/qa/diversity_gate.py` (GREEN).

## Phase 4: Integration and Verdict Wiring
- [x] 4.1 Wire `compute_dynamic_shot_pacing` into `src/pipeline.py` replacing `min(4, ...)`.
- [x] 4.2 Register both gates in `src/core/verdict.py` and `lib/qa/engine.py`.
- [x] 4.3 Run full anti-regression suite (`./scripts/verify_integrity.sh`) to confirm 100% pass and 0 regressions.
