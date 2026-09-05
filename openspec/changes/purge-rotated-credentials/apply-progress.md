# Apply Progress: purge-rotated-credentials

**Change**: purge-rotated-credentials
**Mode**: Strict TDD
**Work unit**: hygiene-scanners-hooks-tests-docs
**Delivery**: single PR (stacked-to-main); Decision needed before apply: No; 400-line budget risk: Low

## Completed Tasks

- [x] 1.1–1.16 RED tests in `tests/unit/test_security_policies.py`
- [x] 2.1 `.gitignore` cookie-txt and drive_key.json classes
- [x] 2.2 `.githooks/pre-commit` filename blocks, `.hermes/`, extras, path-only
- [x] 2.3 `dev/audit_security.py` in-workspace, extras, cookie/drive names, rel_path
- [x] 3.1–3.3 residual git-object/ref risk docs; `.hermes/` in AGENTS.md
- [x] 4.1 `pytest tests/unit/test_security_policies.py` — 21 passed

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/unit/test_security_policies.py` | Unit | ✅ 5/5 | ✅ Written (failed: cookies.txt / *cookies*.txt missing) | ✅ Passed after 2.1 | ✅ 2 patterns | ➖ None needed |
| 1.2 | `tests/unit/test_security_policies.py` | Unit | ✅ 5/5 | ✅ Written (failed: drive_key.json missing) | ✅ Passed after 2.1 | ➖ Single | ➖ None needed |
| 1.3 | `tests/unit/test_security_policies.py` | Unit | ✅ 5/5 | ✅ Written (failed: .env.example / extras missing) | ✅ Passed after 2.2 | ✅ filename + PEM/ya29/AKIA/SA | ➖ None needed |
| 1.4 | `tests/unit/test_security_policies.py` | Unit | ✅ 5/5 | ✅ Written (failed: hermes missing) | ✅ Passed after 2.2 | ✅ hermes + no grep -o / BASH_REMATCH | ➖ None needed |
| 1.5 | `tests/unit/test_security_policies.py` | Unit | ✅ 5/5 | ✅ Written | ✅ Already present (`grep -I -E -q`; no exec) | ✅ grep -I -q + forbidden exec strings | ➖ None needed |
| 1.6 | `tests/unit/test_security_policies.py` | Unit | ✅ 5/5 | ✅ Written | ✅ Already present (`--cached`, `--diff-filter=ACM`) | ✅ both flags | ➖ None needed |
| 1.7 | `tests/unit/test_security_policies.py` | Unit | ✅ 5/5 | ✅ Written (scanner; HEAD clean so immediate pass) | ✅ Passed | ✅ extras + existing signatures; path-only | ➖ None needed |
| 1.8 | `tests/unit/test_security_policies.py` | Unit | ✅ 5/5 | ✅ Written | ✅ Already present (`.cursor/`, `.hermes/`) | ✅ both homes | ➖ None needed |
| 1.9 | `tests/unit/test_security_policies.py` | Unit | ✅ 5/5 | ✅ Written (failed: `/home/moku/secrets/google`) | ✅ Passed after 2.3 | ✅ no out-of-workspace Path + ROOT_DIR checks + cookie/drive names | ✅ `_rel_path` helper |
| 1.10 | `tests/unit/test_security_policies.py` | Unit | ✅ 5/5 | ✅ Written | ✅ Already present (`rel_path`; no match.group); 2.3 also uses rel_path for perms | ✅ rel_path + no group dump | ✅ permission issues now relative |
| 1.11 | `tests/unit/test_security_policies.py` | Unit | ✅ 5/5 | ✅ Written (failed: extras missing in hook/audit) | ✅ Passed after 2.2/2.3 | ✅ PEM/ya29/AKIA/SA in both sources; no live-format literals | ➖ None needed |
| 1.12 | `tests/unit/test_security_policies.py` | Unit | N/A (new) | ✅ Written | ✅ Passed (runtime-built PEM/ya29/AKIA/SA/Telegram) | ✅ 5 synthetic cases | ➖ None needed |
| 1.13 | `tests/unit/test_security_policies.py` | Unit | ✅ 5/5 | ✅ Written (failed: git objects / stale refs) | ✅ Passed after 3.1–3.3 | ✅ three docs | ➖ None needed |
| 1.14 | `tests/unit/test_security_policies.py` | Unit | ✅ 5/5 | ✅ Written (failed: not required) | ✅ Passed after 3.1–3.3 | ✅ three docs | ➖ None needed |
| 1.15 | `tests/unit/test_security_policies.py` | Unit | N/A (new) | ✅ Written | ✅ Passed (no remote-delete script) | ➖ Absence assertion | ➖ None needed |
| 1.16 | `tests/unit/test_security_policies.py` | Unit | N/A (new) | ✅ Written | ✅ Passed (no `git push --delete` helper) | ➖ Absence assertion | ➖ None needed |
| 2.1 | `tests/unit/test_security_policies.py` | Unit | ✅ RED suite | ➖ Production | ✅ gitignore | ➖ Covered by 1.1–1.2 | ➖ None needed |
| 2.2 | `tests/unit/test_security_policies.py` | Unit | ✅ RED suite | ➖ Production | ✅ hook | ➖ Covered by 1.3–1.6, 1.11 | ➖ None needed |
| 2.3 | `tests/unit/test_security_policies.py` | Unit | ✅ RED suite | ➖ Production | ✅ audit | ➖ Covered by 1.9–1.11 | ✅ `_rel_path` |
| 3.1 | `tests/unit/test_security_policies.py` | Unit | ✅ RED suite | ➖ Docs | ✅ SECURITY.md | ➖ Covered by 1.13–1.14 | ➖ None needed |
| 3.2 | `tests/unit/test_security_policies.py` | Unit | ✅ RED suite | ➖ Docs | ✅ AGENTS.md + `.hermes/` | ➖ Covered by 1.13–1.14 | ➖ None needed |
| 3.3 | `tests/unit/test_security_policies.py` | Unit | ✅ RED suite | ➖ Docs | ✅ CONFIGURACION_SECRETOS.md | ➖ Covered by 1.13–1.14 | ➖ None needed |
| 4.1 | `tests/unit/test_security_policies.py` | Unit | ✅ 21/21 | ➖ Verify | ✅ `pytest tests/unit/test_security_policies.py` exit 0, 21 passed | ➖ N/A | ➖ None needed |

### Test Summary

- **Total tests written**: 16 new (+ 5 existing retained) = 21 in file
- **Total tests passing**: 21
- **Layers used**: Unit (21), Integration (0), E2E (0)
- **Approval tests** (refactoring): None — no refactoring-only tasks
- **Pure functions created**: 1 (`_rel_path` in audit); test helpers `_gitignore_lines`, `_hook_text`, `_audit_text`, `_assert_no_live_format`

RED gate (before GREEN): `8 failed, 13 passed` on `pytest tests/unit/test_security_policies.py`. Failures were 1.1, 1.2, 1.3, 1.4, 1.9, 1.11, 1.13, 1.14. Already-green RED tests: 1.5, 1.6, 1.7, 1.8, 1.10, 1.12, 1.15, 1.16.

GREEN gate: `21 passed in 1.14s`, exit 0.

## Work Unit Evidence

| Evidence | Required value |
|---|---|
| Focused test command and exact result | `pytest tests/unit/test_security_policies.py` — exit 0, 21 passed in 1.14s |
| Runtime harness command/scenario and exact result | N/A — no runtime media/upload boundary; secret hygiene is scanners/hooks/docs only |
| Rollback boundary | Revert `.gitignore`, `.githooks/pre-commit`, `tests/unit/test_security_policies.py`, `dev/audit_security.py`, `SECURITY.md`, `AGENTS.md`, `docs/CONFIGURACION_SECRETOS.md` |

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `tests/unit/test_security_policies.py` | Modified | RED tests 1.1–1.16; extras; non-Python scan; synthetic fixtures |
| `.gitignore` | Modified | `cookies.txt`, `*cookies*.txt`, `drive_key.json` |
| `.githooks/pre-commit` | Modified | Filename blocks; hermes; extras; SA AND; path-only |
| `dev/audit_security.py` | Modified | Drop out-of-workspace Path; extras; cookie/drive names; rel_path issues |
| `SECURITY.md` | Modified | Residual git objects/stale refs; rewrite not required; `.hermes/` |
| `AGENTS.md` | Modified | Residual-risk note; `.hermes/` in homedir policy |
| `docs/CONFIGURACION_SECRETOS.md` | Modified | Residual-risk note |
| `openspec/changes/purge-rotated-credentials/tasks.md` | Modified | Marked 1.1–4.1 `[x]` |
| `openspec/changes/purge-rotated-credentials/apply-progress.md` | Created | This artifact |

## Deviations from Design

None — implementation matches design. Tight extra signatures (PEM, long `ya29.`, AKIA, SA JSON AND). No live needles. Path-only reports. No `/home/moku/secrets/google`. No remote delete. No history rewrite. No new scanner framework. Pre-commit stays bash `grep -I -q` on cached names.

## Issues Found

None.

## Remaining Tasks

None. 23/23 complete.

## Workload / PR Boundary

- Mode: single PR
- Current work unit: hygiene-scanners-hooks-tests-docs
- Boundary: gitignore + hook + security tests + audit + three docs
- Estimated review budget impact: Low (forecast 180–280)

## Status

23/23 tasks complete. Ready for verify.
