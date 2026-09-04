# Director single-pass assembly (CPU/RAM)

## Encode counts (video)

| Path | Scene encodes | Assembly | Master (no ASS / with ASS) | Total (N=5, no ASS) |
|------|---------------|----------|----------------------------|---------------------|
| Legacy multi-pass | N libx264 | concat `-c:v copy` (0) | 0 / 1 | **5** |
| `DIRECTOR_SINGLE_PASS=1` stream-copy (homogeneous loops, no HUD) | 0 | trim `-c:v copy` + concat copy (0) | 0 / 1 | **0** |
| Single-pass + scale (resize **or** non-homogeneous codec/pix_fmt/time_base) | 0 | 1 filter_complex concat | 0 / 1 | **1** |
| Single-pass + planner `niche_hud` | 0 | 1 filter_complex concat+HUD (veryfast/CRF21) | 0 / 1 | **1** |
| `DIRECTOR_XFADE=1` | 0 | 1 filter_complex xfade | 0 / 1 | **1** |

## Flags

- `DIRECTOR_SINGLE_PASS` — default **on**. Falls back to legacy multi-pass for hybrid scenes or missing loops (no arbitrary `glob('*.mp4')[0]` fallback).
- `DIRECTOR_XFADE` — default **off** in `MultiSceneCompositor` (timeline shortens; breaks naive narration sync).
- `MULTIACT_XFADE` — default **on** for `MultiActVideoRenderer` (docs/openspec claimed xfade). Set `0` for concat without duration shrink. Callers must pass `total_duration=calculate_xfade_duration([...])` so output `-t` keeps A/V aligned.

## Stream-copy safety

Concat demuxer `-c:v copy` requires all trimmed segments to share **WxH + codec + pix_fmt + time_base** (via ffprobe). Otherwise assembly uses one scale+concat encode.

Planner/lane `niche_hud` (SCP / Reddit-AITA / abyssal) is burned with **one** extra FFmpeg `drawtext`/`drawbox` stage on the concat graph (not N per-scene encodes; no Playwright / wgpu / Pillow frames). Homogeneous loops without HUD still stream-copy. `DIRECTOR_XFADE` stays default off.

## Follow-ups

1. Fuse master audio/ASS into the same filter_complex as loop assembly (true 1-pass end-to-end).
2. Hybrid stills: multi-input `zoompan` + xfade in one graph (larger change).
3. Planner-aware xfade duration accounting so `DIRECTOR_XFADE=1` can be default-safe.
