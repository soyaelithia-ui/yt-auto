# Tasks: Standardize ASS Safe Zones and Stream-Copy Preservation

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~250-320 lines |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single atomic PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Subtitle margins, sentinel & escaping | PR 1 | `pytest tests/unit/test_subtitles_ass.py` | `./scripts/verify_integrity.sh` | `src/media/subtitles_ass.py` |
| 2 | Video engines stream-copy gating | PR 1 | `pytest tests/unit/test_subtitle_safe_zone.py` | `./scripts/verify_integrity.sh` | `src/media/loop_engine.py`, `src/media/compositor.py`, `src/media/multi_act_renderer.py` |

## Phase 1: Core Subtitle Foundations & Sentinel

- [x] 1.1 Add RED tests in `tests/unit/test_subtitles_ass.py` for safe margins (9:16 portrait $MarginV \ge 480$, $MarginR \ge 130$, $MarginL \ge 64$; 16:9 landscape $MarginV \ge 130$, $MarginL/R \ge 40$) and 2.5D camera drift (+30px drift $\to MarginV \ge 510$).
- [x] 1.2 Add RED tests in `tests/unit/test_subtitles_ass.py` for adaptive font sizing (52px at 1920h portrait, 38px at 1080h landscape) and cue chunking ($\le 3$ words/cue).
- [x] 1.3 Add RED tests in `tests/unit/test_subtitles_ass.py` for `has_active_subtitles()` sentinel handling None, missing file, 0-byte file, header-only script, whitespace-only dialogue, and valid dialogue.
- [x] 1.4 Add RED threat-matrix tests in `tests/unit/test_subtitles_ass.py` for `escape_ffmpeg_filter_path()` with colons, single quotes, and Windows backslashes.
- [x] 1.5 Implement `calculate_safe_margins()`, `calculate_font_size()`, `has_active_subtitles()`, and `escape_ffmpeg_filter_path()` in `src/media/subtitles_ass.py`.
- [x] 1.6 Update `ASSSubtitleGenerator` in `src/media/subtitles_ass.py` to use dynamic margins, adaptive font sizing, and safe cue chunking until 1.1–1.4 pass.

## Phase 2: Video Engines Stream-Copy Gating & Escaping

- [x] 2.1 Add RED tests in `tests/unit/test_subtitle_safe_zone.py` verifying `LoopVideoEngine` retains `-c:v copy` when subtitles are absent/inactive and injects escaped filter when active.
- [x] 2.2 Add RED tests in `tests/unit/test_subtitle_safe_zone.py` verifying `MultiSceneCompositor` retains stream-copy (`video_copy=True`) when subtitles are inactive and injects escaped filter when active.
- [x] 2.3 Add RED tests in `tests/unit/test_subtitle_safe_zone.py` verifying `MultiActVideoRenderer` retains stream-copy when subtitles are inactive and injects escaped filter when active.
- [x] 2.4 Update `src/media/loop_engine.py` to gate subtitle burning on `has_active_subtitles()` and escape filter paths.
- [x] 2.5 Update `src/media/compositor.py` to gate `has_ass_burn` on `has_active_subtitles()`, sanitize filter paths, and preserve stream-copy.
- [x] 2.6 Update `src/media/multi_act_renderer.py` to gate subtitle filter on `has_active_subtitles()` and escape filter paths.

## Phase 3: Verification & Anti-Regression

- [x] 3.1 Run unit test suite: `pytest tests/unit/test_subtitles_ass.py tests/unit/test_subtitle_safe_zone.py tests/unit/test_subtitles.py`.
- [x] 3.2 Run repository integrity verification: `./scripts/verify_integrity.sh`.
