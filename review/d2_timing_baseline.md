# Lote D2 — Baseline timing + cuellos ≥25%

Sources: Live `/tmp/d2-baseline.json` + Nova mock profile (`moku-scp-shorts`).

## Live baseline
- wall-clock **~0.132 s** · peak RSS **~87.16 MB** · Δ8=0 / Δ9 gate OK
- Top stages (mock harness — real FFmpeg/TTS will grow):

| Phase | sec | % |
|-------|----:|--:|
| `9_video_rendering` | 0.0314 | **23.9%** (just under 25%) |
| `5_tts_synthesis` | 0.0212 | 16.1% |
| `2_ingest_translate` | 0.0124 | 9.4% |
| `11_thumbnail_metadata` | 0.0111 | 8.4% |

## Cuellos ≥25%
- **Ninguno estricto en mock Live** (tope `9_video_rendering` 23.9%).
- Hipótesis prod: `9_video_rendering` (+ TTS) cruzará ≥25% en render real → mantener lavfi/stream-copy (#57); no reintroducir numpy frame-pump.

## PRs Nova D2
- `feat/lote-d2-stories-perf` — Reddit hybrid scoring on ingest + hooks ≤3s + 3 títulos Moku/SCP (rama local, Scrub push).
- REDUCE aparte con Scrub (thumbs helper dedupe / lavfi palette share) — sin assets/loops/.
