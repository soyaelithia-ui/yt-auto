# Tasks: Implement and Verify Project Policies (yt-auto v3.1)

## Phase 1: Policy Specifications and Architectural Assets
- [x] 1.1 Formulate OpenSpec proposal and policy specifications in `openspec/changes/2026-09-01-project-policies/specs/`
- [x] 1.2 Document architecture design decisions and sequence diagrams in `design.md`
- [x] 1.3 Update project documentation across `docs/` (`ARQUITECTURA.md`, `INTEGRACIONES_Y_SERVICIOS.md`, `AGENTES_IA_Y_POLITICA.md`, `TROUBLESHOOTING.md`)

## Phase 2: Core Policy Enforcement Components
- [x] 2.1 Implement `SessionHealthValidator` in `src/core/cookies.py` with <48h expiration warnings
- [x] 2.2 Implement `SessionUploader` in `src/youtube/session_uploader.py` for zero-quota direct publishing
- [x] 2.3 Implement `TTSRouter` in `src/audio/tts_router.py` with multi-tier circuit breaker
- [x] 2.4 Implement `LeaseReaper` in `src/core/lease_reaper.py` with active PID liveness monitoring
- [x] 2.5 Implement `DBReconciler` in `src/core/db_reconciler.py` for 2PC dual-database atomic consistency
- [x] 2.6 Implement `GPUDetector` in `src/core/gpu_detector.py` for headless safe Chromium defaults

## Phase 3: Media Processing and Subtitle Geometry Standards
- [x] 3.1 Migrate temporary audio and silence generation in `lib/audio.py` to volatile RAM `/dev/shm`
- [x] 3.2 Implement dynamic Pillow font metrics bounding box calculation and auto-wrapping in `lib/subtitles.py`
- [x] 3.3 Ensure Safe Area $MarginV \ge 260\text{px}$ in 9:16 vertical subtitle formatting

## Phase 4: Test Suite and Compliance Verification
- [x] 4.1 Implement comprehensive unit tests in `tests/unit/test_v3_1_architecture_components.py`
- [x] 4.2 Execute test suite ensuring 100% compliance across all policy scenarios
