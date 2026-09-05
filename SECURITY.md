# Security Policy

## Supported Versions

Only the latest version on the canonical repository (`main` branch) is actively maintained with security updates.

| Version | Supported          |
| ------- | ------------------ |
| 3.1.x   | :white_check_mark: |
| < 3.1   | :x:                |

---

## 1. Zero-Secret Hardcoding Policy (Mandatory)

To prevent credential leaks and unauthorized access, the following rules are strictly enforced across the codebase:

1. **No Hardcoded Credentials**: API keys, OAuth client secrets, refresh tokens, private keys, service account JSON files, session cookies, and passwords MUST NEVER be committed to the repository or hardcoded as inline constants in code.
2. **Environment Variable & Secret Directory Isolation**:
   - Local environments MUST store secrets exclusively in `.env` with restrictive permissions (`chmod 600 .env`).
   - Containerized and VPS deployments MUST mount secrets in `/run/secrets/` as read-only volumes.
   - The `.env` file and `secrets/` directory MUST remain strictly listed in `.gitignore`.
3. **Safe Example Templates**:
   - Only `.env.example` may be tracked in git, and it MUST contain empty placeholders (`KEY=`) with zero real production values.
4. **Data Sanitization & Telemetry Hygiene**:
   - Dict representations intended for public logging, Telegram messages, or CLI output (such as `ChannelSettings.public_dict()`) MUST NOT expose filesystem paths to secret files or raw credential payloads. Only boolean availability flags are permitted.
   - Loggers and health reporters MUST never log raw cookie values, session tokens, or OAuth authorization codes.
    5. **Session Memory Scrubbing**:
       - Automated browser sessions (Playwright / Chromium) MUST explicitly clear session cookies from context (`context.clear_cookies()`) and terminate child processes cleanly on teardown to avoid lingering in-memory secrets.
    6. **No Live Literals in Tests or Audits**:
       - Tests, fixtures, mocks, and audit scripts MUST NEVER embed real credentials, even as "forbidden string" matchers.
       - Scan with generic format signatures (for example Google API key / OAuth client-secret shapes) or runtime-built synthetic tokens. Assertion messages MUST NOT print matched secret values.
    7. **Agent Homedirs Are Local-Only**:
       - `.codex/`, `.claude/`, `.gemini/`, `.agents/`, `.opencode/`, `.cursor/`, `.hermes/`, `.copilot/`, `.grok/`, and `.atl/` MUST remain gitignored and untracked, including hooks and session files.
    8. **Residual History / Ref Risk**:
       - Rotated literals MAY remain in git objects and stale refs. History rewrite is not required. Scanners and hooks apply to HEAD and new content; main history stays intact.

---

## 2. Automated Security Verification

The test suite and pre-commit hook enforce credential hygiene automatically:
- Automated tests verify that `.gitignore` contains secret patterns and agent-homedir rules.
- Automated tests scan tracked Python trees so production-format keys, OAuth secrets, bot tokens, and GitHub PATs are not committed.
- The pre-commit hook rejects staged agent homedirs and production-format secret signatures, reporting **file paths only** (never the match).
- Preflight commands (`python main.py run --preflight`) validate required environment variables before production runs.

---

## 3. Incident Response (Credential Leak)

If live credentials appear in git history, logs, or a public clone:

1. **Do NOT open a public GitHub issue.**
2. Make the canonical GitHub repository **private** immediately.
3. Invalidate the leaked Google credentials: delete or shut down the affected GCP project, or disable the consumer APIs and rotate keys/OAuth clients. Revoke Telegram bot tokens in BotFather.
4. Rotate every credential that may have been copied (API keys, OAuth client secret, refresh tokens, cookies, GitHub tokens).
5. Remove literals from `HEAD` using generic scanners. History rewrite is optional and does not un-leak existing clones.
6. Keep the repository private. Do not re-publish until new credentials exist and scanners are green.

---

## 4. Reporting a Vulnerability

If you discover a security vulnerability or accidental credential exposure in `yt-auto`:

1. **Do NOT open a public GitHub issue.**
2. Report the vulnerability privately to the project maintainers via email or private security advisory on GitHub.
3. Include:
   - Description of the vulnerability.
   - Steps to reproduce or proof of concept.
   - Affected files and components.
4. Follow **Incident Response** above before treating the report as closed.
