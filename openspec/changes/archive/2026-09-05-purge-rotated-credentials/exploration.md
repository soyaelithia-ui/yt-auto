## Exploration: Remaining credential leftovers after rotation

### Current State
HEAD `836459d` equals `origin/main` (PR #30). Worktree clean. Local `.env`, `secrets/`, `cookies.json`, `cookies/`, and `browser_data/` are absent (existence checks only; those files were not read). GitHub repo is already **private**.

HEAD format-signature scan of 634 tracked text files found **no live** Google API key / GOCSPX / OAuth client-id / Telegram bot / GitHub PAT / `sk-` / PEM / `ya29.`{50,} / AKIA hits. Residual matches are synthetic or regex text: `src/core/quality.py` (`BEGIN PRIVATE KEY` in a forbidden-output regex), `tests/unit/test_google_auth.py` (`1//sample_saved_refresh`), `tests/unit/test_api_health.py` and `tests/unit/test_drive.py` (empty `{"type":"service_account"}` fixtures). Cookie unit tests use placeholder values. `.env.example` has empty `KEY=` placeholders only. Tracked secret-shaped names: `.env.example` only. No agent homedirs tracked.

**Scanners today (status quo after PR #30):**
- `tests/unit/test_security_policies.py` — gitignore rules, agent-homedir `git ls-files`, production-format regexes on `src|tests|dev|scripts` `*.py` only.
- `.githooks/pre-commit` — rejects staged agent homedirs and production-format signatures; prints **paths only**. `core.hooksPath=.githooks`.
- `dev/audit_security.py` — tracked filename classes + Telegram/GOCSPX over `*.py|json|md|sh`; still probes `Path("/home/moku/secrets/google")` (outside workspace).
- CI (`.github/workflows/tests.yml`) runs `pytest -m "not live"` (includes security tests). No gitleaks/trufflehog/detect-secrets. Docker/compose interpolate `${TELEGRAM_*}` / mount `./secrets:/run/secrets:ro`; no embedded secret values. Entrypoint does not echo secrets.

**Ignore/hook coverage:** `.gitignore` blocks `.env`, `secrets/`, `cookies.json`, `*cookies*.json`, `*token*.json`, `*client_secret*.json`, `*.pem`, `*.key`, `*.token`, and agent homes including `.hermes/` and `.cursor/`. It does **not** ignore `cookies.txt` outside `secrets/` or `cookies/`, nor `drive_key.json` outside `secrets/`. Pre-commit does not filename-block `.env`/`cookies.json`/`secrets/`; agent-home regex omits `.hermes/`; signatures omit PEM, long `ya29.`, AKIA, service-account JSON. Tests do not require `.cursor/` or `.hermes/` in gitignore.

**History / other refs (commit ids + paths only, never values):**
- Live-format literals were removed from main in `b26f397`. Last dirty main ancestor: `170afef` (`b26f397^`).
- `tests/unit/test_security_policies.py` — Google API key, GOCSPX, OAuth client-id (present from add `7b06d33` through `170afef`).
- `dev/audit_security.py` — Telegram bot-token shape (from add `f1b35f3` through `170afef`).
- Deleted `dev/generate_longform_10min.py` — Telegram bot-token shape in `5d12e37`, `a4e6157`, `b5f91e50` (all ancestors of HEAD).
- `.codex/hooks.json` added `f1b35f3`, deleted `9243dbf` (agent homedir, not a format-signature hit).
- No git path history for `.env`, `cookies.json`, `*token*.json`, `*client_secret*.json`, `secrets/`, `*.pem`.
- **27 dirty branch tips** still contain the same two live-format files. Clean tips: `main`, `origin/main`, `fix/ffmpeg-61-unquoted-ass-filters`. Dirty locals include `Ade-ia2005/mira|ningyo|prs`, `chore/ffmpeg-first-ssot-policy`, `enforce_shorts_safe_zones`, `execute_script_logic`, `execute_script_refactor_logic`, `feat/docker-isolated-agy`, `feat/t1-integracion-aterrizaje-total`, `fix/ci-visual-quality-and-offline-suite`, `fix_hud_render_pipeline`, `perf/vertical-loop-stream-copy`, plus matching `origin/*` pre-#30 remotes.

Leak-response policy (AGENTS.md / SECURITY.md) is already followed for private repo + rotation + no public issue. Gap: no history/ref scan, no secret-hygiene OpenSpec, scanners do not cover stale tips or non-Python trees.

### Affected Areas
- `tests/unit/test_security_policies.py` — extend scan roots, gitignore assertions, extra format signatures (no live needles).
- `.githooks/pre-commit` — filename blocks; `.hermes/`; extra signatures; path-only reporting.
- `.gitignore` — `cookies.txt` / `*cookies*.txt` / `drive_key.json` classes outside `secrets/`.
- `dev/audit_security.py` — drop `/home/moku/secrets/google`; align pattern set with tests; do not print matches.
- `SECURITY.md`, `AGENTS.md`, `docs/CONFIGURACION_SECRETOS.md` — document residual history/ref risk; history rewrite remains optional.
- `.github/workflows/tests.yml` — optional audit job (HEAD-only).
- `scripts/design_thumbnails.py`, `scripts/design_impeccable_thumbnails.py` — hardcoded `~/.gemini/antigravity-cli/brain/...` isolation leftovers (not secrets).
- Stale local/remote branches listed above — still carry live-format literals at tips.
- `openspec/specs/` — no `secret-hygiene` spec yet (`cookie-management` / `service-health` only describe `secrets/cookies.txt`).

### Approaches
1. **A — HEAD-only scanner+tests (status quo after PR #30)** — Keep current hooks/tests; do nothing about stale refs or scanner gaps.
   - Pros: zero churn; main HEAD already clean; credentials rotated.
   - Cons: 27 dirty tips still hold live-format blobs; `cookies.txt` / out-of-repo path / non-Python trees uncovered; re-merge of stale branches can resurrect literals.
   - Effort: Low

2. **B — Extend scanners/hooks/tests and retire dirty refs without history rewrite** — Close filename and signature gaps; confine audit to the workspace; rebase or delete stale branches onto sanitized main; add a secret-hygiene spec; leave main history intact.
   - Pros: removes reachable leftovers; prevents reintroduction; matches SECURITY.md (rewrite optional); safe with concurrent occupancy on main; no force-push.
   - Cons: git objects on main history still contain old literals; deleting remote branches does not immediately GC blobs.
   - Effort: Medium

3. **C — History purge (BFG/filter-repo)** — Rewrite main (and remaining branches) to drop historical literals.
   - Pros: removes literals from git objects if GC’d and remotes force-updated.
   - Cons: high risk; does not un-leak existing clones; requires later explicit consent; conflicts with occupancy on this worktree; AGENTS.md forbids history rewrite unless chosen; credentials already rotated so residual risk is archival, not live.
   - Effort: High

### Recommendation
**Approach B.** Name: `purge-rotated-credentials`. Main HEAD is clean; live credentials are rotated; repo is private. Remaining work is (1) scanner/hook/gitignore/test gaps, (2) delete or rebase dirty pre-#30 tips, (3) remove the out-of-workspace audit path. Do **not** rewrite history unless the user later consents to C.

### Risks
- Stale remote branch tips still contain rotated live-format literals for anyone with private-repo access.
- Merging a dirty branch onto main would resurrect literals; hooks would catch a re-commit of current files but not a merge of old blobs if not staged as new content in a way the hook scans.
- History rewrite (C) would not un-leak clones and is unsafe while another agent occupies this worktree.
- Broader `sk-` / 12-digit client-id regexes can false-positive.
- `cookies.txt` at repo root is not gitignored.
- `dev/audit_security.py` still walks `/home/moku/secrets/google` (isolation violation if run).

### Ready for Proposal
Yes. Scope B only unless the user later consents to history purge.
