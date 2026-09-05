# Design: FFmpeg-First SSOT Policy

## Technical Approach

Ratify code as SSOT. Runtime already defaults to FFmpeg lavfi/catalog, `DIRECTOR_SINGLE_PASS`, concat demuxer `-c:v copy` when homogeneous and no `niche_hud`, one `filter_complex` HUD (`drawtext`/`drawbox`, `encode_defaults` veryfast/CRF 21), libass, EBU R128 on master. Deltas in this change folder already encode that. Apply merges them into the five main specs and updates `openspec/config.yaml` context. No renderer rewrite, no `_legacy` delete, no HUD feat/t1 `0a90158`.

## Architecture Decisions

| Decision | Options | Tradeoff | Choice |
|----------|---------|----------|--------|
| SSOT | Specs match code vs restore wgpu vs dual MUST | Dual leaves HUD MUST NOT wgpu vs NativeProceduralEngine MUST; restore fights fail-closed tests | Specs match code |
| Apply surface | Specs+config vs also rewrite engines | Code already fail-closed | Specs+config only unless listed tests fail |
| Native engine | Delete `_legacy` vs keep opt-in | Delete breaks quarantine layout tests | Keep under `src/media/_legacy`; `ENABLE_NATIVE_PROCEDURAL` in {1,true,yes,on} |
| Pillow | Forbid in config vs allow thumbs | Code thumbs are Pillow (`thumbnail_engine.py`) | Allow Pillow thumbs; forbid Playwright media; forbid wgpu-py/resvg-py as production |
| HUD | Bundle `0a90158` vs preserve existing HUD MUST NOT wgpu | Bundling is out of scope | Preserve existing HUD requirement; no new HUD |
| Hardening merge | Nested-delta leftover vs full MODIFIED blocks | Nested merge can leave WebGL MUST fragments | Apply full MODIFIED replacements from this change |

## Data Flow

Unchanged. Apply does not alter this path.

    ENABLE_NATIVE_PROCEDURAL unset
      → MultiSceneCompositor → ProceduralVideoEngine(renderer=None)
      → lavfi/catalog loops
      → DIRECTOR_SINGLE_PASS
           homogeneous, no HUD → concat -c:v copy (loop_stream_copy)
           niche_hud / scale / xfade → one filter_complex encode
      → master EBU R128

    ENABLE_NATIVE_PROCEDURAL=1 → lazy import `_legacy.NativeProceduralEngine` (not production)

## File Changes

Apply only. This phase writes `design.md` only.

| File | Action | Description |
|------|--------|-------------|
| `openspec/specs/procedural-scene-compositor/spec.md` | Modify | Production MUST FFmpeg; rewrite Capability Overview (drop GLSL/Three.js/WebGL/`xfade` as production); GLSL/WebGL/64-byte buffer/NativeProceduralEngine opt-in; keep HUD MUST NOT wgpu/Playwright |
| `openspec/specs/media-processing-performance-policy/spec.md` | Modify | Drop wgpu-py/resvg-py production MUST; MODIFIED Atomic Single-Pass: `-c:v copy` when `stream_copy_mode`; one encode pass only for HUD/scale/xfade/subtitles; raw RGBA stdin opt-in only |
| `openspec/specs/editorial-and-content-policy/spec.md` | Modify | Backgrounds MUST FFmpeg loops, not WebGL/Three.js/Canvas |
| `openspec/specs/media-pipeline-hardening/spec.md` | Modify | Rewrite Capability Overview; Req 2 rawvideo stdin opt-in not production MUST; Req 8 lavfi; Req 10 default `ProceduralVideoEngine()`; restated full reqs (not nested delta) |
| `openspec/specs/legacy-eradication-guardrails/spec.md` | Modify | Pillow thumbs allowed; wgpu-py/resvg-py not production |
| `openspec/config.yaml` | Modify | Context: FFmpeg + Pillow thumbs; drop wgpu-py/resvg-py as production |

Unchanged: `src/media/compositor.py`, `proc_engine.py`, `loop_engine.py`, `loop_worker.py`, `director_single_pass.py`, `native_procedural.py`, `_legacy/`, `pipeline.py`, `thumbnail_engine.py`, `tests/unit/test_retire_wgpu_hot_path.py`, `tests/unit/test_quarantine_native_procedural.py`. Do not delete `_legacy`. Do not edit archives.

## Interfaces / Contracts

No new APIs. Existing gate: `_native_procedural_hot_path_enabled()` in `src/media/compositor.py`. Default compositor: `procedural_engine.renderer is None`. Loop worker label: `technology="ffmpeg_lavfi"`. Public `src/media/native_procedural.py` remains DEPRECATED shim.

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | Default compositor does not load wgpu/`_legacy`; hot-path no top-level wgpu imports; lavfi label; concat `-c:v copy` | Keep `test_retire_wgpu_hot_path.py`, `test_quarantine_native_procedural.py` fail-closed; do not weaken |
| Apply gate | If those tests fail after spec/config edit | Then inspect runtime; do not preemptively rewrite renderers |
| Integration/E2E | Out of scope | No new suites; no HUD golden from `0a90158` |

## Threat Matrix

N/A — this change is spec/config ratification. It does not change routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundaries. Existing FFmpeg Popen/watchdog requirements stay as restated in the hardening delta.

## Migration / Rollout

No migration. Runtime is already FFmpeg-first. Rollback: revert the six apply files. Opt-in WebGPU remains `ENABLE_NATIVE_PROCEDURAL=1` only.

## Open Questions

None. Residual wgpu MUST in other main specs was searched and found only in the five listed files. Stale `ProceduralVideoEngine` docstring (WebGL/Canvas) is out of scope unless tests fail.
