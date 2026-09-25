# Project: yt-auto Video Pipeline Optimization & Bottleneck Elimination

## Architecture
- **Objective**: Accelerate yt-auto Short video production to **4-6 seconds** per Short while strictly respecting the governance resource ceiling of **<= 2 CPU Cores** (<= 200% across concurrent threads) and **<= 2.0 GiB RAM** (2,048 MiB peak memory).
- **Core Strategy**:
  1. **Foundational Latency Removal (Stage 1 & Audio Duration)**: Eliminate synchronous external WAN network delays during claim lease by adding a 5-minute TTL SQLite cache for Reddit post queries. Eliminate repeated `ffprobe` subprocess forks during pause insertion and audio probing by using stdlib `wave.open` for WAV and a pure Python binary header parser (MPEG frame sync `0xFFE`/`0xFFF`) for MP3.
  2. **Narrative Calibration & Audio Folding (Stages 3, 5, 9)**: Prevent blind cold slicing of story endings by embedding strict cadence pacing (2.25 words/s) and complete narrative arc resolution into the LLM prompt. Eliminate 12-second LLM re-curation loops by modulating Edge TTS speed (`rate="+6%"`) for minor overshoots (< 8%). Eliminate standalone voice mastering by bypassing `master_voice_audio` under `YT_FOLD_MASTERING=1`, relying on single-pass sidechain ducking and composite `-14 LUFS` / `-1.5 dB TP` master bus loudnorm in the stream-copy composition pass.
  3. **Visual Quality & Metadata Acceleration (Stages 10 & 11)**: Unify black frame detection and perceptual luminance analysis into a single FFmpeg nullsink pass with explicitly mapped outputs (`-map "[vb]" -map "[vl]"`), parsing metrics directly from stderr to eliminate disk writes and Pillow image processing. Replace 5 sequential FFmpeg subprocesses for thumbnail extraction with a single bounded burst invocation (`-vf fps=2.5 -vframes 5 -threads 2`).
  4. **Verification & Hardening**: Validate 100% passing tests, run end-to-end benchmark timing, verify zero-browser invariants, and run `./scripts/verify_integrity.sh`.

## Feature Inventory
| # | ID | Feature | Description | Milestone | Source |
|---|----|---------|-------------|-----------|--------|
| 1 | F01 | Instant Audio Duration Reader | Pure Python stdlib WAV (`wave.open`) and MP3 (`0xFFE`/`0xFFF` sync) parser in `lib/tts.py`, `ffprobe` fallback | M1 | Survey 1 |
| 2 | F02 | Stage 1 Claim Lease Local Cache | 5-minute TTL SQLite cache (`external_post_cache`) in `stage_01_lease.py`, eliminating ~1.8s WAN delay | M1 | Survey 1 |
| 3 | F03 | Prompt Pacing & Arc Cadence | Add 2.25 words/s cadence and complete arc mandate to `_word_budget_instruction` in `src/llm.py` | M2 | Survey 2 |
| 4 | F04 | TTS Speed Modulation (<8% overshoot) | Modulate Edge TTS `rate` (e.g. `+6%`) in `stage_05_tts.py` for overshoots <8%, avoiding 12s LLM re-curation | M2 | Survey 2 |
| 5 | F05 | Folded Voice Mastering Bypass | Implement `YT_FOLD_MASTERING=1` bypass in `lib/tts.py` and `stage_05_tts.py` to skip redundant voice mastering | M2 | Survey 2 |
| 6 | F06 | Sidechain Ducking & Composite Mastering | Aligned parameters (-14 LUFS, -1.5 dB TP) on final master bus in `stream_copy.py` & `audio.py` | M2 | Survey 2 |
| 7 | F07 | Single-Pass Mapped Visual QA | Single FFmpeg nullsink combining blackdetect and signalstats (`-map "[vb]" -map "[vl]"`), stderr parsing | M3 | Survey 3 |
| 8 | F08 | Bounded Burst Thumbnail Extractor | Single FFmpeg burst extraction (`-vf fps=2.5 -vframes 5 -threads 2`) in `src/media/thumbnails/extractor.py` | M3 | Survey 3 |
| 9 | F09 | E2E Regression & Quality Test Suite | Unit test coverage for bypasses, header parsing, burst extraction, and single-pass QA | M4 | Survey |
| 10 | F10 | Pipeline Production Benchmark & SLA Audit | Verify 4-6s Short production time under <= 2 Cores and <= 2.0 GiB RAM, full `./scripts/verify_integrity.sh` pass | M4 | Survey |
| 11 | F11 | Unified Atomic FFmpeg Encoder | Single-pass FFmpeg stream-copy encoding with multiplexed audio and video | Pipeline | Architecture |
| 12 | F12 | SceneManifest Contract Synchronization | Strict Draft-07 schema compliance for v2 scene manifests | Schemas | Architecture |
| 13 | F13 | Scene Planner Agent Sync | Multi-agent scene planning, camera motion, and safe area layout bounds | Agents | Architecture |
| 14 | F14 | Live Director Shot Mix & Thematic Rotation | Seeded candidate pool rotation across scenes without consecutive repetitions | Visuals | Architecture |
| 15 | F15 | Precomputed QA Metrics Gate | `bank_manifest.json` visual metrics avoid double full-file decode in prepublication QA | Verification | PR #69 |
| 16 | F16 | Multi-Channel Lane Parity | Six production lanes across Horror, Drama, and SciFi (Shorts + Longform) | Core | PR #69 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Low-Overhead Pipeline Foundations | R5 (Instant audio duration in `lib/tts.py`) & R6 (Claim Lease cache in `stage_01_lease.py`) | none | IN_PROGRESS |
| 2 | Narrative Duration Calibration & Audio Folding | R1 (Cadence pacing & TTS speed modulation) & R2 (Folded mastering bypass & sidechain ducking) | M1 | PENDING |
| 3 | Single-Pass Visual QA & Burst Thumbnails | R3 (Single-pass mapped QA gating) & R4 (Bounded burst thumbnail extraction) | M1 | PENDING |
| 4 | Final E2E Validation, Benchmark & Hardening | Phase 1 (100% unit/E2E tests pass) + Phase 2 (Benchmark timing, integrity gate & adversarial audit) | M1, M2, M3 | PENDING |

## Interface Contracts

### `lib.tts:get_audio_duration(path: str | os.PathLike) -> float`
- Fast stdlib WAV reader via `wave.open`.
- Fast binary MP3 reader via MPEG frame sync `0xFFE`/`0xFFF` and Xing/Info header or CBR bitrate.
- Returns duration in seconds with microsecond precision.
- Fallback to `ffprobe` exclusively on exception or non-standard container.
- Must execute in `< 1 ms` on local files.

### `src.pipeline.stages.stage_01_lease:_get_cached_external_stories(database: str, feed: str, limit: int, ttl_seconds: float = 300.0) -> list[dict] | None`
- Retrieves unexpired candidate story list from SQLite table `external_post_cache`.
- Returns `None` on cache miss or expired TTL.

### `lib.tts:master_voice_audio(audio_path: str | os.PathLike, target_lufs: float = -14.0, true_peak_dbtp: float = -1.5, force: bool = False, **kwargs) -> str`
- Checks `os.getenv("YT_FOLD_MASTERING", "1") == "1"`.
- If active (default) and `force=False`, immediately returns `audio_path` without spawning FFmpeg.

### `src.core.quality:run_single_pass_visual_qa(path: str | os.PathLike, *, threads: int = 2, sample_fps: float = 0.25) -> tuple[tuple[float, list[float]], dict[str, Any]]`
- Runs single FFmpeg nullsink with filtergraph: `"[0:v]blackdetect=d=0.5:pix_th=0.10[vb];[0:v]fps={sample_fps},signalstats,metadata=print:key=lavfi.signalstats.YAVG[vl]"`
- Maps both outputs explicitly: `-map "[vb]" -map "[vl]"` into `-f null -`.
- Parses `black_duration:` and `lavfi.signalstats.YAVG=` directly from `stderr`.
- Zero disk writes, zero Pillow calls.

### `src.media.thumbnails.extractor:extract_candidate_frames(video_path: Path, center_timestamp: float, output_dir: Path, window_sec: float = 2.0, count: int = 5) -> List[Path]`
- Executes single FFmpeg command with `-threads 2`, `-vf fps={count/window_sec:.2f}`, `-vframes {count}`.
- Bounded strictly to <= 2 CPU cores.

## Code Layout
- `lib/tts.py`: Audio duration reader & mastering functions.
- `src/pipeline/stages/stage_01_lease.py`: Claim lease stage & external story caching.
- `src/llm.py`: Prompt word budget & cadence instructions.
- `src/pipeline/stages/stage_03_editorial.py`: Editorial stage barrier.
- `src/pipeline/stages/stage_05_tts.py`: Speech synthesis & rate modulation.
- `src/media/loop/audio.py`: Audio filtergraph builder (sidechain ducking + master loudnorm).
- `src/media/loop/stream_copy.py`: Stream copy composition command builder.
- `src/core/quality.py`: Visual QA gating, black frame detection, and perceptual luminance.
- `src/media/thumbnails/extractor.py`: Candidate frame thumbnail extractor.
- `tests/unit/`: Test suites for all components.
- `scripts/verify_integrity.sh`: Project integrity gate script.
