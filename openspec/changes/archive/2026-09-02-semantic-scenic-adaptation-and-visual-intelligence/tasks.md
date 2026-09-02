# Tasks: Layered Atmospheric Visual Intelligence & Maritime Lighthouse Engine

## Review Workload Forecast

| Field | Value |
| :--- | :--- |
| Estimated changed lines | 280-350 lines |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-chain |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Maritime Lighthouse WGSL Shader & Catalog Integration | PR 1 | `.venv/bin/pytest tests/unit/test_loop_video_engine.py` | `NativeProceduralEngine.render_frame` | `src/media/shaders/maritime_lighthouse.wgsl` |
| 2 | Semantic Detector & Multi-Layer Thumbnail Composition | PR 1 | `.venv/bin/pytest tests/unit/test_channel_profile_and_thumbnails.py` | `ThumbnailEngine.generate` | `src/media/thumbnails/subject_extractor.py`, `src/core/scenic_detector.py` |

## Phase 1: Shader Engine & Archetype Foundation

- [x] 1.1 Create `src/media/shaders/maritime_lighthouse.wgsl` featuring rotating beacon beam, sine-fBm ocean waves, rocky cliff, nocturnal moon with cratered halo, and drifting cloud strata.
- [x] 1.2 Register `maritime_lighthouse` in `VALID_ARCHETYPES` and configure default accent palette (`#00E5FF` / `#FFB300`) in `src/media/native_procedural.py`.
- [x] 1.3 Pre-render and register vertical 1080x1920 MP4 loop in SQLite loop catalog `LoopCatalogRepository`.

## Phase 2: Semantic Scenic Detection & Layered Thumbnail Composition

- [x] 2.1 Add `maritime_lighthouse` narrative keywords (`faro`, `faro de sindicado`, `mar`, `océano`, `costa`, `acantilado`, `olas`, `naufragio`, `muelle`, `isla`) in `src/core/scenic_detector.py`.
- [x] 2.2 Update `src/media/thumbnails/subject_extractor.py` with multi-layered scenic props: cratered moon with halo, horizontal cloud ribbons, sea wave crests, and lighthouse tower body with beacon beam.
- [x] 2.3 Update `config/channels/moku.json` to map maritime/nautical story themes to `maritime_lighthouse`.

## Phase 3: Testing & Verification

- [x] 3.1 Run unit test suite covering scenic classifier and thumbnail engine (`test_channel_profile_and_thumbnails.py`, `test_loop_video_engine.py`).
- [x] 3.2 Generate and visually inspect sample thumbnail containing moon, clouds, ocean, and lighthouse tower.
- [x] 3.3 Validate zero-error execution in full pipeline runner.
