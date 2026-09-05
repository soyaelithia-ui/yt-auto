# Tasks: VPS FFmpeg Hot-Path Smoke

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 180–280 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Parser + CLI + fixtures | PR 1 | `pytest tests/unit/test_ffmpeg_hot_path_smoke.py` | N/A — VPS capture is operator CLI, not default pytest | Delete the three new files |

## Phase 1: RED tests

- [x] 1.1 Add `tests/unit/test_ffmpeg_hot_path_smoke.py`: empty capture → fail, argv not recovered (spec Missing argv)
- [x] 1.2 Same file: fixtures named `README.sh` and `requirements.txt` are parsed as text; never exec/chmod/source (threat: documentation-like paths)
- [x] 1.3 Same file: beats log `Executing Stream-Copy ... -c:v copy` → pass; no director job still pass (spec Beats copy / Beats-only fleet)
- [x] 1.4 Same file: libx264 + veryfast + crf 21 → pass; slow/ultrafast or crf≠21 → fail; copy-only sets note `no re-encode observed`

## Phase 2: GREEN parser

- [x] 2.1 Create `src/media/ffmpeg_hot_path_smoke.py` with `HotPathVerdict` + `parse_ffmpeg_evidence` until 1.1–1.4 pass; do not spawn ffmpeg
- [x] 2.2 Open helper reads UTF-8 data only; missing path → `argv_recovered=false`, `passed=false`

## Phase 3: CLI

- [x] 3.1 Create `scripts/smoke_ffmpeg_hot_path.sh` wrapping the parser (`[log_path|-]`); exit 1 unless passed
- [x] 3.2 Confirm `src/media/compositor.py` (read-only), `src/media/proc_engine.py` (read-only), `src/pipeline.py` (read-only) unchanged

## Phase 4: Verify

- [x] 4.1 Run `pytest tests/unit/test_ffmpeg_hot_path_smoke.py`
