# Change Proposal: Visual Diversity Scaling and QA Scene Invariants

## 1. Context and Problem Statement

Recent production audits of longform video deliveries (Moku 14m 25s and Aelithia 10m 13s) revealed critical visual quality regressions:
1. **Arithmetic Shot Cap**: In `src/pipeline.py` (line 908), `shot_count` is hard-capped via `min(4, ...)`. A 15-minute video is mechanically divided into 4 shots lasting ~216 seconds each.
2. **Single-Asset Infinite Looping**: `LoopVideoEngine.render()` in `src/pipeline.py` (line 1003) supplies only one `background_path` to FFmpeg, looping a 6-second video hundreds of times regardless of narrative progression.
3. **QA Gatekeeper Blindspot**: `QAGatekeeper` and `src/core/verdict.py` validate per-frame sharpness and EBU R128 audio, but lack temporal diversity checks and average luminance thresholds, allowing single-background and near pitch-black frames to be approved as production-grade.

## 2. Proposed Changes

We introduce three targeted, production-hardened capabilities:

1. **`scene-pacing-scaling`**: Replace the static `min(4, ...)` cap with a dynamic shot pacing formula designed for longform and short formats (shots bounded between 15s and 45s for longform, 8s and 15s for shorts), selecting diverse background assets from the catalog across acts.
2. **`qa-scene-diversity-gate`**: A deterministic quality gate in the QA subsystem that audits scene manifests and video transitions. Rejects any production $\ge 5$ minutes with fewer than 6 distinct scenes or where a single visual asset exceeds 25% of the total runtime.
3. **`qa-luminance-contrast-gate`**: An optical QA gate evaluating average perceived luminance and darkness distribution across sampled frames, detecting "false black" scenes where over 85% of pixels are under-illuminated ($Y < 16$ in digital 8-bit Rec.709).

## 3. Capabilities Introduced

- `specs/scene-pacing-scaling/spec.md`: Behavioral specification for dynamic scene shot calculation, act-based pacing, and non-repeating asset resolution.
- `specs/qa-scene-diversity-gate/spec.md`: Specification for the temporal scene diversity gate in `lib/qa/` and `src/core/verdict.py`.
- `specs/qa-luminance-contrast-gate/spec.md`: Specification for average luminance floor and low-contrast shadow detection in video frames.

## 4. Impact Assessment & Risk Mitigation

- **Performance SLA**: Shot calculation is strictly arithmetic ($\le 5\text{ms}$). QA frame sampling uses existing 1.0 fps probe routines without introducing external dependencies or browser runtimes.
- **Zero-Browser Policy**: Preserved 100%. All computations use native Python math, Pillow/OpenCV/FFmpeg lavfi, and existing SQLite catalog lookups.
- **Rollback Plan**: Changes are isolated behind standard gate evaluations and configurable lane defaults. If needed, legacy loop fallback can be engaged via configuration flag.
