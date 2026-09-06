# Lote D2 — Baseline timing (mock) + cuellos ≥25%

Date: 2026-09-05 (America/El_Salvador). Harness: `main.py profile -c moku --lane moku-scp-shorts --mock --iterations 1`.

| Phase | wall-clock (s) | % of total |
|-------|----------------|------------:|
| **9_video_rendering** | **0.0316** | **25.4%** ≥25% |
| 5_tts_synthesis | 0.0208 | 16.7% |
| 2_ingest_translate | 0.0117 | 9.4% |
| 11_thumbnail_metadata | 0.0101 | 8.1% |
| (rest) | <0.007 each | <6% each |

**Total mock wall-clock:** 0.1243 s (RSS ~89 MB).

Notes for Quill:
- Mock path understates real FFmpeg/TTS; expect `9_video_rendering` (and possibly TTS) to dominate a live `-t` / full render.
- Live D1 smoke already showed stages 8–9 ~84–88 MB with lavfi; this baseline is *time* share, not RSS.
- Next: re-run with `--mock false` / synthetic `-t` when secrets allow and compare %.

Bottleneck action (≥25%): keep stream-copy / lavfi hot path; avoid numpy reintroductions (covered by #57).
