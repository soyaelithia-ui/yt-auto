# TEST READY: yt-auto Visual Quality, Subtitles & Narrative Coherence E2E Test Suite

**Publication Date**: 2026-09-07T19:48:00Z  
**Author**: Test Writer (`teamwork_preview_test_writer_e2e_1`)  
**Scope Reference**: `PROJECT.md` (teamwork_preview_orchestrator_2) & `ORIGINAL_REQUEST.md` (## 2026-09-07T19:33:24Z)  
**Status**: **READY & CERTIFIED**

---

## 1. Executive Summary

The complete, opaque-box, requirement-driven E2E test suite for `yt-auto` has been designed, implemented, and verified in accordance with the Dual Track protocol.

All 57 newly authored test cases across 5 dedicated modules are 100% discoverable and executable under the offline test profile (`tests/conftest.py`) with zero network quota consumption.

### Execution Results
- **Total Test Items in Suite**: 167 items (57 new R1-R4 tests + 110 baseline tests)
- **Pass Count**: 148 passed
- **XFail Count (Pending Milestones)**: 13 xfailed (clearly isolating pending features in M1, M2, M3, M4)
- **Skipped (Quarantined/Live)**: 6 skipped
- **Failures / Errors**: **0 failed, 0 errors**
- **Execution Duration**: ~24.7s for the entire suite (5.0s for the new R1-R4 suite)

---

## 2. 4-Tier Test Suite Architecture & Breakdown

| Tier | Purpose | Coverage / Metrics | Test Files |
| :--- | :--- | :--- | :--- |
| **Tier 1: Feature Coverage** | Verify primary happy path for every feature in R1-R4 | >=5 tests per feature (23 tests total) | `test_e2e_loop_catalog.py`<br/>`test_e2e_subtitles_aesthetics.py`<br/>`test_e2e_narrative_coherence.py`<br/>`test_e2e_resource_stability.py` |
| **Tier 2: Boundary & Corner Cases** | Stress edge cases: 0-duration, extreme lengths, empty inputs, missing assets, corrupt files, SQL injection | >=5 tests per feature (22 tests total) | Same as above |
| **Tier 3: Cross-Feature Interactions** | Pairwise coverage across subsystems | 5 tests: Subtitles + Multi-scene loops, Pre-TTS + Audio, Seeded rotation + Channel isolation | All test files & `test_e2e_pipeline_canary.py` |
| **Tier 4: Real-World Workload Scenarios** | Realistic end-to-end production runs under offline profile | 4 tests: Moku Horror Short, Moku Horror Long, Aelithia Drama Short, Aelithia Drama Long | `test_e2e_pipeline_canary.py` |
| **Total** | **Complete Requirement Matrix** | **57 New Tests** | **5 Test Modules** |

---

## 3. Detailed Feature Mapping

### Requirement R1: Loop Catalog Activation & SQLite Indexing (`test_e2e_loop_catalog.py`)
- **F1 (Loop Scan)**: Validates >=64 cinematic loop MP4/WebM files exist in `assets/loops/horizontal` and `vertical` (88 discovered).
- **F2 (DB Indexing)**: Contract test for `sync_catalog_from_assets()` indexing >50 loops into SQLite table `video_loops`.
- **F3 (Auto-Seeding)**: Verifies `LoopCatalogRepository` auto-seeds when `count_loops() < 50` on empty DB startup.
- **F4 (Category Aliasing)**: Verifies `LoopVideoEngine.THEMATIC_CATEGORIES` and `CATEGORY_ALIASES` map semantic themes (`tactical_chamber` -> `horror`, `drama_aita` -> `drama`, etc.).
- **F5 (Channel Isolation & Rotation)**: Verifies `channel="moku"` resolves horror loops and `channel="aelithia"` resolves drama loops with deterministic seeded rotation.
- **F6 (Deprecate Monochrome Defaults)**: Verifies default rotation pool excludes flat monochrome placeholders (`loop_maritime_lighthouse_h`, `loop_arctic_desolation_v`).
- **Boundaries**: Empty asset dir sync, corrupt/zero-byte (<25KB) exclusion, unknown category fallback, exclude all loops, non-video extension pruning, SQL injection safety.

### Requirement R2: Dynamic Subtitles & Aesthetic Enrichment (`test_e2e_subtitles_aesthetics.py`)
- **F7 (Subtitle Reactivation)**: Verifies `subtitles_active = True` in `src/pipeline.py`.
- **F8 (Aesthetic Typography & Margins)**: Verifies `Montserrat-Black` styling with high contrast outline/shadow, vertical safe margins $MarginV \ge 480$px (preventing UI overlay occlusion in Shorts), and horizontal margins $MarginV \ge 130$px.
- **F9 (Multi-Scene Pacing)**: Verifies longform scene subdivision into 8-15s shots in `scene_planner.py`.
- **F10 (Multi-Scene Video Composition)**: Verifies `LoopVideoEngine` multi-scene background composition.
- **F11 (Single-Pass FFmpeg Enrichment)**: Verifies libass subtitle burning clause formatting and path escaping.
- **Boundaries**: Empty word timestamps, single-word cue rendering, 120-word cue wrapping, missing font fallback, negative cue timestamp clamping, excessive downward drift clamping.

### Requirement R3: Narrative Coherence & Quality Gate (`test_e2e_narrative_coherence.py`)
- **F12 (3-Act Narrative Structure)**: Verifies hook, buildup/conflict, and climax/resolution.
- **F13 (Single POV Consistency)**: Detects erratic perspective swapping (1st vs 3rd person collision).
- **F14 (Neutral Spanish & Anti-Crutches)**: Validates inverted question/exclamation punctuation (`¿`, `¡`) and rejects repetitive formulaic clickbait crutches ("Pero antes de empezar", "No vas a creer").
- **F15 (Pre-TTS Quality Gate)**: Verifies `validate_narrative_coherence` interface returns `ValidationResult(valid, errors, score)`.
- **F16 (Story Fallback Diversity)**: Verifies dynamic thematic fallbacks produce distinct stories for Moku vs Aelithia.
- **Boundaries**: Empty script rejection, under minimum word count (<115 words for shorts), over maximum word count (>170 words for shorts), unpaired inverted punctuation, English/Spanglish leakage rejection, forbidden channel alias leakage (`canal_terror`, `soy_el_malo`).

### Requirement R4: Bare-Metal Efficiency & Supervisor (`test_e2e_resource_stability.py`)
- **F17 (Render Timeouts & Presets)**: Enforces strict render timeout limits (<=300s shorts, <=900s longs) and fast presets (`veryfast`, `ultrafast`).
- **F18 (Memory RSS Tracking)**: Verifies child process RSS memory inspection via `resource.getrusage(resource.RUSAGE_CHILDREN)`.
- **F19 (Regression Integrity)**: Verifies database repository access without locking errors.
- **F20 (Supervisor Stability)**: Verifies `./deploy/ctl.sh status` contract checking `ytauto-sched` and `ytauto-bot`.
- **Boundaries**: `FFmpegTimeoutError` exception inheritance and attributes, disk space budget gatekeeper, 0-byte partial output cleanup, stale PID lock recovery, CPU core concurrency budget.

### Tier 4 Real-World Workload Scenarios (`test_e2e_pipeline_canary.py`)
- `test_workload_moku_horror_short_offline`: 1080x1920 vertical canvas, 3-act horror script, Montserrat ASS subtitles, AAC audio, faststart moov atom container audit.
- `test_workload_moku_horror_long_offline`: 1920x1080 horizontal canvas, horror longform pacing, safe margin $MarginV \ge 130$px, AAC audio, faststart.
- `test_workload_aelithia_drama_short_offline`: 1080x1920 vertical canvas, human drama narrative, drama loop resolution, dynamic subtitles.
- `test_workload_aelithia_drama_long_offline`: 1920x1080 horizontal canvas, drama multi-scene composition, AAC audio, faststart.

---

## 4. How to Execute the Test Suite

```bash
# Run the entire E2E test suite (167 test cases)
.venv/bin/pytest tests/e2e/ -v

# Run the 5 new visual quality and narrative coherence modules (57 test cases)
.venv/bin/pytest tests/e2e/test_e2e_loop_catalog.py tests/e2e/test_e2e_subtitles_aesthetics.py tests/e2e/test_e2e_narrative_coherence.py tests/e2e/test_e2e_resource_stability.py tests/e2e/test_e2e_pipeline_canary.py -v
```

---

## 5. Certification & Sign-off

The test infrastructure is complete, hermetic, fully passing, and ready for implementing agents to execute progressive verification across Milestones M1 through M5.
