# Tasks: Audiovisual Pipeline Hardening, Channel Purge & Visual QA

## Review Workload Forecast
- 400-line budget risk: High (~650 lines added/modified across 8 modules, ~280 lines deleted).
- Chained PRs recommended: Yes (split into 2 sequential PRs to maintain review velocity).
- Chain strategy: PR 1 (Phases 1-2: Test infra, safe-zone, FFmpeg hardening) -> PR 2 (Phases 3-4: Purge CLI, visual QA, shim cleanup).
- Decision needed before apply: None (all interfaces strictly typed, non-breaking migrations).

## Suggested Work Units
| Unit | Phase | Description | Target Files | Est. Diff |
| :--- | :--- | :--- | :--- | :--- |
| U1 | 1 | Test helper migration & mock cleanup | `tests/helpers/audio.py`, `<MagicMock *>` | +30 / -26 files |
| U2 | 1 | Author RED test suites | `tests/unit/test_*.py` | +210 / -0 |
| U3 | 2 | Subtitle safe-zone & FFmpeg hardening | `src/compositing/subtitles.py`, `src/audio/*.py`, `src/media/*.py` | +120 / -90 |
| U4 | 3 | Purge CLI & Visual QA implementation | `src/cli/purge_channels.py`, `src/cli/visual_inspect.py` | +240 / -0 |
| U5 | 4 | Shim removal & full test verification | `src/*.py`, codebase imports | +10 / -40 |

## Phase 1: Test Infrastructure & Repository Cleanup
- [x] 1.1 Move synthetic audio helper `generate_synthetic_pcm_audio` from `src/audio/__init__.py` to `tests/helpers/audio.py`.
- [x] 1.2 Delete 26 residual `<MagicMock ...>` files from repository root.
- [x] 1.3 [TDD-RED] Create `tests/unit/test_subtitle_safe_zone.py` verifying $MarginV \ge 480\text{px}$ for 1080x1920 portrait and $\ge 130\text{px}$ for landscape.
- [x] 1.4 [TDD-RED] Create `tests/unit/test_purge_channels.py` covering default `--dry-run`, affirmative `"DELETE"` token, channel ownership check, and HTTP 429 quota handling.
- [x] 1.5 [TDD-RED] Create `tests/unit/test_visual_inspect.py` covering 5-point keyframe extraction (10%, 30%, 50%, 70%, 90%), `blackdetect`, and `freezedetect`.

## Phase 2: Subtitle Safe-Zone & FFmpeg Process Hardening
- [x] 2.1 [TDD-GREEN] Update `src/compositing/subtitles.py` to enforce $MarginV \ge 480\text{px}$ for portrait ($height > width$) and $MarginV \ge 130\text{px}$ for landscape. Verify `test_subtitle_safe_zone.py` passes.
- [x] 2.2 Refactor `src/audio/mixer.py` to replace `subprocess.run` with `lib.ffmpeg.run_ffmpeg` and raise `FFmpegExecutionError`.
- [x] 2.3 Refactor `src/audio/vocal_chain.py` to execute vocal filtergraphs via `lib.ffmpeg.run_ffmpeg`.
- [x] 2.4 Refactor `src/media/multi_act_renderer.py` to route multi-act compositing through `lib.ffmpeg.run_ffmpeg`.
- [x] 2.5 Refactor `src/media/realtime_video_engine.py` to standardize child process execution and error propagation using `lib.ffmpeg.run_ffmpeg`.

## Phase 3: Channel Purge & Visual QA CLI Tools
- [x] 3.1 [TDD-GREEN] Implement `src/cli/purge_channels.py` with `purge_channel_videos()`, `--dry-run`, `"DELETE"` prompt, channel ID validation, and $\ge 0.5\text{s}$ pacing. Verify `test_purge_channels.py` passes.
- [x] 3.2 [TDD-GREEN] Implement `src/cli/visual_inspect.py` with `inspect_video_media()`, 5-point keyframe extraction, `blackdetect`, `freezedetect`, and JSON telemetry. Verify `test_visual_inspect.py` passes.

## Phase 4: Obsolete Shim Removal & Full Verification
- [x] 4.1 Delete 5 obsolete root shims: `src/audio.py`, `src/video.py`, `src/tts.py`, `src/subtitles.py`, and `src/youtube_control.py`.
- [x] 4.2 Update imports across codebase and tests to target canonical modules in `lib/` and `src/compositing/`.
- [x] 4.3 Run full test suite (`pytest`) across all unit and integration layers to confirm 100% pass rate.
