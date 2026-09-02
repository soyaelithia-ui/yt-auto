# Tasks: Dynamic Shorts Multi-Shot Cadence, Script Boilerplate Sanitization, and Adaptive Thumbnail Subject Compositing

This document details the actionable, hierarchically numbered engineering tasks required to implement and verify the dynamic shorts pacing, outro sanitization, and thumbnail subject compositing.

---

## Phase 1: Outro & Boilerplate Script Sanitization (TDD & Implementation)

- [x] **1.1 Unit tests for outro boilerplate sanitization**
  - [x] 1.1.1 Add unit tests in `tests/unit/test_outro_sanitizer.py` verifying that strings like `"Todos los expedientes y archivos se encuentran en Moku Reddit*"` are dropped.
  - [x] 1.1.2 Verify that `@MokuRedit`, `@Moku Reddit`, and `@Aelithia` handle references are stripped cleanly.
  - [x] 1.1.3 Verify that `repair_forbidden_editorial()` strips trailing custodial sentences without mangling valid horror narrative text.
- [x] **1.2 Verify `src/sanitizer.py` and `src/llm.py` enforcement**
  - [x] 1.2.1 Confirm `FORBIDDEN_EDITORIAL_PATTERNS` regex compiles and executes with sub-millisecond latency.
  - [x] 1.2.2 Confirm `_FORBIDDEN_EDITORIAL_DIRECTIVE` in `src/llm.py` warns against outro plugs.

---

## Phase 2: Adaptive Thumbnail Subject Compositor (TDD & Implementation)

- [x] **2.1 Unit tests for `AdaptiveSubjectCompositor`**
  - [x] 2.1.1 Add unit tests in `tests/unit/test_subject_compositor.py` asserting `composite_thematic_subject()` accepts an image, archetype, and accent color.
  - [x] 2.1.2 Verify that all 9 archetypes (`maritime_lighthouse`, `tactical_chamber`, `dark_forest`, `arctic_desolation`, `cosmic_singularity`, `arcade_vector_flight`, `parkour_runner`, `cozy_hearth`, `synaptic_network`) render without crashing.
  - [x] 2.1.3 Verify that output image matches input dimensions (e.g. 1080x1920 or 1280x720) and RGBA/RGB mode.
  - [x] 2.1.4 Verify that central focal region has non-zero alpha blending and rim-light glow.
- [x] **2.2 Verify `src/media/thumbnails/engine.py` integration**
  - [x] 2.2.1 Confirm `ThumbnailEngine` calls `AdaptiveSubjectCompositor.composite_thematic_subject()` prior to typography rendering.

---

## Phase 3: Multi-Camera Shot Cadence for Shorts (TDD & Implementation)

- [x] **3.1 Unit tests for multi-shot planning**
  - [x] 3.1.1 Add unit tests in `tests/unit/test_multi_shot_cadence.py` testing audio partitioning logic:
    - Audio <= 14s produces 1 shot.
    - Audio 15s–25s produces 2 shots.
    - Audio 26s–36s produces 3 shots.
    - Audio > 36s produces 4 shots (capped at 4).
  - [x] 3.1.2 Verify sum of shot durations exactly equals total audio duration within 0.001s tolerance.
  - [x] 3.1.3 Verify distinct seed progression across shots (`s_idx * 101`).
- [x] **3.2 Verify `src/pipeline.py` multi-shot execution**
  - [x] 3.2.1 Verify `visual_plan.json` serialization with `scenes` and `shot_durations`.

---

## Phase 4: Verification, Full Suite & Archive

- [x] **4.1 Run full unit and integration test suites**
  - [x] 4.1.1 Execute all newly added tests.
  - [x] 4.1.2 Execute entire test suite (`pytest`) ensuring 100% pass rate.
- [x] **4.2 OpenSpec state sync and archive**
  - [x] 4.2.1 Update tasks status to complete.
  - [x] 4.2.2 Move change to `openspec/changes/archive/`.
