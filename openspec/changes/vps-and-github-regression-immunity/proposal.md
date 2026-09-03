# Proposal: VPS and GitHub Regression Immunity

## Intent
Permanently eliminate the risk of reverting to obsolete commits, resurrected legacy browser rendering modules (Playwright/Chromium), and stale worktrees across both GitHub and the host VPS by establishing automated pre-commit gates, external filesystem hygiene, and branch alignment.

## Scope

### In Scope
- **External Hygiene**: Purge leftover worktrees in `/home/moku/.gemini/antigravity-cli/worktrees/yt-auto/`, prune `.git/worktrees/`, and clean `/tmp/playwright*` orphan folders.
- **Git SSOT Alignment**: Push verified commit `fe294b0` to GitHub `origin/main`, delete stale remote branch `origin/refactor_consolidate_codebase_tests`, and prune local branches `Ade-ia2005/yt-auto-main` and `refactor_consolidate_codebase_tests`.
- **Legacy Module Retirement**: Deprecate/retire obsolete v2 rendering subsystems (`src/rendering/`, `src/compositing/`, `src/export/`, `src/cli/cosmic_pipeline_cli.py`) that still contain direct Playwright imports.
- **Automated Anti-Regression Gates**: Install `.git/hooks/pre-commit` to reject any commits introducing browser dependencies in media generation or restoring deleted architecture docs.
- **CI Modernization**: Remove `playwright install chromium` from `.github/workflows/tests.yml`.

### Out of Scope
- Altering YouTube video upload fallback logic in `src/youtube/uploader.py` (which uses session cookies when API quota is exhausted).
- Modifying production database schema v005 or active channel assets.

## Capabilities

### New Capabilities
- `anti-regression-git-hooks`: Deterministic pre-commit hook enforcing zero browser imports in video pipelines and blocking resurrected documents before commit creation.

### Modified Capabilities
- `media-processing-performance-policy`: Expand zero-browser mandate to explicitly include retirement of `src/rendering/` and `src/compositing/`.

## Approach
1. Clean external directories on VPS (`/tmp/playwright*`, `.gemini/worktrees/`, `.git/worktrees/`).
2. Synchronize GitHub `origin/main` to `fe294b0` and prune stale branches.
3. Prune legacy v2 rendering files and update CI configuration.
4. Deploy `.git/hooks/pre-commit` executable enforcing zero browser regressions.
5. Verify 97/97 tests pass with zero lingering processes.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `/tmp/playwright*` | Removed | Purge >30 orphaned browser profile/artifact directories |
| `.gemini/worktrees/` | Removed | Delete physical stale worktree directory |
| `.git/worktrees/` | Removed | Prune stale worktree registrations via `git worktree prune` |
| `GitHub / Local Git` | Modified | Push `fe294b0` to `origin/main`; delete stale branches |
| `src/rendering/` & `src/compositing/` | Removed | Retire legacy modules importing Playwright |
| `src/cli/cosmic_pipeline_cli.py` | Removed | Retire legacy CLI script |
| `.github/workflows/tests.yml` | Modified | Remove `playwright install chromium` step |
| `.git/hooks/pre-commit` | New | Install automated anti-regression hook |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Accidental deletion of active worktrees | Low | Verified `/home/moku/projects/yt-auto` is the sole authoritative repo |
| Breaking YouTube upload fallback | Low | `src/youtube/uploader.py` remains untouched and explicitly allowed |

## Rollback Plan
Create git tag `pre-immunity-hardening-tag`. Revert hooks and branch deletions if required.

## Success Criteria
- [ ] 0 stale worktrees registered in `git worktree list`.
- [ ] `origin/main` on GitHub equals local `main` (`fe294b0`); 0 stale remote branches.
- [ ] 0 files in `src/media/`, `src/rendering/`, or `src/cli/` import `playwright`.
- [ ] `.git/hooks/pre-commit` active and blocking forbidden imports.
- [ ] 100% of the 97-test anti-regression suite passes cleanly.
