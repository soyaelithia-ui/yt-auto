# Tasks: Purge Rotated Credentials

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 180–280 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Gitignore, hook, tests, audit, three docs | PR 1 | pytest tests/unit/test_security_policies.py | N/A (no runtime media/upload) | Revert gitignore, hook, security tests, audit, three docs |

## Phase 1: RED Tests

- [x] 1.1 In `tests/unit/test_security_policies.py`, fail until `.gitignore` (read-only) lists cookies.txt and *cookies*.txt.
- [x] 1.2 In `tests/unit/test_security_policies.py`, fail until `.gitignore` (read-only) lists drive_key.json.
- [x] 1.3 In `tests/unit/test_security_policies.py`, fail until `.githooks/pre-commit` (read-only) has filename regexes, extras (PEM, long ya29., AKIA, SA JSON), and --cached.
- [x] 1.4 In `tests/unit/test_security_policies.py`, fail until `.githooks/pre-commit` (read-only) blocks .hermes/ and has no grep -o or group dump.
- [x] 1.5 Threat docs-like: in `tests/unit/test_security_policies.py`, fail until `.githooks/pre-commit` (read-only) uses grep -I -q and does not exec staged docs-like files.
- [x] 1.6 Threat commit-state: in `tests/unit/test_security_policies.py`, fail until `.githooks/pre-commit` (read-only) uses --cached and --diff-filter=ACM.
- [x] 1.7 In `tests/unit/test_security_policies.py`, scan tracked non-Python text (md, json, sh, yml, yaml, txt, toml) and fail on a production-format signature.
- [x] 1.8 In `tests/unit/test_security_policies.py`, require .cursor/ and .hermes/ in `.gitignore` (read-only).
- [x] 1.9 In `tests/unit/test_security_policies.py`, fail until `dev/audit_security.py` (read-only) has no hardcoded out-of-workspace secrets path and checks stay under ROOT_DIR.
- [x] 1.10 In `tests/unit/test_security_policies.py`, fail until `dev/audit_security.py` (read-only) findings append rel_path only (never matched text).
- [x] 1.11 In `tests/unit/test_security_policies.py`, inspect `.githooks/pre-commit` (read-only) and `dev/audit_security.py` (read-only); patterns are generic regex/format, not live literals.
- [x] 1.12 In `tests/unit/test_security_policies.py`, construct samples with placeholders or runtime-built tokens; never copy live secrets.
- [x] 1.13 In `tests/unit/test_security_policies.py`, fail until `SECURITY.md` (read-only), `AGENTS.md` (read-only), and `docs/CONFIGURACION_SECRETOS.md` (read-only) mention git objects and stale refs.
- [x] 1.14 In `tests/unit/test_security_policies.py`, assert `SECURITY.md` (read-only), `AGENTS.md` (read-only), and `docs/CONFIGURACION_SECRETOS.md` (read-only) say history rewrite is not required.
- [x] 1.15 In `tests/unit/test_security_policies.py`, assert no default-apply remote-delete script exists.
- [x] 1.16 In `tests/unit/test_security_policies.py`, assert default apply has no git-push-delete helper.

## Phase 2: GREEN Hygiene

- [x] 2.1 Add cookies.txt, *cookies*.txt, and drive_key.json to `.gitignore`.
- [x] 2.2 Extend `.githooks/pre-commit`: filename blocks (.env except .env.example, cookies.json, secrets/), .hermes/ in agent-home regex, extras, grep -I -q, --cached ACM, path-only output.
- [x] 2.3 Update `dev/audit_security.py`: drop hardcoded out-of-workspace secrets Path; align extras and cookie/drive names; path-only issues.

## Phase 3: GREEN Docs

- [x] 3.1 In `SECURITY.md`, note residual git-object/ref risk; rewrite not required.
- [x] 3.2 In `AGENTS.md`, same residual-risk note; include .hermes/ in homedir policy.
- [x] 3.3 In `docs/CONFIGURACION_SECRETOS.md`, same residual-risk note.

## Phase 4: Verify

- [x] 4.1 Run pytest tests/unit/test_security_policies.py until Phase 1 tests pass.
