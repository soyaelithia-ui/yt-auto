# Project: yt-auto

## Architecture
`yt-auto` is an automated video generation pipeline consisting of:
- **Agents (`src/agents/`)**: LLM-driven cinematic script curation (`CinematicScriptCuratorAgent`), visual director, metadata generator, title generator.
- **Core Domain & Config (`src/core/`, `config/`)**: Lane definitions (`config/lanes.json`), voice profiles (`config/voice_profiles.json`), editorial/anti-plagiarism rules (`config/editorial_rules.json`).
- **Media & DSP Pipelines (`lib/`, `src/media/`, `src/audio_processor.py`)**: TTS generation (`lib/tts.py`), procedural ambient audio (`src/media/procedural_audio.py`), EBU R128 loudness normalization (-14 LUFS), sidechain ducking, video rendering.
- **Sanitizers & Editorial Guardrails (`src/sanitizer.py`)**: Leak detection, taboo phrase filtering, prompt directives, SimHash deduplication.
- **CLI & Orchestration (`main.py`, `src/cli/`, `src/pipeline.py`)**: Multi-lane pipeline runner, synthetic dry-run testing (`-t/--test`), channel resolution.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F-01 | Granular Phase Profiling Framework | Granular phase timing & memory instrumentation across all execution stages | M1 | R1 |
| F-02 | Pipeline Stage Instrumentation | Structured telemetry and timing metrics collection per pipeline step | M1 | R1 |
| F-03 | Profiling Benchmark CLI | Benchmark CLI commands for pipeline profiling and latency analysis | M1 | R1 |
| F-04 | Deep Recursive Storage Sweep | Automated deep disk cleanup for stale caches and temporary files | M2 | R2 |
| F-05 | Intermediate Buffer & Audio Purge | Selective purge of intermediary audio artifacts and scratch media | M2 | R2 |
| F-06 | Bounded LRU & TTL Caches | Memory-bounded LRU caches with time-to-live eviction policies | M2 | R2 |
| F-07 | Safe Disk Reclaim & Master Preservation | Preserves published masters while reclaiming scratch disk capacity | M2 | R2 |
| F-08 | Automated Post-Render & Daemon Hooks | Post-render automatic garbage collection and maintenance hooks | M2 | R2 |
| F-09 | Test Suite Artifact Auto-Teardown | Auto-teardown fixtures ensuring zero disk footprint after test runs | M2 | R2 |
| F-10 | Single-Pass Realtime Video & Audio Muxing | High-throughput direct stream muxing via FFmpeg image2pipe | M3 | R3 |
| F-11 | Streamlined Subtitle Encoding Pipeline | Fast subtitle frame drawing with safe-area bounding and dynamic font sizing | M3 | R3 |
| F-12 | Balanced FFmpeg Thread Allocation & Presets | CPU-adaptive thread balancing and ultrafast/faster H.264 presets | M3 | R3 |
| F-13 | Single-Pass Audio Mastering Folding | Single-pass integrated EBU R128 loudness normalization and sidechain ducking | M3 | R3 |
| F-14 | RAM & Frame Buffer Optimization | Bounded frame streaming avoiding full-video in-memory buffering | M4 | R4 |
| F-15 | SQLite WAL Concurrency & Lock-Free Leases | Concurrency-safe SQLite WAL mode with busy timeouts and lease locks | M4 | R4 |
| F-16 | End-to-End Regression & Adversarial Hardening | End-to-end multi-tier test harness with zero-quota mocking | M4 | R1-R4 |
| F-17 | Multi-Scene Orchestration & Composition | Dynamic multi-scene composition with xfade transitions and Ken Burns motion | M5 | Architecture Doc 02 |
| F-18 | Dual Rendering Engines (Procedural & Hybrid) | Hybrid AI 2.5D parallax and pure procedural WebGL/Canvas2D engines | M5 | Architecture Doc 01 |
| F-19 | Script Curation & Editorial Guardrails | 4-Act script curation with tension grading (1-5) and editorial filters | M5 | Architecture Doc 03 |
| F-20 | Zero-Quota Testing Framework | Complete offline synthetic mock harness executing without external API quota | M5 | Architecture Doc 05 |
| F-21 | EBU R128 Loudness Compliance | Broadcast standard -14 LUFS loudness and -1.5 dBTP true peak mastering | M5 | Architecture Doc 04 |
| F-22 | Rec.709 Color Grade & Theme Matrices | Strict Rec.709 color profiles and cinematic LUT matrices per channel lane | M5 | Architecture Doc 01 |
| F-23 | SimHash Visual & Textual Deduplication | 64-bit SimHash Hamming distance deduplication preventing topic overlap | M5 | Architecture Doc 03 |
| F-24 | Automated Drive Backup & Metadata Registry | Automated cloud backup and SQLite artifact lineage registration | M5 | Architecture Doc 02 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Scripting & Curation Formulas (R1) | `src/agents/script_curator.py`, prompt templates, schema validator | none | DONE |
| M2 | TTS Voice Profiles & Audio Calibration (R2) | `config/voice_profiles.json`, `config/lanes.json`, `lib/tts.py`, `src/pipeline.py` | none | IN_PROGRESS |
| M3 | Originality & Editorial Rules (R3) | `config/editorial_rules.json`, `src/sanitizer.py`, prompt safeguards | none | PLANNED |
| M4 | E2E Integration & Synthetic Verification | `src/pipeline.py`, `main.py`, `src/cli/`, unit tests, synthetic runs | M1, M2, M3 | PLANNED |

## Interface Contracts
### `src/agents/script_curator.py` ↔ `schemas/script_curator.schema.json`
- Output dictionary must match schema: `version="2.0"`, `metadata` with `duration_target_seconds`, `tension_curve` (list of ints [1-5]), `hook_summary`.
- `acts`: list of 1 to 4 acts, each with `act_number`, `act_title`, `dramatic_role` in `["hook", "escalation", "climax", "aftermath"]`, and `scenes`.
- `scenes`: each scene with `scene_id` (e.g. `scene_001`), `visual_description`, `narration_text`, `duration_seconds`, optional `audio_pacing_cue` in `["whispered_grave", "ominous_slow", "rapid_breathless", "clinical_sterile", "conversational_warm", "tense_pause"]`.

### `config/voice_profiles.json` & `config/lanes.json` ↔ `lib/tts.py`
- Voice profile object: `{"voice": str, "pitch": str (e.g. "-2Hz"), "rate": str (e.g. "+0%", "+6%"), "ducking_level": float, "normalization_lufs": float}`.
- `lib/tts.py`: `generate_audio(text, output_path, voice=None, rate=None, pitch=None, lane=None)` accepts and applies pitch and rate to `edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)`.

### `config/editorial_rules.json` ↔ `src/sanitizer.py`
- Editorial rules define `taboo_words`, `forbidden_phrases`, `immersion_breaking_patterns`, `rephrasing_directives`.
- Sanitizer sanitizes narration text before TTS synthesis and script curation.

## Code Layout
- `src/agents/`: Agent implementations (`script_curator.py`, `visual_director.py`, etc.)
- `src/core/`: Domain models and lane configs (`lanes.py`, `domain.py`)
- `src/cli/`: CLI handlers and argument parsers
- `config/`: JSON configuration files (`voice_profiles.json`, `lanes.json`, `editorial_rules.json`)
- `lib/`: Core libraries (`tts.py`, `audio.py`, `video.py`)
- `schemas/`: JSON schemas (`script_curator.schema.json`, etc.)
- `tests/`: Unit and integration test suites
