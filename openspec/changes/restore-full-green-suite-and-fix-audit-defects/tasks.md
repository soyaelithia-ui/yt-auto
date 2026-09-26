# Tasks: Restore Full Green Suite and Fix Audit Defects

## Phase 1: Code Defect Fixes
- [x] 1.1 Fix Concurrency Guard in `deploy/ctl.sh` (#10)
- [x] 1.2 Fix Screenshot Path Guard in `src/youtube/uploader/session.py` (#8)
- [x] 1.3 Export and Test Ownership Verification in `src/youtube/control.py` (#7)
- [x] 1.4 Fix Channel Alias & Persona Resolution in `src/llm.py` (#9)

## Phase 2: Test Suite & Guardrail Alignment
- [x] 2.1 Update `docs/FFMPEG_LOW_CPU.md` with resource budget (≤ 2 Cores, ≤ 2 GB) and turnaround ceiling (≤ 45s) (#9)
- [x] 2.2 Update `tests/unit/test_anti_regression_guardrails.py` for REG-03, REG-08, REG-09, REG-14 (#9)
- [x] 2.3 Retire obsolete graphics test module `tests/unit/test_chunked_xfade.py` (#9)
- [x] 2.4 Update legacy channel fixtures and assertions in `tests/unit/test_branding.py` and `tests/unit/test_watchdog_resiliency.py` (#9)
- [x] 2.5 Clean up remaining legacy graphics test assertions in `test_ffmpeg_low_cpu_defaults.py` and `test_libass_subtitle_preference.py` (#9)

## Phase 3: Full Verification & Issue Management
- [x] 3.1 Verify full repository test suite (`pytest`) runs 100% green
- [x] 3.2 Run `./scripts/verify_integrity.sh`
- [x] 3.3 Rewrite GitHub issues #6-#10 with compressed, AI-optimized specifications
- [x] 3.4 Close resolved issues #7, #8, #9, #10 with verification receipts
- [x] 3.5 Archive SDD change and sync specs
