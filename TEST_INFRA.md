# E2E Test Infra: yt-auto Video Pipeline Optimization

## Test Philosophy
- Requirement-driven, opaque-box & unit validation.
- Enforce strict resource budgets: <= 2 CPU Cores, <= 2.0 GiB RAM.
- Zero-Browser policy: strictly zero Playwright/Chromium outside `src/youtube/session_uploader.py`.
- Methodology: Category-Partition, Boundary Value Analysis, Integration & Real-World Workload Testing.

## Feature Inventory & Test Coverage Map
| # | ID | Feature | Requirements Source | Tier 1 (Feature) | Tier 2 (Boundary) | Tier 3 (Cross-Feature) | Tier 4 (Real-World) |
|---|----|---------|---------------------|:----------------:|:-----------------:|:----------------------:|:-------------------:|
| 1 | F01 | Instant Audio Duration | R5 (`lib/tts.py`) | WAV & MP3 parsed in <1ms without ffprobe | Corrupt header, zero-byte file, VBR/CBR edge cases | Audio duration used in pause insertion & alignment | Full story audio duration calculation |
| 2 | F02 | Stage 1 Claim Lease Cache | R6 (`stage_01_lease.py`) | Feed cache hit & miss behavior | Expired TTL (300s), empty feed response, DB lock recovery | Cache interaction with `is_story_duplicate` and `claim` | Successive pipeline runs in daemon loop |
| 3 | F03 | Prompt Pacing & Arc Cadence | R1 (`src/llm.py`, `stage_03`) | 2.25 words/s instruction generation | Min/max words boundary, short vs long duration types | Script pacing + coherence gatekeeper | End-to-end script curation without cold cuts |
| 4 | F04 | TTS Speed Modulation | R1 (`stage_05_tts.py`) | Rate boost (+6% to +8%) for <8% overshoot | Exact 8% boundary, >8% fallback to re-curation | Rate modulation + alignment stage bypass | Complete Short speech generation under 60s |
| 5 | F05 | Folded Voice Mastering Bypass | R2 (`lib/tts.py`, `stage_05`) | `YT_FOLD_MASTERING=1` bypasses FFmpeg | `force=True` overrides bypass, `YT_FOLD_MASTERING=0` runs FFmpeg | Bypass in Stage 5 followed by Stream-Copy muxing | Full voice pipeline without standalone mastering |
| 6 | F06 | Sidechain Ducking & Loudnorm | R2 (`stream_copy.py`, `audio.py`) | Sidechain compression + loudnorm in filtergraph | Zero music volume, missing BGM track, custom LUFS | Voice + BGM ducking during narration | Final master bus loudness (-14 LUFS, -1.5 dB TP) |
| 7 | F07 | Single-Pass Mapped Visual QA | R3 (`src/core/quality.py`) | Single FFmpeg nullsink with `-map "[vb]" -map "[vl]"` | All-black video, high-brightness video, empty video | Visual QA facts + Precomputed QA manifest | Stage 10 prepublication validation in live run |
| 8 | F08 | Burst Thumbnail Extraction | R4 (`extractor.py`) | Single FFmpeg burst `-vf fps=2.5 -vframes 5` | Video shorter than window, start timestamp near 0 | Burst extraction + frame scoring | Stage 11 metadata and thumbnail selection |
| 9 | F09 | E2E Regression & Quality Test Suite | R3/R4 (`tests/`) | Unit test coverage for bypasses, header parsing | Adversarial corruptions & timeout handling | Cross-stage pipeline regression testing | Full suite execution via verify_integrity.sh |
| 10 | F10 | Pipeline Production Benchmark | Governance SLA | Production SLA of 4-6s Short generation | Memory peak <= 2.0 GiB, CPU <= 2 cores | Combined stages 1-12 latency validation | Headless daemon throughput verification |
| 11 | F11 | Unified Atomic FFmpeg Encoder | R2 (`src/media/`) | Filter complex graph construction & stderr drain | Broken pipe recovery & stream termination | Sidechain ducking & composite mastering muxing | End-to-end video muxing via stream-copy |
| 12 | F12 | SceneManifest Contract Sync | Architecture (`schemas/`) | Schema Draft-07 syntax & payload validation | Invalid tension levels, missing required fields | Manifest consumption across compositor engines | Multi-scene longform production run |
| 13 | F13 | Scene Planner Agent Sync | Architecture (`src/agents/`) | Plan generation & camera motion specification | Safe area margins & resolution compliance | Curation -> Art Direction -> Scene Planning | Autonomous story staging & plan rendering |
| 14 | F14 | Live Director Shot Mix | Architecture (`src/core/`) | Rotation of certified loop pool without repeats | Empty catalog or unindexed categories | Concurrency locks & candidate pool rotation | Multi-act Short & Longform rendering |
| 15 | F15 | Precomputed QA Metrics Gate | Architecture (`src/core/`) | Bypasses live decode when metrics in manifest | Missing manifest keys or corrupted metric types | QA Gatekeeper & prepublication validation | Live production QA execution |
| 16 | F16 | Multi-Channel Lane Parity | Architecture (`config/`) | 6 production lanes across Moku, Aelithia, SciFi | Channel isolation & config schema validation | Profile preparsing & lane dispatching | Autonomous multi-channel publication |

## Test Execution Commands
- **Full Unit & Decoupled Suite**:
  ```bash
  .venv/bin/pytest tests/unit/ -q
  ```
- **Targeted Feature Suites**:
  ```bash
  .venv/bin/pytest tests/unit/test_tts.py tests/unit/test_audio_processor.py -v
  .venv/bin/pytest tests/unit/test_quality_gate_resolution.py tests/unit/test_ffmpeg_low_cpu_defaults.py -v
  .venv/bin/pytest tests/unit/test_channel_profile_and_thumbnails.py -v
  .venv/bin/pytest tests/unit/test_loop_video_engine.py tests/unit/test_loop_video_engine_adversarial.py -v
  .venv/bin/pytest tests/unit/test_anti_regression_guardrails.py -v
  ```
- **Mandatory Repository Integrity Gate**:
  ```bash
  ./scripts/verify_integrity.sh
  ```

## Acceptance Criteria
- 100% test pass rate across all suites (0 failures, 0 errors).
- Integrity script `./scripts/verify_integrity.sh` returns exit code 0 (100% HEALTHY).
- Video production benchmark completes Short production in 4-6 seconds under <= 2 CPU cores and <= 2.0 GiB RAM.
