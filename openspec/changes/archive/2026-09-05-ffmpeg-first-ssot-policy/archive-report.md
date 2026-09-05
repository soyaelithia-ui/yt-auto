# Archive Report: ffmpeg-first-ssot-policy

**Change Name**: `ffmpeg-first-ssot-policy`
**Archived To**: `openspec/changes/archive/2026-09-05-ffmpeg-first-ssot-policy/`
**Archive Date**: `2026-09-05`
**Status**: Closed & Shipped

---

## 1. Executive Summary

Ratified FFmpeg-first as the production media SSOT across five OpenSpec domains and `openspec/config.yaml`. Native WebGPU/GLSL/WebGL/`NativeProceduralEngine` remain opt-in behind `ENABLE_NATIVE_PROCEDURAL` under `src/media/_legacy`. Pillow remains allowed for thumbnail SSOT; Playwright stays forbidden as production media. Runtime renderers were not rewritten in this change (spec/config ratification only).

---

## 2. Specs Synced to Source of Truth

Main specs were already merged during apply (PR #23 / `a7bc6bb`) and remain the source of truth. Archive did not re-apply MODIFIED deltas by heading rename, which would have duplicated numbered requirements.

| Domain | Action | Details |
|--------|--------|---------|
| `procedural-scene-compositor` | Already updated | FFmpeg lavfi / stream-copy / `DIRECTOR_SINGLE_PASS` / drawtext HUD; native stack opt-in |
| `media-processing-performance-policy` | Already updated | Production MUST FFmpeg; wgpu-py/resvg-py not production; `-c:v copy` when `stream_copy_mode` |
| `editorial-and-content-policy` | Already updated | Backgrounds MUST FFmpeg loops; WebGL/Three.js/Canvas MUST NOT |
| `media-pipeline-hardening` | Already updated | Rawvideo stdin opt-in; lavfi catalog; `ProceduralVideoEngine()` default |
| `legacy-eradication-guardrails` | Already updated | Pillow thumbs allowed; Playwright/wgpu-py/resvg-py not production |

Mechanical `diff -r` of the change folder vs archive destination: empty (byte-identical).

---

## 3. Tasks Reconciliation

- **Total Implementation Tasks**: 16
- **Completed Tasks**: 16 (100%)
- **Pending / Unchecked Tasks**: 0
- **Task Completion Gate**: Passed. `tasks.md` has no unchecked implementation items.
- **state.yaml**: `status: completed`, `current_phase: archive`

---

## 4. Verification Proof

- **verify-report**: verdict `pass`; 0 CRITICAL; 8/8 requirements; 12/12 scenarios; 27/27 covering tests at verification time.
- **Covering tests**: `tests/unit/test_ffmpeg_first_ssot_policy.py` now resolves change specs from `openspec/changes/archive/*-ffmpeg-first-ssot-policy` after this archive.

---

## 5. Archived Artifacts Manifest

- `proposal.md`
- `exploration.md`
- `design.md`
- `tasks.md`
- `apply-progress.md`
- `verify-report.md`
- `state.yaml`
- `specs/` (five domain deltas)

---

## 6. SDD Cycle Complete

The change has been planned, implemented, verified, and archived. Ready for the next change.
