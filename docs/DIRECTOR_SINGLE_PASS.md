# Director single-pass assembly (CPU/RAM)

## Encode counts (video)

| Path | Scene encodes | Assembly | Master (no ASS / with ASS) | Total (N=5, no ASS) |
|------|---------------|----------|----------------------------|---------------------|
| Legacy multi-pass | N libx264 | concat `-c:v copy` (0) | 0 / 1 | **5** |
| `DIRECTOR_SINGLE_PASS=1` stream-copy (default when loops match WxH) | 0 | trim `-c:v copy` + concat copy (0) | 0 / 1 | **0** |
| Single-pass + scale (loops need resize) | 0 | 1 filter_complex concat | 0 / 1 | **1** |
| `DIRECTOR_XFADE=1` | 0 | 1 filter_complex xfade | 0 / 1 | **1** |

## Flags

- `DIRECTOR_SINGLE_PASS` — default **on**. Falls back to legacy multi-pass for hybrid scenes or missing loops.
- `DIRECTOR_XFADE` — default **off** in `MultiSceneCompositor` (timeline shortens; breaks naive narration sync). `MultiActVideoRenderer` uses real `xfade` (docs/openspec aligned).

## Follow-ups

1. Fuse master audio/ASS into the same filter_complex as loop assembly (true 1-pass end-to-end).
2. Hybrid stills: multi-input `zoompan` + xfade in one graph (larger change).
3. Planner-aware xfade duration accounting so `DIRECTOR_XFADE=1` can be default-safe.
