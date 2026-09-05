# Tasks: FFmpeg-First SSOT Policy

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 500–700 (full MODIFIED markdown replacements; no app code) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 compositor+perf → PR2 editorial+hardening → PR3 guardrails+config |
| Delivery strategy | size-exception |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: size-exception
400-line budget risk: High

size-exception already recorded. Keep one slice.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Compositor + performance SSOT | PR 1 | `pytest tests/unit/test_retire_wgpu_hot_path.py tests/unit/test_quarantine_native_procedural.py` | N/A — spec/config ratification; runtime unchanged | `openspec/specs/procedural-scene-compositor/spec.md`, `openspec/specs/media-processing-performance-policy/spec.md` |
| 2 | Editorial + hardening full MODIFIED | PR 2 | same pytest pair | N/A — spec/config ratification; runtime unchanged | `openspec/specs/editorial-and-content-policy/spec.md`, `openspec/specs/media-pipeline-hardening/spec.md` |
| 3 | Pillow guardrail + config context | PR 3 | same pytest pair | N/A — spec/config ratification; runtime unchanged | `openspec/specs/legacy-eradication-guardrails/spec.md`, `openspec/config.yaml` |
| 4 | Rebase onto origin/main + slim CHANGE specs + covering tests | this slice | `.venv/bin/python -m pytest tests/unit/test_retire_wgpu_hot_path.py tests/unit/test_quarantine_native_procedural.py tests/unit/test_ffmpeg_first_ssot_policy.py tests/unit/test_anti_regression_guardrails.py::TestRetiredSubsystemGuardrails::test_reg11_zero_playwright_in_openspec_config -v` | N/A — spec/config ratification; runtime unchanged | five main specs, `openspec/config.yaml`, change specs, covering tests, REG-11 retarget |

## Phase 1: Fail-closed TDD baseline

- [x] 1.1 Run pytest on `tests/unit/test_retire_wgpu_hot_path.py` (read-only) and `tests/unit/test_quarantine_native_procedural.py` (read-only); keep fail-closed; do not invent renderer RED tests.
- [x] 1.2 Confirm apply stays spec/config-only: no renderer rewrites, no `src/media/_legacy` (read-only) deletes, no HUD 0a90158.

## Phase 2: Merge delta specs

- [x] 2.1 Merge `openspec/specs/procedural-scene-compositor/spec.md` from `openspec/changes/ffmpeg-first-ssot-policy/specs/procedural-scene-compositor/spec.md` (read-only): rewrite Capability Overview (drop GLSL/Three.js/WebGL/`xfade` as production); FFmpeg lavfi/stream-copy/DIRECTOR_SINGLE_PASS/drawtext HUD; wgpu/GLSL/WebGL/64-byte/NativeProceduralEngine opt-in; keep HUD MUST NOT wgpu.
- [x] 2.2 Merge `openspec/specs/media-processing-performance-policy/spec.md` from `openspec/changes/ffmpeg-first-ssot-policy/specs/media-processing-performance-policy/spec.md` (read-only): production MUST FFmpeg; wgpu-py/resvg-py not production; MODIFIED Atomic Single-Pass so `-c:v copy` when `stream_copy_mode` and encode only for HUD/scale/xfade/subtitles (raw RGBA stdin opt-in only).
- [x] 2.3 Merge `openspec/specs/editorial-and-content-policy/spec.md` from `openspec/changes/ffmpeg-first-ssot-policy/specs/editorial-and-content-policy/spec.md` (read-only): backgrounds MUST FFmpeg loops, not WebGL/Three.js/Canvas.
- [x] 2.4 Merge full MODIFIED (not nested leftovers) into `openspec/specs/media-pipeline-hardening/spec.md` from `openspec/changes/ffmpeg-first-ssot-policy/specs/media-pipeline-hardening/spec.md` (read-only): rewrite Capability Overview; Req 2 rawvideo stdin opt-in `ENABLE_NATIVE_PROCEDURAL` only; Req 8 lavfi; Req 10 default ProceduralVideoEngine().
- [x] 2.5 Merge `openspec/specs/legacy-eradication-guardrails/spec.md` from `openspec/changes/ffmpeg-first-ssot-policy/specs/legacy-eradication-guardrails/spec.md` (read-only): Pillow thumbs allowed; wgpu-py/resvg-py not production.

## Phase 3: Config

- [x] 3.1 Edit `openspec/config.yaml` context to FFmpeg + Pillow thumbs; drop wgpu-py/resvg-py as production; keep Playwright off production media.

## Phase 4: Verify

- [x] 4.1 Re-run pytest on `tests/unit/test_retire_wgpu_hot_path.py` (read-only) and `tests/unit/test_quarantine_native_procedural.py` (read-only); if fail, inspect runtime — do not preemptively rewrite renderers.
- [x] 4.2 Confirm five main specs have no production-hot-path MUST wgpu/WebGL/NativeProceduralEngine; HUD MUST NOT wgpu remains.

## Phase 5: Rebase onto origin/main, slim CHANGE specs, covering tests

- [x] 5.1 Re-run fail-closed pytest pair on origin/main base (`d42642e`); keep 14/14.
- [x] 5.2 RED: retarget `test_reg11_zero_playwright_in_openspec_config` so config MAY contain Pillow thumbs SSOT, MUST reject Playwright as production media, MUST reject wgpu-py/resvg-py as production stack; write `tests/unit/test_ffmpeg_first_ssot_policy.py` covering remaining CHANGE scenarios.
- [x] 5.3 Slim CHANGE specs under `openspec/changes/ffmpeg-first-ssot-policy/specs/` to in-scope proposal capabilities only (`#### Scenario:` ≤ 12). Do not restate GLSL/camera/particles/watchdog/Popen/xfade novels.
- [x] 5.4 GREEN: merge FFmpeg SSOT into five main specs on origin/main without clobbering HUD `hud_layout` top_bar/card/bottom_bar, AspectLayoutManager safe-zone, or shared typography.
- [x] 5.5 GREEN: update `openspec/config.yaml` with Pillow thumbs SSOT; keep origin/main `projects:` block, zero-browser constraint, and testing notes; do not list wgpu-py/resvg-py as production.
- [x] 5.6 Re-run fail-closed 14/14 plus covering tests (REG-11 + `test_ffmpeg_first_ssot_policy.py`).
