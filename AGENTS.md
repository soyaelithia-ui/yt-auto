# Agent Directives and Inviolable Project Governance

## 1. Project Invariants and Mandatory Cadence Check
- Every **25 commits** or before starting any major work or pipeline execution, you MUST execute `./scripts/verify_integrity.sh`.
- **Mandatory Work Refusal (Kill Switch)**: If `./scripts/verify_integrity.sh` returns any failure (code 1), you MUST REFUSE TO PROCEED with feature work or video generation. Stop, alert the user, and resolve the regression.
- **Zero-Browser Policy**: Absolutely zero `playwright` or `chromium` imports in `src/media/`, `src/cli/`, `src/narrative/`, or `src/core/`. Playwright is restricted to `src/youtube/` exclusively for fallback session uploads.
- **Zero Resurrected Docs**: Absolutely zero legacy architecture blueprints in `docs/architecture/0*.md` or retired modules (`src/rendering/`, `src/compositing/`, `src/export/`).

## 2. Product Value Priority vs. Premature Refactoring
- **Ship Production Value First**: Prioritize functional video publishing and measurable audience quality over cosmetic code slimming or aesthetic refactors.
- **Refactoring Prohibition**: Never undertake massive rewrites or module mergers in working `src/` code solely to decrease line count if tests pass and performance contracts are met.
- **Anti-Bloat Policy**: Never commit minified libraries (`*.min.js`), third-party tools, or vendored skills (e.g. dozens of `.mjs` files) to this repository. The pre-commit hook (`.githooks/pre-commit`) will strictly reject them.
