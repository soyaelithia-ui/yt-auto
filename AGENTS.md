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

## 3. Security, Credentials & Memory Governance
- **Zero Secrets in Memory**: Never persist credentials, OAuth tokens, API keys, cookies, cookie jars, `.env` values, or secrets into Engram, agent notes, session summaries, or logs. Always redact (`[REDACTED]`).
- **Strict Project Isolation**: Keep agent context, memory operations, and commands bound strictly to this project (`yt-auto`). Never read, write, or leak files outside the yt-auto workspace root (including `~/.ssh`, `~/.config`, sibling repositories, and unrelated directories).
- **Environment Isolation**: `.env`, `cookies.json`, and database state files remain local, untracked, and strictly non-extractable.

## 4. Concurrent Agent Worktrees
- Use `scripts/agent_worktree.sh` for create, force-remove, list, and prune. It MUST NOT delete or alter the primary repository checkout under any cleanup flag or argument error.
- `scripts/setup_worktree_env.sh` MUST idempotently link `.venv`, `.agents`, and `.env` into derived worktrees using safe relative (fallback absolute) paths. Never print secret file contents.
- Prefer shipping production video value over cosmetic refactors; do not rewrite working `src/` solely to slim line count when tests and performance contracts already pass.
