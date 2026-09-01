# Proposal: YouTube Cookie Resilience & Session Health Inspection

## Intent
Eliminate cookie-related publication failures and false-positive health checks in `yt-auto` by implementing a universal hybrid cookie parser (supporting both JSON array and Netscape `cookies.txt` formats), introducing deep session health validation (detecting expiration dates and essential Google/YouTube session tokens), and enhancing Playwright browser session resilience.

## Scope

### In Scope
- **Universal Hybrid Cookie Parser**:
  - Implement a dedicated parser module (`src/core/cookies.py`) that auto-detects and seamlessly parses both JSON arrays and Netscape HTTP cookie file formats (`cookies.txt`).
  - Normalize cookies into Playwright-ready format (`name`, `value`, `domain`, `path`, `secure`, `httpOnly`, `sameSite`, `expires`).
- **Deep Session Health Check**:
  - Enhance `src/api_health.py` (`check_cookies`) to verify not only file existence and JSON structure, but also:
    - Presence of essential YouTube session identifiers (`LOGIN_INFO`, `SID`, `__Secure-1PSID`, `__Secure-3PSID`, `SSID`, `HSID`, `SAPISID`).
    - Expiration timestamps, providing clear diagnostics: active, expiring soon (< 48h), or expired.
- **Playwright Upload Resilience**:
  - Integrate the universal cookie parser into `src/youtube/uploader.py`.
  - Support persistent user data directory (`user_data_dir`) options to maintain browser session context and reduce Google 2FA/anti-bot challenge triggers.
- **Test Infrastructure**:
  - Add comprehensive unit tests in `tests/unit/test_cookies.py` and update `tests/unit/test_api_health.py` and `tests/unit/test_youtube_uploader.py`.

### Out of Scope
- Committing real credentials, cookies, or secrets to the repository.
- Changes to video generation, audio DSP, or LLM script pipelines.
- Automating bypass of Google 2FA or CAPTCHAs beyond standard session preservation best practices.

## Capabilities

### New Capabilities
- `cookie-management`: Universal parsing (JSON + Netscape), normalization, and deep session expiration/integrity validation.

### Modified Capabilities
- `service-health`: Extended `check_cookies` with deep inspection (session token verification + time-to-expiry diagnostics).
- `youtube-publishing`: Refactored cookie loading in Playwright uploader to use the centralized, resilient parser.

## Approach
1. **Core Cookie Module (`src/core/cookies.py`)**:
   - Provide `parse_cookies_file(file_path)` supporting both JSON and Netscape formats.
   - Provide `validate_youtube_session_cookies(cookies)` returning detailed diagnostics: status (`HEALTHY`, `EXPIRING_SOON`, `EXPIRED`, `INCOMPLETE`, `INVALID`), minimum expiration epoch, and missing critical cookie names.
   - Provide `format_cookies_for_playwright(cookies)` returning normalized dicts ready for `context.add_cookies()`.
2. **Health Check Integration (`src/api_health.py`)**:
   - Update `check_cookies(channel)` to call `src.core.cookies` and report precise status (e.g. `Cookies OK (válidas por 14 días)` or `Cookies expiradas` or `Faltan cookies de sesión: LOGIN_INFO`).
3. **Uploader Integration (`src/youtube/uploader.py`)**:
   - Replace manual `json.load()` in `upload_video_via_playwright` with `parse_cookies_file()`.
   - Validate session health before launching Chromium to fail fast with clear diagnostic messages if cookies are expired.
4. **Channel Settings & Registry Consistency**:
   - Ensure channel configs (`config/channels/*.json`) and settings can point to either `.json` or `.txt` paths without error.

## Affected Areas
| Area | Impact | Description |
|------|--------|-------------|
| `src/core/cookies.py` | NEW | Universal cookie parser, normalizer, and session health validator |
| `src/api_health.py` | MEDIUM | Upgraded `check_cookies` with deep token inspection and expiration checks |
| `src/youtube/uploader.py` | MEDIUM | Use universal parser and preflight session health verification |
| `src/config.py` | LOW | Ensure transparent path handling for cookie files |
| `tests/unit/test_cookies.py` | NEW | Unit tests for Netscape/JSON parsing and expiration checks |
| `tests/unit/test_api_health.py` | MEDIUM | Updated tests for deep cookie health validation |

## Risks
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Incomplete Netscape format exported by custom browser extensions | Low | Robust regex/line-splitting parser with fallback line ignoring and comment handling |
| Timezone discrepancy when calculating cookie expiration | Low | Compare timestamps using UTC standard epoch floats (`time.time()`) |
| Breaking existing test suites expecting raw json errors | Low | Preserve backward-compatible exceptions while extending capability |

## Rollback Plan
1. Revert Git commits associated with `cookie-resilience-and-session-health`.
2. Existing JSON cookie files remain 100% compatible.

## Success Criteria
- [ ] Both JSON array and Netscape `.txt` cookie files are correctly parsed and normalized for Playwright.
- [ ] Expired cookies or missing session tokens (`LOGIN_INFO`, `SID`, etc.) are detected proactively with clear error messages.
- [ ] `api_health.check_cookies()` displays detailed health and validity window (e.g. days remaining) without leaking secrets.
- [ ] All unit and integration tests pass with 0 regressions.
