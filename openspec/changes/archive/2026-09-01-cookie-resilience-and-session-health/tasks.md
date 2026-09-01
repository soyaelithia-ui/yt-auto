# Tasks: YouTube Cookie Resilience & Deep Session Health

## Review Workload Forecast
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Low

## Phase 1: Core Universal Cookie Module (TDD RED -> GREEN)
- [x] 1.1 [TDD-RED] Create unit test suite `tests/unit/test_cookies.py`:
  - Test parsing JSON array cookies.
  - Test parsing Netscape `cookies.txt` format with comments and whitespace.
  - Test Playwright formatting/normalization (domains, timestamps, sameSite).
  - Test session token validation (HEALTHY, EXPIRING_SOON, EXPIRED, INCOMPLETE, INVALID).
  - Test error handling for missing/empty/corrupt files.
- [x] 1.2 [TDD-GREEN] Implement `src/core/cookies.py`:
  - Data classes / Enums: `SessionStatus`, `SessionHealthResult`.
  - Functions: `parse_cookies_file()`, `format_cookies_for_playwright()`, `validate_youtube_session_cookies()`.
- [x] 1.3 Verify `pytest tests/unit/test_cookies.py` passes (100% GREEN).

## Phase 2: Deep Health Check Integration (TDD RED -> GREEN)
- [x] 2.1 [TDD-RED] Update `tests/unit/test_api_health.py`:
  - Test `check_cookies` with active JSON cookies (reports OK with days left).
  - Test `check_cookies` with active Netscape `cookies.txt` (reports OK without JSON error).
  - Test `check_cookies` with expired cookies (reports failure with expired detail).
  - Test `check_cookies` with missing session tokens (reports failure with missing tokens).
- [x] 2.2 [TDD-GREEN] Update `src/api_health.py` `check_cookies()` to use `src.core.cookies`:
  - Call `parse_cookies_file()` and `validate_youtube_session_cookies()`.
  - Format output safely without exposing secrets.
- [x] 2.3 Verify `pytest tests/unit/test_api_health.py` passes (100% GREEN).

## Phase 3: Playwright Uploader Integration (TDD RED -> GREEN)
- [x] 3.1 Update `src/youtube/uploader.py`:
  - Use `parse_cookies_file()` instead of raw `json.load()`.
  - Add preflight cookie session check to fail fast if expired.
- [x] 3.2 Update `tests/unit/test_youtube_uploader.py` and run offline uploader tests.

## Phase 4: Full Regression Verification
- [x] 4.1 Run full unit test suite (`pytest tests/unit`) to ensure 0 regressions.
- [x] 4.2 Validate `check_cookies` report formatting via CLI/status helper.
