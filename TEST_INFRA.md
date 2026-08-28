# E2E Test Infra: yt-auto Architecture Optimization

## Test Philosophy
- Opaque-box, requirement-driven, and regression-free.
- Systematic 4-tier + 1 adversarial tier approach (Feature Coverage, Boundary/Corner, Pairwise/Combinatorial, Real-World Workload, and Adversarial White-Box Coverage).
- Pass criteria: 100% test pass rate on all active test suites (`pytest`), zero SQLite lock errors under multi-lane concurrency, verifiable disk footprint reduction, zero audio/video quality regressions.

## Feature Inventory Mapping
| # | Feature | Source (Requirement) | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---------|----------------------|:------:|:------:|:------:|:------:|
| F-01 | Granular Phase Profiling Framework | R1 | 5 | 5 | ✓ | ✓ |
| F-02 | Pipeline Stage Instrumentation | R1 | 5 | 5 | ✓ | ✓ |
| F-03 | Profiling Benchmark CLI | R1 | 5 | 5 | ✓ | ✓ |
| F-04 | Deep Recursive Storage Sweep | R2 | 5 | 5 | ✓ | ✓ |
| F-05 | Intermediate Buffer & Audio Purge | R2 | 5 | 5 | ✓ | ✓ |
| F-06 | Bounded LRU & TTL Caches | R2 | 5 | 5 | ✓ | ✓ |
| F-07 | Safe Disk Reclaim & Master Preservation | R2 | 5 | 5 | ✓ | ✓ |
| F-08 | Automated Post-Render & Daemon Hooks | R2 | 5 | 5 | ✓ | ✓ |
| F-09 | Test Suite Artifact Auto-Teardown | R2 | 5 | 5 | ✓ | ✓ |
| F-10 | Single-Pass Realtime Video & Audio Muxing | R3 | 5 | 5 | ✓ | ✓ |
| F-11 | Streamlined Subtitle Encoding Pipeline | R3 | 5 | 5 | ✓ | ✓ |
| F-12 | Balanced FFmpeg Thread Allocation & Presets | R3 | 5 | 5 | ✓ | ✓ |
| F-13 | Single-Pass Audio Mastering Folding | R3 | 5 | 5 | ✓ | ✓ |
| F-14 | RAM & Frame Buffer Optimization | R4 | 5 | 5 | ✓ | ✓ |
| F-15 | SQLite WAL Concurrency & Lock-Free Leases | R4 | 5 | 5 | ✓ | ✓ |
| F-16 | End-to-End Regression & Adversarial Hardening | R1-R4 | 5 | 5 | ✓ | ✓ |
| F-17 | Multi-Scene Orchestration & Composition | Architecture Doc 02 | 5 | 5 | ✓ | ✓ |
| F-18 | Dual Rendering Engines (Procedural & Hybrid) | Architecture Doc 01 | 5 | 5 | ✓ | ✓ |
| F-19 | Script Curation & Editorial Guardrails | Architecture Doc 03 | 5 | 5 | ✓ | ✓ |
| F-20 | Zero-Quota Testing Framework | Architecture Doc 05 | 5 | 5 | ✓ | ✓ |
| F-21 | EBU R128 Loudness Compliance | Architecture Doc 04 | 5 | 5 | ✓ | ✓ |
| F-22 | Rec.709 Color Grade & Theme Matrices | Architecture Doc 01 | 5 | 5 | ✓ | ✓ |
| F-23 | SimHash Visual & Textual Deduplication | Architecture Doc 03 | 5 | 5 | ✓ | ✓ |
| F-24 | Automated Drive Backup & Metadata Registry | Architecture Doc 02 | 5 | 5 | ✓ | ✓ |

## Test Architecture
- Test Runner: `pytest` with `pytest-asyncio` and `pytest-xdist`.
- Primary test execution commands:
  - Core requirements suite: `pytest -v tests/e2e/test_r1_r4_e2e.py`
  - Architectural documentation & schema suite: `pytest -v tests/unit/test_architectural_specs.py`
  - Cleaner & retention unit tests: `pytest -v tests/unit/test_cleaner.py tests/unit/test_retention.py`
  - Media & FFmpeg unit tests: `pytest -v tests/unit/test_loop_video_engine.py tests/unit/test_realtime_engine.py tests/unit/test_code_subtitles.py`
  - Full suite: `pytest -q`
- Directory layout:
  - `tests/unit/`: Component-level unit tests
  - `tests/integration/`: Cross-module integration tests
  - `tests/e2e/`: End-to-end pipeline and multi-lane concurrency tests

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Full Procedural Realtime Video Render with Audio & Subtitles | F-01, F-02, F-10, F-12, F-13, F-14 | High |
| 2 | Multi-Lane Parallel Daemon Processing with Concurrency Locks | F-01, F-08, F-15 | High |
| 3 | Heavy Storage Accumulation & Automated Deep Clean Cycle | F-04, F-05, F-06, F-07, F-08 | Medium |
| 4 | Longform Multi-Scene Composition with Loudnorm Mastering | F-01, F-02, F-11, F-12, F-13 | High |
| 5 | End-to-End Ingest-to-Publish Pipeline with Telemetry Capture | F-01, F-02, F-03, F-07, F-08, F-15, F-16 | High |

## Coverage Thresholds
- Tier 1: ≥5 per feature
- Tier 2: ≥5 per feature (boundary and corner cases)
- Tier 3: Pairwise combinations across storage, media, profiling, and database modules
- Tier 4: ≥5 realistic end-to-end workload scenarios
- Tier 5: Adversarial white-box gap testing and memory limit validation
