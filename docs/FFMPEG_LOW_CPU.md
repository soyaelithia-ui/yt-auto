# FFmpeg low-CPU defaults

Goal: near-zero resource on the default hot path (beats already stream-copy).

## Knobs (SSOT)

| Env | Default (compose) | Role |
|-----|-------------------|------|
| `RENDER_PRESET` | `veryfast` | x264 preset when a re-encode is unavoidable |
| `RENDER_CRF` | `21` | Quality target (≤22 with veryfast is YT-safe) |
| `FFMPEG_THREADS` | `4` | Cap encoder threads inside the cgroup |

Helpers: `src/media/encode_defaults.py` (`default_render_preset`, `default_render_crf`, `default_ffmpeg_threads`, `loop_matches_target_geometry`).

## Rules

1. **Horizontal beats / loop** (`LoopVideoEngine`): prefer `-c:v copy` when orientation is horizontal and subtitles are not burned. Pipeline already sets `stream_copy=True` in that case.
2. **Re-encode paths** (vertical + libass, hybrid zoompan, multi-scene master): use `veryfast` + CRF 21 — **not** `slow` (CPU disaster) and **not** blind `ultrafast` on final delivers.
3. **Pillow / rawvideo**: opt-in only via `FORCE_PILLOW_SUBTITLES` / `FORCE_PILLOW_HYBRID_FRAMES`. Default hybrid/procedural paths must not open a Python frame pipe.
4. **Procedural segments** without subtitles: stream-copy trim (`-stream_loop` + `-c:v copy`) when `loop_matches_target_geometry` says WxH already match — same predicate as director single-pass (PR #11). Mismatched geometry re-encodes with scale+crop+fps + `veryfast`/`RENDER_CRF`.

## Guardrails

See `tests/unit/test_ffmpeg_low_cpu_defaults.py`.

## Coordination with director single-pass (PR #11)

`proc_engine` stream-copy / geometry logic is intentionally aligned with
`MultiSceneCompositor._loop_matches_target` / single-pass assembly on
`perf/director-single-pass-ffmpeg`. Prefer landing **this PR (encode_defaults)
before #11**, then rebase #11 onto it and switch the compositor helper to call
`loop_matches_target_geometry` so the two PRs do not fight over `proc_engine.py`.
