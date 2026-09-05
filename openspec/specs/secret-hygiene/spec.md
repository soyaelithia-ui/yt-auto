# Secret Hygiene Specification

## Purpose

Workspace-confined scanners, hooks, gitignore, and tests block secret-shaped filenames and production-format signatures without live needles, reporting paths only.

## Requirements

### Requirement: Gitignore Secret Filename Classes

Gitignore MUST ignore `cookies.txt`, `*cookies*.txt`, and `drive_key.json` classes outside `secrets/`.

#### Scenario: Cookie-txt class ignored outside secrets

- GIVEN a `cookies.txt` or `*cookies*.txt` path outside `secrets/`
- WHEN gitignore is evaluated
- THEN the path MUST be ignored

#### Scenario: Drive key class ignored outside secrets

- GIVEN `drive_key.json` outside `secrets/`
- WHEN gitignore is evaluated
- THEN the path MUST be ignored

### Requirement: Pre-commit Filename Signature And Path-Only Reports

Pre-commit MUST reject staged secret-shaped filenames, `.hermes/` paths, and extra production-format signatures. Failure output MUST be path-only.

#### Scenario: Secret filename or extra signature blocked

- GIVEN a staged `.env`, `cookies.json`, `secrets/` path, PEM, long `ya29.`, AKIA, or service-account JSON match
- WHEN pre-commit runs
- THEN the commit MUST be rejected
- AND the report MUST include the path

#### Scenario: Hermes home blocked without printing matches

- GIVEN a staged `.hermes/` path or a signature match
- WHEN pre-commit reports failure
- THEN `.hermes/` MUST be blocked
- AND the report MUST NOT print matched secret values

### Requirement: Security Tests Scan Beyond Python

Security tests MUST scan tracked text beyond `*.py` and MUST require `.cursor/` and `.hermes/` in gitignore.

#### Scenario: Non-Python tracked text is scanned

- GIVEN tracked non-Python text matching a production-format signature
- WHEN security policy tests run
- THEN the tests MUST fail

#### Scenario: Agent homes required in gitignore

- GIVEN `.gitignore`
- WHEN security policy tests assert agent-home rules
- THEN `.cursor/` and `.hermes/` MUST be required

### Requirement: Workspace-Confined Audit Without Match Printing

The security audit MUST stay inside the workspace and MUST NOT print matched secret values.

#### Scenario: Audit stays inside the workspace

- GIVEN the security audit
- WHEN it runs
- THEN it MUST NOT walk hardcoded paths outside the workspace

#### Scenario: Audit reports paths not matches

- GIVEN an in-workspace file matching a production-format signature
- WHEN the audit reports findings
- THEN it MUST identify the path
- AND it MUST NOT print the matched text

### Requirement: No Live Needles

Hooks, audit, and tests MUST use generic format signatures or synthetic tokens and MUST NOT embed live credentials as needles.

#### Scenario: Generic signatures only

- GIVEN hooks, audit, and security tests
- WHEN their pattern sources are inspected
- THEN they MUST NOT contain live credential literals

#### Scenario: Synthetic fixtures allowed

- GIVEN tests that need token-shaped input
- WHEN they construct samples
- THEN they MUST use synthetic or placeholder values
- AND they MUST NOT copy live secrets

### Requirement: Residual History Risk Documentation

Security docs SHOULD record residual history and ref risk. This change MUST NOT require history rewrite.

#### Scenario: Docs mention residual history risk

- GIVEN `SECURITY.md`, `AGENTS.md`, and `docs/CONFIGURACION_SECRETOS.md`
- WHEN they are read
- THEN they SHOULD state that rotated literals MAY remain in git objects and stale refs

#### Scenario: History rewrite remains out of scope

- GIVEN this change
- WHEN apply or verify is evaluated
- THEN history rewrite MUST NOT be required
- AND main history MUST remain intact

### Requirement: Dirty Pre-#30 Tip Retirement

Dirty pre-#30 tips SHOULD be retired or rebased onto sanitized main. Apply MUST NOT delete remotes unless an operator SHA list is recorded for rollback.

#### Scenario: Optional retirement with recorded SHAs

- GIVEN an operator-provided SHA list of dirty tips
- WHEN those tips are retired or rebased onto sanitized main
- THEN the listed tips SHOULD no longer be live dirty refs

#### Scenario: No SHA list means no remote deletion

- GIVEN no operator-provided SHA list
- WHEN apply runs
- THEN remote branches MUST NOT be deleted
- AND main history MUST NOT be rewritten
