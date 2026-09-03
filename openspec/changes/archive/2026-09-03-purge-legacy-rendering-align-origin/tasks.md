# Tasks: Purge Legacy Browser Rendering and Align with Origin Main

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~350 lines |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Git & Docs Cleanup) → PR 2 (Media Engine & WGSL) → PR 3 (QA Verification) |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Git SSOT Alignment & Doc Purge | PR 1 | `git status` | N/A (repo alignment) | `git reset --hard pre-purge-alignment-backup` |
| 2 | Native Procedural & Media Hardening | PR 2 | `pytest tests/unit/test_native_procedural_uniforms.py` | `main.py loop generate -c drama_aita -o horizontal` | Revert `src/media/` and `src/cli/handlers/loop.py` |
| 3 | QA Certification & Test Verification | PR 3 | `pytest tests/unit/test_loop_video_engine.py tests/integration/test_multiscene_dispatch.py` | Full zero-quota test runner | Revert test additions |

## Phase 1: Git SSOT & Workspace Reconciliation (Subagent 1)

- [ ] 1.1 Fast-forward `/home/moku/projects/yt-auto` `main` branch to match `origin/main` (`acc279f`).
- [ ] 1.2 Remove the 5 resurrected obsolete architecture docs in `docs/architecture/` (`01_DUAL_RENDERING_ENGINES.md` to `05_ZERO_QUOTA_TESTING_FRAMEWORK.md`).
- [ ] 1.3 Remove/prune outdated `implement_grill_test_suite` worktree anchored to pre-pruning commit `7b06d33`.

## Phase 2: Media Engine Hardening & WGSL Integration (Subagent 2)

- [ ] 2.1 Reconcile `src/media/native_procedural.py` with hex accent color parsing, photometric luminance floor, and safe pipe error handling.
- [ ] 2.2 Verify `src/cli/handlers/loop.py` uses `LoopSynthesizerWorker` with native FFmpeg exclusively; assert 0 imports of `WebVideoRenderer`.
- [ ] 2.3 Update `openspec/specs/media-processing-performance-policy/spec.md` with explicit prohibition against headless browser rendering.

## Phase 3: QA Certification & Zero-Quota Regression Suite (Subagent 3)

- [ ] 3.1 Verify `tests/unit/test_native_procedural_uniforms.py` and `tests/integration/test_multiscene_dispatch.py` pass 100%.
- [ ] 3.2 Execute `tests/unit/test_loop_video_engine.py` ensuring zero regressions on loop composition.
- [ ] 3.3 Confirm zero active Chromium/Playwright processes spawned during end-to-end execution.
