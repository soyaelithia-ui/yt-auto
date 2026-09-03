# Proposal: Eradicate Legacy Rendering Artifacts and Enforce Cross-Environment Guardrails

## Intent
Despite previous cleanup passes that removed retired rendering implementations (`src/rendering/`, `src/compositing/`), legacy artifacts continue to resurface due to gaps in governance enforcement:
1. Dead unit test files (`tests/unit/test_procedural_compositor_subtitles.py` and `tests/unit/test_subtitle_safe_zone.py`) remained tracked in Git, attempting to import deleted modules and causing pytest collection failures.
2. `openspec/config.yaml` continued declaring `Playwright` and `Pillow` in its tech stack context.
3. Neither `.githooks/pre-commit` nor `scripts/verify_integrity.sh` enforced AST import checks against retired namespaces or executed full test suite collection (`pytest --collect-only`), allowing broken tests to slip past integrity audits.
4. Local commits on `/srv/projects/yt-auto` drifted ahead of GitHub `origin/main` without end-to-end sync.

This change permanently eliminates all remaining legacy references, implements automated AST and pre-commit import gates, and synchronizes the entire VPS and GitHub repository.

## Scope
### In Scope
- Physically delete dead legacy test files importing retired modules (`src.rendering`, `src.compositing`).
- Align `openspec/config.yaml` to the real tech stack (FFmpeg Stream-Copy, libass, Edge-TTS, SQLite, WebGPU, resvg).
- Update delta spec `subtitles-safe-zone` to reflect `ASSSubtitleGenerator`.
- Introduce automated guardrail tests `REG-10` and `REG-11` in `tests/unit/test_anti_regression_guardrails.py`.
- Fortify `.githooks/pre-commit` and `scripts/verify_integrity.sh` with import bans and full `pytest --collect-only` checks.
- Commit, synchronize and push verified changes to `origin/main` on GitHub and across `/srv/projects/yt-auto`.

### Out of Scope
- Modifying the core video generation pipeline logic (`src/media/loop_engine.py` or `src/pipeline.py`), which is already operating on Stream-Copy.
- Re-architecting database schemas or SQLite migrations.

## Approach
1. **Red Test Phase**: Author automated guardrail tests `REG-10` (banning retired imports across `src/` and `tests/`) and `REG-11` (enforcing clean `openspec/config.yaml`).
2. **Purge & Sanitize**: Remove the dead test files, update `openspec/config.yaml`, and update `openspec/specs/subtitles-safe-zone/spec.md`.
3. **Green Test Phase**: Verify all guardrail tests, `verify_integrity.sh`, and `pytest --collect-only` pass with 0 errors.
4. **Hook & Gate Fortification**: Update `.githooks/pre-commit` and `scripts/verify_integrity.sh` to fail closed if any retired import or uncollectable test is introduced.
5. **Sync Phase**: Commit at worktree level, merge/reconcile with `/srv/projects/yt-auto` main, push to GitHub `origin/main`, and prune stale worktrees.

## Capabilities
### New Capabilities
- `legacy-eradication-guardrails`: Automated AST scanner and integrity check preventing any code or tests from importing `src.rendering`, `src.compositing`, or `src.export`, and guaranteeing 100% collectability of the test suite.

### Modified Capabilities
- `subtitles-safe-zone`: Updated contract referencing `ASSSubtitleGenerator` (`src/media/subtitles_ass.py`) instead of the deprecated `TerminalKaraokeSubtitleGenerator`.

## Impact
- **Deleted files**: `tests/unit/test_procedural_compositor_subtitles.py`, `tests/unit/test_subtitle_safe_zone.py`.
- **Modified files**: `openspec/config.yaml`, `openspec/specs/subtitles-safe-zone/spec.md`, `tests/unit/test_anti_regression_guardrails.py`, `.githooks/pre-commit`, `scripts/verify_integrity.sh`, `tests/unit/test_quality_gate_resolution.py`.
- **Breaking changes**: None. The deleted tests were already broken and covered by modern suites (`tests/unit/test_subtitles_ass.py`).

## Rollback Plan
If any unforeseen regression occurs, Git history preserves all states. Rollback command: `git revert HEAD` or restore tracked files via `git checkout`.
