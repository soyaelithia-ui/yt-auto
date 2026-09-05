# Design: Purge Rotated Credentials

## Technical Approach

Approach B: extend gitignore, `.githooks/pre-commit`, `tests/unit/test_security_policies.py`, and `dev/audit_security.py`; document residual git-object/ref risk. Default apply is those plus docs — no history rewrite, no remote deletes unless an operator SHA list exists. Optional HEAD-only CI audit is SHOULD; existing pytest + pre-commit already cover HEAD. Maps to `secret-hygiene` (7 requirements, 14 scenarios). DSP/EBU R128: N/A. No sequence diagram.

## Architecture Decisions

| Option | Tradeoff | Decision |
|--------|----------|----------|
| New scanner / hook-invoked Python helper | DRY vs exec of user paths | **No.** Bash `grep` on `git diff --cached --name-only`; tests inspect sources to keep regexes aligned |
| Default apply deletes dirty pre-#30 remotes | Closes tips vs missing rollback SHAs | **No** without an operator SHA list. Default = scanners/hooks/tests/docs |
| History rewrite (BFG/filter-repo) | Purges objects vs occupancy/force-push | **Out of scope** (Approach C) |
| New CI `audit_security.py` job | Extra signal vs duplicate pytest+hook | **SHOULD, not required** |
| Loose extra signatures | Catch more vs false positives (`ya29.test_*`, empty SA JSON, `BEGIN PRIVATE KEY` in `src/core/quality.py`) | Tight generics below |
| Filename-block `.env*` | Stops leaks vs rejecting `.env.example` | Reject `.env` / `.env.<name>` except `.env.example` |

## Data Flow

```
git commit → git diff --cached --name-only --diff-filter=ACM
  → filename / `.hermes/` reject (path)
  → grep -I -E -q signatures (path, never match text)
pytest test_security_policies.py → gitignore + git ls-files text
audit_security.py → ROOT_DIR + git ls-files; path-only issues
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `.gitignore` | Modify | Add `cookies.txt`, `*cookies*.txt`, `drive_key.json` |
| `.githooks/pre-commit` | Modify | Filename blocks; `.hermes/` in agent-home regex; extra signatures; path-only echo |
| `tests/unit/test_security_policies.py` | Modify | New gitignore asserts; `.cursor/` + `.hermes/`; scan beyond `*.py`; extras; inspect hook/audit |
| `dev/audit_security.py` | Modify | Drop `Path("/home/moku/secrets/google")`; align signatures and cookie/drive names; path-only |
| `SECURITY.md` | Modify | Residual history/ref risk; rewrite not required |
| `AGENTS.md` | Modify | Same residual-risk note; `.hermes/` in homedir policy |
| `docs/CONFIGURACION_SECRETOS.md` | Modify | Same residual-risk note |
| `.github/workflows/tests.yml` | Optional | HEAD-only audit job; omit unless cheap |

No `src/` edits.

## Interfaces / Contracts

Canonical extras (generic; never live needles):

- PEM: `-----BEGIN [A-Z ]*PRIVATE KEY-----`
- Long Google access: `ya29\.[A-Za-z0-9_-]{50,}`
- AWS id: `AKIA[0-9A-Z]{16}`
- SA JSON: `"type"\s*:\s*"service_account"` **and** `"private_key"`

Keep existing AIzaSy, GOCSPX, `sk-`, `ghp_`, Telegram, and 12-digit client-id patterns.

Staged filename rejects: `.env` except `.env.example`; `cookies.json`; `secrets/`; `.hermes/`.

Failure output: path lines only. Tests/audit messages use relative paths, never matched text.

Audit permission checks: `ROOT_DIR / ".env"` and `ROOT_DIR / "secrets"` only.

## Testing Strategy

Extend `tests/unit/test_security_policies.py`. RED first. No user-path exec.

| Scenario | RED test |
|----------|----------|
| Cookie-txt ignored | gitignore has `cookies.txt` and `*cookies*.txt` |
| Drive key ignored | gitignore has `drive_key.json` |
| Filename/signature blocked | hook has filename regexes, extras, `--cached` |
| Hermes / no match print | hook includes `.hermes/`; no `grep -o` / group dump |
| Non-Python scanned | `git ls-files` text (`.md` `.json` `.sh` `.yml` `.yaml` `.txt` `.toml` `.py`) fails on a signature |
| Agent homes in gitignore | require `.cursor/` and `.hermes/` |
| Audit in-workspace | no `/home/moku/secrets/google`; checks under `ROOT_DIR` |
| Audit paths not matches | findings append `rel_path` only |
| Generic signatures only | hook/audit/tests patterns are regex/format, not live literals |
| Synthetic fixtures allowed | placeholders or runtime-built (`"A"*35`) |
| Docs residual risk | three docs mention git objects/stale refs |
| History rewrite out of scope | no BFG/filter-repo; docs say rewrite not required |
| Optional SHA retirement | no default-apply remote-delete script |
| No SHA list → no remote delete | no `git push --delete` helper in default apply |

Integration: existing CI pytest. E2E: N/A.

## Threat Matrix

| Boundary | Applicability | Design response | Planned RED tests |
|----------|---------------|-----------------|-------------------|
| Documentation-like paths | **Applicable** — staged docs grepped as text | `grep -I` only; never exec `README.sh` / md / `requirements.txt` | Hook `grep -I -q` not exec; non-py scan |
| Git repository selection | **N/A** — no `git -C` or user repo path | `cwd=BASE_DIR` / `ROOT_DIR` | none |
| Commit state | **Applicable** — index-only hook | `--cached` ACM; empty index passes; unstaged ignored | Assert `--cached` and `--diff-filter=ACM` |
| Push state | **N/A** — default apply does not push/delete remotes | Operator SHA list gates optional retirement | Scenario 14: no default remote-delete |
| PR commands | **N/A** — no PR automation | — | none |

## Migration / Rollout

No migration. Ship the hygiene PR. Tip retirement is operator-only with recorded SHAs. Rollback: revert the PR.

## Open Questions

None.
