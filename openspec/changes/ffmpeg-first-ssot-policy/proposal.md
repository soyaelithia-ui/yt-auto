# Proposal: FFmpeg-First SSOT Policy

## Intent

Archived purge-legacy/cinematic changes installed WebGPU as production MUST. Code already defaults to FFmpeg (lavfi loops, stream-copy beats, `DIRECTOR_SINGLE_PASS`, drawtext HUD, veryfast/CRF 21). Specs contradict code and each other (HUD MUST NOT wgpu vs NativeProceduralEngine MUST). Ratify FFmpeg as SSOT; keep WebGPU opt-in under `src/media/_legacy`. Succeeds those archives; does not duplicate browser-purge.

## Scope

### In Scope
- Delta five existing specs so production MUST matches code
- Allow Pillow thumbs SSOT in `openspec/config.yaml`; do not drop Pillow
- Context: FFmpeg + Pillow thumbs; wgpu-py/resvg-py not production
- Keep fail-closed tests as contract (`test_retire_wgpu_hot_path.py`, `test_quarantine_native_procedural.py`)

### Out of Scope
- Deleting `src/media/_legacy`; Playwright upload (`src/youtube/`)
- HUD feature work; do not bundle feat/t1 HUD commit `0a90158`
- Full-suite M3, dep pinning, linters, Python 3.11 host vs 3.12 CI

## Capabilities

### New Capabilities
None

### Modified Capabilities
- `procedural-scene-compositor`: Production MUST FFmpeg lavfi / stream-copy / `DIRECTOR_SINGLE_PASS` / drawtext HUD. NativeProceduralEngine / WebGPU / GLSL / WebGL opt-in only (`ENABLE_NATIVE_PROCEDURAL`).
- `media-processing-performance-policy`: Production video MUST FFmpeg, not wgpu-py/resvg-py.
- `editorial-and-content-policy`: Backgrounds MUST FFmpeg procedural loops, not WebGL/Three.js/Canvas.
- `media-pipeline-hardening`: `MultiSceneCompositor` default `ProceduralVideoEngine()`; NativeProceduralEngine only when `ENABLE_NATIVE_PROCEDURAL`; drop WebGPU-as-MUST.
- `legacy-eradication-guardrails`: Allow Pillow in `openspec/config.yaml` (thumbs SSOT); forbid wgpu-py/resvg-py as production stack.

## Approach

Spec-and-context ratification only. Code is already fail-closed. Preserve HUD scenarios that already MUST NOT wgpu. No new HUD on this branch.

**Media processing performance impact:** Avoids wgpu/Lavapipe CPU raster and per-frame Python loops. Homogeneous beats stay `-c:v copy`. HUD is one `filter_complex` at veryfast/CRF 21 only when `niche_hud` is present. Opt-in WebGPU stays off the hot path.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `openspec/specs/procedural-scene-compositor/spec.md` | Modified | FFmpeg SSOT; wgpu opt-in |
| `openspec/specs/media-processing-performance-policy/spec.md` | Modified | Drop wgpu-py/resvg-py MUST |
| `openspec/specs/editorial-and-content-policy/spec.md` | Modified | Drop WebGL/Three.js MUST |
| `openspec/specs/media-pipeline-hardening/spec.md` | Modified | Default compositor path |
| `openspec/specs/legacy-eradication-guardrails/spec.md` | Modified | Pillow allowed |
| `openspec/config.yaml` | Modified | Context stack |
| `src/media/compositor.py`, `_legacy/` | Unchanged | Already FFmpeg default |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Specs drop Pillow thumbs | Med | Guardrail allows Pillow |
| Residual wgpu MUST elsewhere | Low | Spec search hit these five |
| Apply rewrites renderers | Med | Spec/config only unless tests fail |

## Rollback Plan

Revert spec deltas and `openspec/config.yaml` context. Runtime is already FFmpeg-first; no binary rollback. WebGPU remains `ENABLE_NATIVE_PROCEDURAL=1` only.

## Dependencies

None. Compositor default and unit tests encode behavior (re-verified 2026-09-05).

## Success Criteria

- [ ] Five listed specs no longer MUST wgpu/WebGL/NativeProceduralEngine on the production hot path
- [ ] `openspec/config.yaml` lists FFmpeg + Pillow thumbs; not wgpu-py/resvg-py as production
- [ ] Guardrail allows Pillow; still forbids Playwright as production media stack
- [ ] Default compositor and quarantine tests remain fail-closed; HUD `0a90158` not bundled; `_legacy` not deleted
