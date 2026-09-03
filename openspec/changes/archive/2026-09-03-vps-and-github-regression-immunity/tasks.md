# Tasks: VPS and GitHub Regression Immunity

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~250 lines (mostly deletions of dead code) |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (External & Git Hygiene) → PR 2 (Retire v2 Modules & CI) → PR 3 (Pre-Commit Hook & QA) |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | External & Git Hygiene | PR 1 | `git worktree list && git branch -a` | `git status` | `git checkout -b rollback-u1` |
| 2 | Retire Legacy Modules & CI | PR 2 | `pytest tests/e2e/test_tier1_features.py` | `grep -rn "src\.rendering" src/` | Restore pruned directories |
| 3 | Pre-Commit Hook & QA Verification | PR 3 | `bash .git/hooks/pre-commit && pytest` | Full test runner | Remove `.git/hooks/pre-commit` |

## Phase 1: External Filesystem & Git Remote Hygiene

- [ ] 1.1 Purge orphaned browser profiles and artifact directories in `/tmp/playwright*` and `/tmp/org.chromium*`.
- [ ] 1.2 Remove physical stale worktree directory `/home/moku/.gemini/antigravity-cli/worktrees/yt-auto/refactor_consolidate_codebase_tests`.
- [ ] 1.3 Prune dead worktrees from git administrative metadata using `git worktree prune -v`.
- [ ] 1.4 Fast-forward push local `main` (`fe294b0`) to GitHub `origin/main`.
- [ ] 1.5 Delete obsolete remote branch `origin/refactor_consolidate_codebase_tests` on GitHub.
- [ ] 1.6 Delete obsolete local branches `Ade-ia2005/yt-auto-main` and `refactor_consolidate_codebase_tests`.

## Phase 2: Legacy v2 Subsystem Retirement & CI Modernization

- [ ] 2.1 Remove obsolete `src/rendering/` directory (`renderer.py`, `camera_controller.py`).
- [ ] 2.2 Remove obsolete `src/compositing/` directory (`stream_renderer.py`, `subtitles.py`).
- [ ] 2.3 Remove obsolete `src/export/` directory (`pipeline.py`, `presets.py`).
- [ ] 2.4 Remove obsolete standalone CLI script `src/cli/cosmic_pipeline_cli.py`.
- [ ] 2.5 Retire legacy test files that explicitly tested the retired v2 browser renderer (`tests/unit/test_rendering_engine.py`, `tests/unit/test_compositing.py`, `tests/unit/test_media_cleanup.py`, `tests/integration/test_cosmic_pipeline_e2e.py`).
- [ ] 2.6 Remove `playwright install chromium` from `.github/workflows/tests.yml`.

## Phase 3: Automated Anti-Regression Gate & Final Verification

- [ ] 3.1 Create and install `.git/hooks/pre-commit` with executable permissions (`chmod +x`), verifying AST/regex rules forbidding `playwright` outside `src/youtube/uploader.py` and forbidding files in `docs/architecture/0*.md`.
- [ ] 3.2 Test pre-commit hook execution directly to ensure zero false positives on current clean tree.
- [ ] 3.3 Execute the comprehensive 90+ test suite (`pytest`) to certify 100% PASS with zero regressions.
- [ ] 3.4 Confirm zero active Chromium/Playwright processes across the entire VPS.
