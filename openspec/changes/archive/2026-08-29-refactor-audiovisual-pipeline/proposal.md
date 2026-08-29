# Proposal: Audiovisual Pipeline Hardening, Channel Purge & Visual QA

## Problem Statement
The current automated video generation pipeline (`yt-auto`) contains code smells, raw unhandled `subprocess` executions, missing try/except blocks in procedural engines, subtitle safe-zone boundary violations on YouTube Shorts ($MarginV=422\text{px}$ vs $450\text{px}$ mobile UI danger zone), and 111 legacy/duplicate/test videos across Moku and Aelithia channels requiring deterministic cleanup.

## Capabilities

### New Capabilities
- `channel-purge-control`: Interactive and programmatic CLI for listing, dry-run auditing, and controlled batch deletion of YouTube channel video catalogs with API quota safeguards.
- `visual-qa-inspection`: Post-render quality assurance harness performing keyframe extraction (5 canonical points) and automated FFmpeg `blackdetect`/`freezedetect` artifact validation.

### Modified Capabilities
- `media-pipeline-hardening`: Standardized process lifecycle management replacing raw `subprocess.run`/`Popen` with `lib.ffmpeg.run_ffmpeg`, rawvideo pipe streaming, typed exception handling, and deprecation of unmaintained experimental engines.
- `subtitles-safe-zone`: ASS subtitle formatting and positioning ensuring $MarginV \ge 480\text{px}$ for 1080x1920 portrait aspect ratio, preventing collision with YouTube Shorts bottom UI.

## Scope
- Purge residual `<MagicMock>` test files from repository root.
- Eliminate empty 3-line re-export shims (`src/video.py`, `src/tts.py`, `src/subtitles.py`, `src/youtube_control.py`).
- Move `generate_synthetic_pcm_audio` from `src/audio.py` into `tests/helpers/audio.py`.
- Enforce `run_ffmpeg` across `src/audio/mixer.py`, `src/audio/vocal_chain.py`, `src/media/multi_act_renderer.py`, and `src/media/realtime_video_engine.py`.
- Adjust subtitle margin in `src/compositing/subtitles.py`.
- Implement `src/cli/purge_channels.py` with default `--dry-run` and interactive confirmation.
- Implement `src/cli/visual_inspect.py` and unit test `tests/unit/test_subtitle_safe_zone.py`.

## Non-Scope
- Creating redundant parallel modules (`tts_provider.py`, `audio_engine.py`, `timeline.py`, `ass_generator.py`).
- Web scraping fallback for YouTube Studio deletion (API only).
- Premature SSIM golden master testing without established baselines.

## Rollback Plan
All modifications are backwards-compatible and tested via pytest. If any refactored module exhibits unexpected regressions, changes can be rolled back via git without persistent data corruption since DB migrations are not required.

## Performance Impact
Replacing PNG screenshot piping (`image2pipe` + `png`) with uncompressed `rawvideo rgb24` in Playwright capture pipelines eliminates frame-by-frame compression overhead, reducing render latency by up to 40%.
