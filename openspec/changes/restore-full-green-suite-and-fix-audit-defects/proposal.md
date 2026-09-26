# Proposal: Restore Full Repository Green Suite and Fix Audit Defects

## Intent
Address and resolve open GitHub audit issues (#7, #8, #9, #10) while compressing issue specifications and streamlining codebase invariants for autonomous AI agents without overengineering or bloat.

## Scope
1. **deploy/ctl.sh (#10)**: Match Docker Compose v2 container naming (`(^|[-_])yt-automation([-_]|$)`) to prevent concurrent host/container execution collisions.
2. **src/youtube/uploader/session.py (#8)**: Guard screenshot directory path construction when `screenshot_dir` is `None` or custom path.
3. **src/youtube/control.py & src/analytics/pruner.py (#7)**: Export and explicitly verify video channel ownership with dedicated unit test coverage.
4. **Test Suite Hygiene & Anti-Regression Alignment (#9)**:
   - Synchronize `test_anti_regression_guardrails.py` and `docs/FFMPEG_LOW_CPU.md` with stream-copy and local-loop policies.
   - Retire legacy tests targeting deleted graphics engines (`hybrid_engine.py`, `compositor.py`, `inmemory_compositor.py`, `test_chunked_xfade.py`).
   - Fix canonical channel alias resolution in `src/llm.py` and update test assertions to `CanonicalChannel` (`horror`, `drama`).
   - Restore 100% pass rate across the full test suite.
5. **Issue Optimization**:
   - Rewrite GitHub issues into dense, unambiguous, machine-readable specifications optimized for AI agents.
   - Close resolved issues with deterministic verification receipts.
