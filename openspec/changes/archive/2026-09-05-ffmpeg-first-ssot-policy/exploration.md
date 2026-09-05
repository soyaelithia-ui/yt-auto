## Exploration: ffmpeg-first-ssot-policy

### Current State

Production code is already FFmpeg-first. Specs and `openspec/config.yaml` still describe the archived WebGPU/cinematic stack as production MUST.

**Runtime (verified, not edited):**

- `MultiSceneCompositor.__init__` (`src/media/compositor.py`) constructs `ProceduralVideoEngine()` with `renderer is None` unless `ENABLE_NATIVE_PROCEDURAL` is explicitly `1`/`true`/`yes`/`on`. Opt-in then lazy-imports `src.media._legacy.native_procedural.NativeProceduralEngine`.
- Default `DIRECTOR_SINGLE_PASS=1` (`src/media/director_single_pass.py`). Homogeneous procedural loops with no `niche_hud` assemble as `loop_stream_copy` (`-c:v copy`). HUD burns in **one** `filter_complex` (`drawtext`/`drawbox`, `encode_defaults` veryfast/CRF 21). `DIRECTOR_XFADE` defaults off.
- Beats/loop composition: `LoopVideoEngine.build_stream_copy_composition_cmd` is concat demuxer + `-c:v copy`. `src/pipeline.py` sets `stream_copy_mode = bool(lane.orientation == "horizontal" and not burn_subtitles)`.
- Loop synthesis: `LoopSynthesizerWorker` labels catalog rows `technology="ffmpeg_lavfi"` (lavfi `gradients=...`); default constructor takes `renderer=None`.
- Quarantine: implementation lives in `src/media/_legacy/`; public `src/media/native_procedural.py` is a DEPRECATED shim that `RuntimeError`s if production importers (`pipeline`, `compositor`, `loop_worker`, `hybrid_engine`, `proc_engine`, `multi_act_renderer`) import it without opt-in.
- Thumbnails: `src/media/thumbnail_engine.py` and `src/media/thumbnails/` use Pillow. Video subtitles default to libass; Pillow frame loops are `FORCE_PILLOW_*` opt-in only.
- Fail-closed tests: `tests/unit/test_retire_wgpu_hot_path.py`, `tests/unit/test_quarantine_native_procedural.py`. Default compositor must not load `wgpu` / `_legacy.native_procedural`; hot-path modules must not top-level-import them.

**Spec contradiction (the reason for this change):**

| Spec | Production MUST today | Code SSOT |
|------|----------------------|-----------|
| `procedural-scene-compositor` Req 7 | `MultiSceneCompositor` MUST `NativeProceduralEngine` (WebGPU/Lavapipe) | Default FFmpeg lavfi/catalog; wgpu opt-in |
| Same spec HUD requirement | HUD MUST NOT wgpu / Playwright / Pillow frame loops | Matches code |
| `media-processing-performance-policy` | Video MUST `wgpu-py` + `resvg-py` | FFmpeg + libass; no resvg-py on hot path |
| `editorial-and-content-policy` | Backgrounds MUST WebGL / Three.js / Canvas | FFmpeg procedural loops |
| `media-pipeline-hardening` Req 8/10 | WGSL archetypes; director lane MUST wire `NativeProceduralEngine` | Default `ProceduralVideoEngine()`; shaders under `_legacy` |
| `legacy-eradication-guardrails` | `config.yaml` SHALL NOT list Playwright **or Pillow** | Thumbs are Pillow; config still lists wgpu-py/resvg-py |
| `openspec/config.yaml` context | `WebGPU (wgpu-py), resvg-py` | Not production |

A content search of `openspec/specs/` found wgpu/WebGL/`NativeProceduralEngine`/`resvg` **only** in the five specs listed by the proposal. Residual MUST risk outside those five is low.

`media-pipeline-hardening/spec.md` is still titled "Delta Specification" in main specs (archive residue). Spec phase should rewrite it as a full main requirement set, not a nested delta.

### Affected Areas

- `openspec/specs/procedural-scene-compositor/spec.md` — Req 1–3, 5–7 still GLSL/WebGL/WGSL/`NativeProceduralEngine` MUST; HUD scenarios already FFmpeg-correct and MUST be preserved.
- `openspec/specs/media-processing-performance-policy/spec.md` — "Native Procedural and Vector Rendering" MUST wgpu-py/resvg-py.
- `openspec/specs/editorial-and-content-policy/spec.md` — anti-filler MUST WebGL/Three.js/Canvas.
- `openspec/specs/media-pipeline-hardening/spec.md` — Req 8 WGSL, Req 10 compositor→NativeProceduralEngine, WebGL glitch scenario; unit-test isolation still mentions Lavapipe.
- `openspec/specs/legacy-eradication-guardrails/spec.md` — forbids Pillow in `config.yaml` context (conflicts with thumbs SSOT).
- `openspec/config.yaml` — tech-stack context still names wgpu-py/resvg-py as production.
- `src/media/compositor.py`, `proc_engine.py`, `loop_engine.py`, `loop_worker.py`, `director_single_pass.py`, `native_procedural.py`, `_legacy/`, `pipeline.py` — **unchanged** (already fail-closed).
- `tests/unit/test_retire_wgpu_hot_path.py`, `tests/unit/test_quarantine_native_procedural.py` — keep as contract; do not weaken.
- Stale code comments (out of this change unless tests fail): `ProceduralVideoEngine` class docstring still says "WebGL, Three.js, and HTML5 Canvas".

### Approaches

1. **Spec-and-context ratification only** — Delta the five specs + `openspec/config.yaml` so production MUST matches code. Keep `_legacy` and fail-closed tests. No HUD feature work; do not bundle feat/t1 HUD commit `0a90158`.
   - Pros: Matches existing runtime; smallest review surface; rollback is revert of markdown/yaml; preserves quarantine.
   - Cons: Stale class docstrings remain until a later hygiene change; archived changes still narrate WebGPU (archives must not be rewritten).
   - Effort: Low

2. **Restore WebGPU as production SSOT** — Make code match current specs (construct `NativeProceduralEngine` by default, wgpu-py/resvg-py as MUST).
   - Pros: Specs stay historically consistent with cinematic/purge archives.
   - Cons: Contradicts fail-closed tests, `_legacy` quarantine, low-CPU stream-copy path, and HUD MUST NOT wgpu. High CPU (Lavapipe) and dep risk. Explicitly out of product intent.
   - Effort: High

3. **Dual language (FFmpeg default + keep WebGPU MUST in specs)** — Specs describe both without demoting wgpu.
   - Pros: Avoids deleting historical requirements.
   - Cons: Leaves the contradiction that already exists (HUD MUST NOT wgpu vs NativeProceduralEngine MUST). Downstream apply/verify cannot decide a single SSOT.
   - Effort: Low, but fails the change intent

### Recommendation

Approach 1. Code is already the SSOT; this change is ratification, not a renderer rewrite.

Spec-phase deltas should:

- Production video MUST: FFmpeg lavfi / catalog loops, beats concat demuxer `-c:v copy` when `stream_copy_mode`, `DIRECTOR_SINGLE_PASS` assembly, drawtext/drawbox HUD, libass, encode_defaults veryfast/CRF 21.
- `NativeProceduralEngine` / WebGPU / GLSL / WebGL / wgpu-py / resvg-py: opt-in only (`ENABLE_NATIVE_PROCEDURAL=1`), quarantined under `src/media/_legacy`. Do not delete `_legacy`.
- Preserve existing HUD Given/When/Then that already MUST NOT wgpu/Playwright/Chromium.
- Req 6 (64-byte uniform buffer) and WGSL archetype scenarios: relocate as **opt-in / quarantined** behavior, not production MUST.
- `legacy-eradication-guardrails`: allow Pillow in `config.yaml` for thumbs SSOT; still forbid Playwright as production media stack; forbid wgpu-py/resvg-py as production stack.
- `openspec/config.yaml` context: FFmpeg + Pillow thumbs; drop wgpu-py/resvg-py as production.

Apply remains spec/config only unless a listed fail-closed test starts failing.

### Risks

- Specs drop Pillow thumbs while code uses Pillow for thumbnails — mitigate by explicitly allowing Pillow in guardrails + config context.
- Residual wgpu MUST in unlisted main specs — search of `openspec/specs/` found hits only in the five listed files.
- Apply phase rewrites renderers "to match old specs" — proposal and this exploration constrain apply to spec/config unless tests fail.
- `media-pipeline-hardening` still formatted as a delta inside main specs — merging MODIFIED blocks without restating full requirements could leave WebGL/NativeProceduralEngine MUST fragments.
- Stale Python docstrings (`ProceduralVideoEngine` WebGL/Canvas) can re-confuse later agents if specs are fixed but comments are not (out of scope unless tests fail).

### Ready for Proposal

Yes. Proposal already exists at `openspec/changes/ffmpeg-first-ssot-policy/proposal.md` and matches this investigation (scope, five specs, config context, fail-closed tests, no `_legacy` delete, no HUD bundling). Orchestrator should run **sdd-spec** next. No missing code facts for spec drafting.
