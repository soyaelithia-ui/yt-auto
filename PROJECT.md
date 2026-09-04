# Project: yt-auto Codebase Reconciliation, Browser Eradication, Doc Purge & Test Certification

## Architecture
The yt-auto media pipeline is built on a zero-browser, deterministic **FFmpeg-first** architecture (SSOT Teología PDF v2.4.0):
1. **Production visual path (FFmpeg)**:
   - **Beats / loop**: `LoopVideoEngine` concat demuxer + `-c:v copy` (near-zero reencode) on the default horizontal path.
   - **Director / multi-scene**: `MultiSceneCompositor` + `HybridVideoEngine` Ken Burns via FFmpeg `zoompan`. Default `DIRECTOR_SINGLE_PASS=1` assembles all-procedural manifests from catalog loops with stream-copy trim + concat demuxer (eliminates per-scene libx264). Real `xfade` is opt-in (`DIRECTOR_XFADE=1`) because it shortens the timeline; `MultiActVideoRenderer` uses `xfade` in one `filter_complex`. `ENABLE_NATIVE_PROCEDURAL` defaults to **off** (quarantined under `src/media/_legacy`).
2. **Loop catalog (`src/media/loop_worker.py`, `src/media/loop_engine.py`)**:
   - Background synthetic video loop creation via native FFmpeg `lavfi` (`technology=ffmpeg_lavfi`).
   - Stream looping (`-stream_loop -1`), EBU R128 sidechain ducking filtergraphs, and ASS subtitle burning.
   - Strictly zero Playwright, Chromium, or headless browser subprocesses in media rendering.
3. **Quarantined**: `src/media/_legacy/native_procedural.py` + shaders (WebGPU/`wgpu-py` WGSL). Not SSOT. Production = FFmpeg + Pillow thumbs. Constructed only if `ENABLE_NATIVE_PROCEDURAL=1`.
4. **Storage & Concurrency Architecture**:
   - SQLite with Write-Ahead Logging (`WAL`), `PRAGMA busy_timeout=15000`, `synchronous=NORMAL`.
   - Discrete per-PID test review databases avoiding lock collisions under concurrency.
   - Strict offline socket network isolation in test environments.

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F01 | Stage & Preserve Local Shaders & Profiles | Commit uncommitted WGSL shader updates, hex accent parsing, Kelvin mapping, and Aelithia profiles. | M1 | Survey 1 / R1 |
| F02 | Git Reconcile with origin/main (acc279f) | Fast-forward/merge local main with origin/main (acc279f) cleanly without merge conflicts. | M1 | Survey 1 / R1 |
| F03 | Purge Obsolete Architecture Blueprints | Delete permanently docs/architecture/01_*.md to 05_*.md resuscitated in acc279f. | M1 | Survey 1 / R1 |
| F04 | Discard & Prune Outdated Worktree | Remove implement_grill_test_suite worktree and prune git worktrees. | M1 | Survey 1 / R1 |
| F05 | Media Browser Eradication & Code Alignment | Guarantee 0 playwright/chromium imports in src/media/ and src/cli/handlers/loop.py, and clean cosmetic docstrings. | M2 | Survey 2 / R2 |
| F06 | Performance Policy Spec Ratification | Ratify explicit ban on headless browsers in openspec/specs/media-processing-performance-policy/spec.md with Gherkin scenarios. | M2 | Survey 2 / R2 |
| F07 | CLI Loop Generation Latency SLA (<2.0s) | Optimize FFmpeg encoding preset to ultrafast in loop_worker.py and defer eager imports in main.py. | M2 | Survey 3 / R2 |
| F08 | Verification Targets Certification | Certify 100% green pass on the 4 targeted test suites (test_native_procedural_uniforms, test_cinematic_storyboard, test_multiscene_dispatch, test_loop_video_engine). | M3 | Survey 3 / R3 |
| F09 | Full Suite Zero-Regression & DB Concurrency Certification | Run full pytest suite, verifying 0 failures, 0 database locks (WAL/busy_timeout), 0 browser leaks, and 0 network quota consumption. | M3 | Survey 3 / R3 |
| F10 | Monotonic Timestamp Sanitizer | Timestamp sanitization enforcing monotonicity, non-negative durations, and millisecond ASS formatting. | M3 | Tier 1 |
| F11 | Unified Atomic FFmpeg Encoder | Unified single-pass filtergraph, libass subtitles, EBU R128 ducking, and async stderr drain. | M3 | Tier 1 |
| F12 | SceneManifest Contract Synchronization | Synchronization of SceneManifest and JSON Schema contracts with VisualArchetypeId. | M4 | Tier 1 |
| F13 | Scene Planner Agent Sync | Scene planner agent resolving archetype tokens and generating valid vertical SceneManifest instances. | M4 | Tier 1 |
| F14 | Deterministic Video QA Gate | Forensic audiovisual QA auditor verifying faststart, yuv420p, loudness, and frame integrity. | M4 | Tier 1 |
| F15 | Documentation Synchronization | Architecture and operations documentation synchronization with zero legacy blueprints. | M4 | Tier 1 |
| F16 | E2E Testing Suite (Tiers 1–4) | Complete test runner CLI, multi-tier test suites (Tiers 1–4), and boundary/workload coverage. | E2E | Tier 1 |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Git SSOT Sync, Doc Purge & Worktree Cleanup | Stage untracked tests & local WGSL/Aelithia changes, sync main with origin/main (acc279f), purge docs/architecture/0*.md, prune worktree. (F01, F02, F03, F04) | none | DONE |
| M2 | Media Browser Eradication & Policy Ratification | Verify zero Playwright in src/media/, clean cosmetic docstrings, optimize loop generation to <2.0s, ratify openspec policy. (F05, F06, F07) | M1 | IN_PROGRESS |
| M3 | Test Suite Certification & Zero Regressions | Execute target suites (32 tests) and full pytest suite (1850+ tests), benchmark loop generation, verify zero DB locks, zero browser processes. (F08, F09) | M2 | PLANNED |

---

## Interface Contracts

### 1. Git Repository SSOT State
- Target Remote: `origin/main` commit `acc279f`.
- Working Tree: clean working tree (`git status` clean) with all WGSL shaders, Aelithia profiles, and test files tracked.
- Architecture Docs: `docs/architecture/0*.md` must not exist.
- Worktrees: `implement_grill_test_suite` removed from `git worktree list`.

### 2. Media Rendering Pipeline ↔ Zero-Browser Policy
- Module Boundary: `src/media/` and `src/cli/handlers/loop.py`.
- Invariant: 0 imports of `playwright` or launches of `chromium`.
- SLA: `main.py loop generate -c drama_aita -o horizontal --duration 3.0` executes in $\le 2.0\text{s}$ wall-clock time using native FFmpeg lavfi.
- Policy: `openspec/specs/media-processing-performance-policy/spec.md` mandates zero browser runtimes with explicit Gherkin scenarios.

### 3. Test Suite & Concurrency Invariants
- Pytest invocation: `.venv/bin/pytest tests/unit/test_native_procedural_uniforms.py tests/unit/test_cinematic_storyboard.py tests/integration/test_multiscene_dispatch.py tests/unit/test_loop_video_engine.py` -> 100% pass (32/32 green).
- Full suite: 0 failures, 0 database locked exceptions, 0 external network requests.

---

## Code Layout
```text
src/
├── cli/
│   ├── handlers/
│   │   └── loop.py                   # Loop CLI handler (FFmpeg lavfi, 0 browser)
│   └── parser.py                     # CLI argument parser
├── media/
│   ├── loop_engine.py                # LoopVideoEngine (FFmpeg audio & video looping)
│   ├── loop_worker.py                # LoopSynthesizerWorker (fast FFmpeg lavfi generator)
│   ├── _legacy/native_procedural.py  # QUARANTINED: wgpu/WGSL (ENABLE_NATIVE_PROCEDURAL=1 only)
│   ├── native_procedural.py          # DEPRECATED shim -> _legacy (fail-closed without opt-in)
│   └── shaders/
│       └── maritime_lighthouse.wgsl  # WGSL shader with photometric luminance floor
docs/
└── architecture/                     # Obsolete 01-05 blueprints purged
openspec/
└── specs/
    └── media-processing-performance-policy/
        └── spec.md                   # Ratified zero-browser performance policy
tests/
├── unit/
│   ├── test_native_procedural_uniforms.py
│   ├── test_cinematic_storyboard.py
│   └── test_loop_video_engine.py
└── integration/
    └── test_multiscene_dispatch.py
```
