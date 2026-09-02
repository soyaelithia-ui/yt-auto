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

---

## 2. Automated Security Verification

The test suite enforces credential hygiene automatically:
- Automated tests verify that `.gitignore` contains all necessary secret patterns.
- Automated tests scan tracked files to ensure no real API keys, OAuth secrets, or raw credential paths are committed.
- Preflight commands (`python main.py run --preflight`) validate required environment variables before production runs.

---

## 3. Reporting a Vulnerability

If you discover a security vulnerability or accidental credential exposure in `yt-auto`:

1. **Do NOT open a public GitHub issue.**
2. Report the vulnerability privately to the project maintainers via email or private security advisory on GitHub.
3. Include:
   - Description of the vulnerability.
   - Steps to reproduce or proof of concept.
   - Affected files and components.
4. If real credentials were inadvertently exposed, rotate the affected API keys and OAuth client secrets immediately in the Google Cloud Console / Telegram BotFather before reporting.
