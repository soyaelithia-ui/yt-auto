# Project: yt-auto Video Pipeline Optimization & Bottleneck Elimination

## Architecture
- **Objective**: Accelerate yt-auto Short video production to **4-6s** per Short under **<= 2 CPU Cores** and **<= 2.0 GiB RAM**.
- **Strategy**: Instant audio duration reader, 5-min TTL claim cache, narrative cadence pacing (2.25 words/s), single-pass audio ducking/loudnorm (`-14 LUFS`), mapped nullsink visual QA (`-map "[vb]" -map "[vl]"`), and bounded burst thumbnail extraction (`-threads 2`).

## Feature Inventory
| # | ID | Feature | Description | Milestone | Status |
|---|----|---------|-------------|-----------|--------|
| 1 | F01 | Instant Audio Duration Reader | Pure Python stdlib WAV (`wave.open`) and MP3 (`0xFFE`/`0xFFF` sync) parser | M1 | COMPLETED |
| 2 | F02 | Stage 1 Claim Lease Local Cache | 5-minute TTL SQLite cache (`external_post_cache`) eliminating WAN delay | M1 | COMPLETED |
| 3 | F03 | Prompt Pacing & Arc Cadence | 2.25 words/s cadence and complete arc mandate in `src/llm.py` | M2 | COMPLETED |
| 4 | F04 | TTS Speed Modulation (<8% overshoot) | Modulate Edge TTS rate (+6%) in `stage_05_tts.py` avoiding re-curation | M2 | COMPLETED |
| 5 | F05 | Folded Voice Mastering Bypass | `YT_FOLD_MASTERING=1` bypass in `lib/tts.py` skipping redundant mastering | M2 | COMPLETED |
| 6 | F06 | Sidechain Ducking & Composite Mastering | Aligned parameters (-14 LUFS, -1.5 dB TP) on master bus in `stream_copy.py` | M2 | COMPLETED |
| 7 | F07 | Single-Pass Mapped Visual QA | Single FFmpeg nullsink combining blackdetect and signalstats (`-map "[vb]" -map "[vl]"`) | M3 | COMPLETED |
| 8 | F08 | Bounded Burst Thumbnail Extractor | Single FFmpeg burst (`-vf fps=2.5 -vframes 5 -threads 2`) in `extractor.py` | M3 | COMPLETED |
| 9 | F09 | E2E Regression & Quality Test Suite | Unit test coverage for bypasses, header parsing, burst extraction, and QA | M4 | COMPLETED |
| 10 | F10 | Pipeline Production Benchmark & SLA Audit | 4-6s Short production under <= 2 Cores and <= 2.0 GiB RAM, verify integrity pass | M4 | COMPLETED |
| 11 | F11 | Unified Atomic FFmpeg Encoder | Single-pass FFmpeg stream-copy encoding with multiplexed audio/video | Pipeline | COMPLETED |
| 12 | F12 | SceneManifest Contract Synchronization | Strict Draft-07 schema compliance for v2 scene manifests | Schemas | COMPLETED |
| 13 | F13 | Scene Planner Agent Sync | Multi-agent scene planning, camera motion, and safe area layout bounds | Agents | COMPLETED |
| 14 | F14 | Live Director Shot Mix & Thematic Rotation | Seeded candidate pool rotation across scenes without repetitions | Visuals | COMPLETED |
| 15 | F15 | Precomputed QA Metrics Gate | `bank_manifest.json` visual metrics avoid double full-file decode in QA | Verification | COMPLETED |
| 16 | F16 | Multi-Channel Lane Parity | Six production lanes across Horror, Drama, and SciFi (Shorts + Longform) | Core | COMPLETED |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Low-Overhead Pipeline Foundations | R5 (Audio duration in `lib/tts.py`) & R6 (Claim Lease cache) | none | COMPLETED |
| 2 | Narrative Duration Calibration & Audio Folding | R1 (Cadence pacing & TTS modulation) & R2 (Folded mastering & ducking) | M1 | COMPLETED |
| 3 | Single-Pass Visual QA & Burst Thumbnails | R3 (Single-pass mapped QA) & R4 (Bounded burst thumbnail extraction) | M1 | COMPLETED |
| 4 | Final E2E Validation, Benchmark & Hardening | Phase 1 (100% tests pass) + Phase 2 (Benchmark timing & integrity gate) | M1-M3 | COMPLETED |

## Interface Contracts & Layout
- **`lib.tts:get_audio_duration`**: Fast stdlib WAV and binary MP3 reader (<1ms, microsecond precision).
- **`stage_01_lease:_get_cached_external_stories`**: SQLite `external_post_cache` unexpired candidate retrieval (300s TTL).
- **`lib.tts:master_voice_audio`**: Respects `YT_FOLD_MASTERING=1` to skip redundant voice mastering pass.
- **`src.core.quality:run_single_pass_visual_qa`**: Nullsink `blackdetect` + `signalstats` (`-threads 2`), stderr parsing.
- **`src.media.thumbnails.extractor:extract_candidate_frames`**: Bounded burst extraction (`-threads 2`, <= 2 CPU cores).
- **Code Layout**: `lib/tts.py`, `src/pipeline/stages/` (01 to 13), `src/media/loop/`, `src/core/quality.py`, `tests/unit/`.
