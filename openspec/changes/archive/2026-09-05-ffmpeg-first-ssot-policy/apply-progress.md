# Apply Progress: ffmpeg-first-ssot-policy

**Change**: ffmpeg-first-ssot-policy
**Mode**: Strict TDD
**Workload**: size:exception (single PR; maintainer accepted)
**Work unit**: rebase-ssot-onto-main (tasks 1.1–4.2 preserved; 5.1–5.6 this batch)

## Completed Tasks

- [x] 1.1 Run fail-closed pytest pair (read-only tests)
- [x] 1.2 Confirm spec/config-only apply (no renderer/`_legacy`/HUD 0a90158)
- [x] 2.1 Merge procedural-scene-compositor main spec
- [x] 2.2 Merge media-processing-performance-policy main spec
- [x] 2.3 Merge editorial-and-content-policy main spec
- [x] 2.4 Merge media-pipeline-hardening full MODIFIED (not nested leftover)
- [x] 2.5 Merge legacy-eradication-guardrails main spec
- [x] 3.1 Update openspec/config.yaml context
- [x] 4.1 Re-run fail-closed pytest pair
- [x] 4.2 Confirm no production-hot-path MUST wgpu/WebGL/NativeProceduralEngine; HUD MUST NOT wgpu remains
- [x] 5.1 Re-run fail-closed 14/14 on origin/main `d42642e`
- [x] 5.2 RED: retarget REG-11 Pillow thumbs SSOT; write `tests/unit/test_ffmpeg_first_ssot_policy.py`
- [x] 5.3 Slim CHANGE specs to in-scope proposal capabilities (`#### Scenario:` = 12)
- [x] 5.4 GREEN: merge five main specs without clobbering HUD/safe-zone/typography
- [x] 5.5 GREEN: `openspec/config.yaml` Pillow thumbs SSOT; keep projects/zero-browser/testing
- [x] 5.6 Re-run fail-closed 14/14 plus covering tests

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/unit/test_retire_wgpu_hot_path.py`, `tests/unit/test_quarantine_native_procedural.py` | Unit | ✅ 14/14 existing | ✅ Existing fail-closed suite 14/14 | N/A this task (baseline) | ➖ Single: do not invent renderer tests | ➖ None needed |
| 1.2 | same pair (scope gate) | Unit | ✅ 14/14 | ✅ Baseline already green | ✅ Spec/config-only; no src/_legacy/HUD 0a90158 | ➖ Structural scope check | ➖ None needed |
| 2.1–4.2 | same pair | Unit | ✅ 14/14 | ✅ Prior batch on wrong base; re-applied this rebase | ✅ 14/14 after origin/main merge | ➖ Fail-closed pair remains the runtime contract | ➖ Markdown merge only |
| 5.1 | fail-closed pair | Unit | ✅ 14/14 on `d42642e` | ✅ 14 passed in 1.70s | N/A baseline | ➖ No renderer suites | ➖ None needed |
| 5.2 | `tests/unit/test_anti_regression_guardrails.py`, `tests/unit/test_ffmpeg_first_ssot_policy.py` | Unit | ✅ 14/14 | ✅ REG-11 + covering tests failed 9 (Pillow thumbs, production MUST wgpu, fat CHANGE specs) | ✅ After config/spec slim/merge | ✅ Config FFmpeg+Pillow vs projects/zero-browser; HUD preservation; hot-path imports | ✅ Parser treats `TERM … MUST NOT` as prohibition |
| 5.3 | `test_change_specs_only_in_scope_scenarios` | Unit | N/A (change specs) | ✅ 38 scenarios | ✅ 12 `#### Scenario:` headings | ✅ Forbidden novel titles empty | ➖ Slim rewrite |
| 5.4 | covering spec tests | Unit | ✅ HUD approval green before merge | ✅ Production MUST FFmpeg/lavfi/ProceduralVideoEngine missing | ✅ Five main specs merged; HUD top_bar/card/bottom_bar + AspectLayoutManager kept | ✅ Per-domain positive assertions | ➖ Compact opt-in restatements on MAIN |
| 5.5 | REG-11 + config covering tests | Unit | ✅ projects/zero-browser/testing already green | ✅ Pillow thumbs missing | ✅ `Pillow thumbs SSOT` in context; no wgpu-py/resvg-py/Playwright | ✅ Keep projects + testing notes | ➖ One context line |
| 5.6 | fail-closed pair + covering | Unit | ✅ 14/14 | ✅ Re-run GREEN gate | ✅ 27 passed in 1.90s | ➖ Same files | ➖ None needed |

### Test Summary

- **Total tests written**: 12 new in `test_ffmpeg_first_ssot_policy.py` plus retargeted REG-11
- **Total tests passing**: 27 (14 fail-closed + 12 covering + 1 REG-11)
- **Layers used**: Unit (27), Integration (0), E2E (0)
- **Approval tests** (refactoring): 14 fail-closed + HUD/projects/zero-browser assertions
- **Pure functions created**: 0 (spec/config ratification)

## Work Unit Evidence

| Evidence | Required value |
|---|---|
| Focused test command and exact result | `.venv/bin/python -m pytest tests/unit/test_retire_wgpu_hot_path.py tests/unit/test_quarantine_native_procedural.py tests/unit/test_ffmpeg_first_ssot_policy.py tests/unit/test_anti_regression_guardrails.py::TestRetiredSubsystemGuardrails::test_reg11_zero_playwright_in_openspec_config -v` → RED 9 failed / 18 passed; GREEN 27 passed in 1.90s; exit 0. Fail-closed pair 14/14 throughout. |
| Runtime harness command/scenario and exact result | N/A — spec/config ratification; runtime unchanged; no ENABLE_NATIVE_PROCEDURAL renderer suites |
| Rollback boundary | `openspec/specs/procedural-scene-compositor/spec.md`, `openspec/specs/media-processing-performance-policy/spec.md`, `openspec/specs/editorial-and-content-policy/spec.md`, `openspec/specs/media-pipeline-hardening/spec.md`, `openspec/specs/legacy-eradication-guardrails/spec.md`, `openspec/config.yaml`, `tests/unit/test_anti_regression_guardrails.py`, `tests/unit/test_ffmpeg_first_ssot_policy.py`, change folder `specs/` + `tasks.md` + `apply-progress.md` |

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `openspec/specs/procedural-scene-compositor/spec.md` | Modified | FFmpeg SSOT / wgpu opt-in; kept origin/main HUD hud_layout top_bar/card/bottom_bar, AspectLayoutManager, typography |
| `openspec/specs/media-processing-performance-policy/spec.md` | Modified | Production MUST FFmpeg; wgpu-py/resvg-py not production; stream-copy when `stream_copy_mode` |
| `openspec/specs/editorial-and-content-policy/spec.md` | Modified | Backgrounds MUST FFmpeg loops, not WebGL/Three.js/Canvas |
| `openspec/specs/media-pipeline-hardening/spec.md` | Modified | Req 2 rawvideo opt-in; Req 8 lavfi; Req 10 default `ProceduralVideoEngine()` |
| `openspec/specs/legacy-eradication-guardrails/spec.md` | Modified | Pillow thumbs allowed; wgpu-py/resvg-py not production |
| `openspec/config.yaml` | Modified | Pillow thumbs SSOT; kept projects/zero-browser/testing; no wgpu-py/resvg-py production |
| `tests/unit/test_anti_regression_guardrails.py` | Modified | REG-11 retargeted: require Pillow thumbs; forbid Playwright/wgpu-py/resvg-py as production |
| `tests/unit/test_ffmpeg_first_ssot_policy.py` | Created | Covering tests for remaining CHANGE scenarios; no renderer suites |
| `openspec/changes/ffmpeg-first-ssot-policy/specs/**/spec.md` | Modified | Slimmed to 8 requirements / 12 `#### Scenario:` headings |
| `openspec/changes/ffmpeg-first-ssot-policy/tasks.md` | Modified | Kept 1.1–4.2 `[x]`; added 5.1–5.6 `[x]` |
| `openspec/changes/ffmpeg-first-ssot-policy/apply-progress.md` | Modified | This artifact |

## Deviations from Design

None — spec/config + covering tests only. No renderer rewrite, no `_legacy` delete, no HUD `0a90158`.

## Issues Found

Prior apply/verify on HUD branch `0a90158` produced 38 CHANGE scenarios / 28 UNTESTED. This rebase slims CHANGE specs to 12 in-scope scenarios with covering tests.

## Remaining Tasks

None. 16/16 complete.

## Workload / PR Boundary

- Mode: size:exception
- Current work unit: rebase-ssot-onto-main
- Boundary: fail-closed RED → slim CHANGE specs + origin/main spec/config merge + covering tests → GREEN 27/27
- Estimated review budget impact: High (forecast 500–700); do not shrink docs. Tracked main-spec+config+REG-11 git numstat 137 insertions / 117 deletions; change-folder slim and new covering tests are additional untracked.

## Status

16/16 tasks complete. Ready for verify.
