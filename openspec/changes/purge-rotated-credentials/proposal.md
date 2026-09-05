# Proposal: Purge Rotated Credentials

## Intent

HEAD `836459d` (post-rotation, PR #30) has no live-format literals in tracked text; repo is private. Close scanner/hook/gitignore/test gaps, confine audit to the workspace, and retire dirty pre-#30 tips. Main history intact.

## Scope

### In Scope
- `.gitignore`: `cookies.txt`, `*cookies*.txt`, `drive_key.json` classes outside `secrets/`
- Pre-commit: secret-filename blocks; `.hermes/`; extra signatures (PEM, long `ya29.`, AKIA, service-account JSON); path-only reports
- `tests/unit/test_security_policies.py`: scan beyond `*.py`; assert `.cursor/` and `.hermes/` gitignore
- `dev/audit_security.py`: drop `Path("/home/moku/secrets/google")`; align signatures; never print matches
- Docs (`SECURITY.md`, `AGENTS.md`, `docs/CONFIGURACION_SECRETOS.md`): residual history/ref risk
- Optional HEAD-only CI audit job; retire/rebase dirty pre-#30 tips; new `secret-hygiene` spec

### Out of Scope
- History rewrite (BFG/filter-repo/force-push)
- Reading `.env` / `cookies.json` / live secrets
- Public GitHub issue; live needles in tests
- Media/ffmpeg work; Approaches A and C

## Capabilities

### New Capabilities
- `secret-hygiene`: Workspace-confined scanners, hooks, gitignore, and tests that block secret-shaped filenames and production-format signatures without live needles; path-only reports.

### Modified Capabilities
None

## Approach

Approach B only: extend scanners/hooks/tests/gitignore; confine audit to the workspace; retire or rebase dirty pre-#30 tips; add `secret-hygiene`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| Hygiene surfaces | Modified | `.gitignore`, `.githooks/pre-commit`, `tests/unit/test_security_policies.py`, `dev/audit_security.py` |
| Docs / CI | Modified | Residual history/ref risk; optional HEAD-only audit job |
| Dirty pre-#30 tips | Removed/rebased | Onto sanitized main |
| `openspec/specs/secret-hygiene/` | New | Capability spec |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Stale tips hold rotated literals | Med | Delete or rebase onto sanitized main |
| Dirty merge resurrects literals | Med | Retire tips; hooks/tests on new content |
| Broader signatures false-positive | Med | Generic format signatures; no live needles |
| History objects remain after delete | Low | Docs; rewrite deferred |
| Audit walks outside workspace | Low | Drop hardcoded out-of-repo path |

## Rollback Plan

Revert the hygiene PR (gitignore, hooks, tests, audit, docs, optional CI). Recreate a retired tip from its recorded SHA if deleted in error.

## Media processing performance impact

None / N/A — secret hygiene only; no media/ffmpeg path changes.

## Dependencies

- Credentials already rotated; GitHub repo private; `core.hooksPath=.githooks`
- Do not touch primary checkout or the occupied ffmpeg branch

## Success Criteria

- [ ] Gitignore covers cookie-txt and `drive_key.json` classes
- [ ] Pre-commit blocks secret filenames and extra signatures; path-only; includes `.hermes/`
- [ ] Security tests scan beyond `*.py`; audit stays in-workspace and does not print matches
- [ ] Docs note residual history/ref risk; dirty tips retired or rebased; main history unchanged; no live needles
