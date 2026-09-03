# Tasks: Eradicate Legacy Rendering Artifacts and Enforce Cross-Environment Guardrails

## Phase 1: Red Guardrail Tests (TDD-RED)
- [x] 1.1 Add `test_reg10_zero_imports_of_retired_legacy_subsystems` to `tests/unit/test_anti_regression_guardrails.py` scanning `src/` and `tests/` for `src.rendering`, `src.compositing`, `src.export`.
- [x] 1.2 Add `test_reg11_zero_playwright_in_openspec_config` to `tests/unit/test_anti_regression_guardrails.py` asserting clean `context:` in `openspec/config.yaml`.
- [x] 1.3 Run guardrail suite and confirm failure (RED) detecting existing legacy files and config.

## Phase 2: Purge & Sanitize (TDD-GREEN)
- [x] 2.1 Physically delete dead test `tests/unit/test_procedural_compositor_subtitles.py`.
- [x] 2.2 Physically delete dead test `tests/unit/test_subtitle_safe_zone.py`.
- [x] 2.3 Sanitize `openspec/config.yaml` to remove Playwright and Pillow, declaring Stream-Copy & libass.
- [x] 2.4 Update `openspec/specs/subtitles-safe-zone/spec.md` interface reference to `ASSSubtitleGenerator`.
- [x] 2.5 Run guardrail suite and confirm pass (GREEN).

## Phase 3: Fortify Gates & Pre-Commit
- [x] 3.1 Update `scripts/verify_integrity.sh` with step 3b (recursive grep for retired imports) and step 6b (`pytest --collect-only -q` failure trap).
- [x] 3.2 Update `.githooks/pre-commit` with rule 5 blocking staged files importing retired subsystems.
- [x] 3.3 Execute `./scripts/verify_integrity.sh` and verify all 8 invariants pass with 0 failures.

## Phase 4: Multi-Environment Synchronization (VPS & GitHub)
- [x] 4.1 Commit sanitized changes to Git with conventional message `fix(hygiene): eradicate legacy test artifacts and enforce anti-resurrection guardrails`.
- [x] 4.2 Merge into `/srv/projects/yt-auto` (`main`).
- [x] 4.3 Push clean `main` to GitHub `origin/main`.
- [x] 4.4 Run `git worktree prune` and verify VPS permissions for group `developers`.
