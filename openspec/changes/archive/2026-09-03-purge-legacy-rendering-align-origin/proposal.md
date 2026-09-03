# Proposal: Purge Legacy Browser Rendering and Align with Origin Main

## Intent
Eliminate lingering headless browser rendering dependencies (Playwright/Chromium) across video pipelines, align the local codebase with GitHub `origin/main` (commit `acc279f`), purge resurrected obsolete architecture documents, and integrate validated WebGPU WGSL shaders.

## Scope

### In Scope
- Synchronize local repository with authoritative GitHub `origin/main` (`acc279f`).
- Remove 5 resurrected legacy architecture markdown files in `docs/architecture/`.
- Ensure zero Playwright/Chromium invocations across `main.py loop`, `main.py run`, and media synthesis.
- Port and integrate non-blocking native procedural WGSL shaders (`src/media/native_procedural.py`) and cinematic direction updates from `/home/moku/projects/yt-auto`.
- Validate 100% test pass rate across unit, integration, and E2E suites with zero quota consumption.

### Out of Scope
- Modifying production publishing credentials or live YouTube channel tokens.
- Altering core SQLite WAL transactional migration schemas (001-005).

## Capabilities

### New Capabilities
None

### Modified Capabilities
- `media-processing-performance-policy`: Explicitly prohibit headless browser instantiation (Playwright/Chromium) for video synthesis and loop generation; require pure FFmpeg and native WGSL rendering.
- `test-infrastructure`: Enforce zero-quota automated validation ensuring test suites execute without browser binaries.

## Approach
1. Fast-forward and rebase on GitHub `origin/main` (`acc279f`), which already pruned 15,285 lines of legacy web renderers (`c75541b`).
2. Remove resurrected obsolete docs in `docs/architecture/` (`01_DUAL_RENDERING_ENGINES.md` through `05_ZERO_QUOTA_TESTING_FRAMEWORK.md`).
3. Apply validated WGSL shader uniforms and cinematic storyboard improvements from `/home/moku/projects/yt-auto`.
4. Partition tasks into 3 decoupled work units for Teamwork parallel execution.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `docs/architecture/` | Removed | Purge 5 obsolete markdown files resurrected in PR #1 merge |
| `src/cli/handlers/loop.py` | Modified | Ensure loop synthesis uses FFmpeg `LoopSynthesizerWorker` exclusively |
| `src/media/native_procedural.py` | Modified | Integrate WGSL shaders with luminance floor and safe pipe handling |
| `openspec/specs/media-processing-performance-policy/spec.md` | Modified | Add explicit prohibition against browser-based video rendering |
| `tests/unit/test_native_procedural_uniforms.py` | New | Verify native procedural buffer packing and broken pipe guards |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Merge conflicts during origin/main synchronization | Low | Merge base is cleanly identified (`145dfc8`); changes are modular |
| Lingering references to `WebVideoRenderer` in tests | Low | `origin/main` already pruned obsolete adversarial browser tests |

## Rollback Plan
Create an atomic pre-alignment git tag (`pre-purge-alignment-backup`). If synchronization fails, reset hard to this tag.

## Success Criteria
- [ ] 0 files in `src/` import `playwright` for video composition or loop synthesis.
- [ ] 5 resurrected legacy docs in `docs/architecture/` are completely removed.
- [ ] 100% of test suites pass cleanly via `pytest` without browser launching.
- [ ] Codebase is byte-synchronized with GitHub `origin/main` plus clean WGSL improvements.
