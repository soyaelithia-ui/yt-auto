# Specification: Universal Cookie Management

## Capability Overview
The `cookie-management` capability provides a unified, resilient ingestion, normalization, and session verification layer for browser cookies in both JSON array and Netscape `cookies.txt` formats.

## Requirements

### Requirement 1: Universal Cookie Ingestion
The cookie parser MUST transparently detect and parse both JSON array formats and Netscape HTTP cookie file formats (`cookies.txt`).

#### Scenario: Parsing JSON array cookies file (Happy Path)
- **Given** a cookie file containing a JSON array of cookie objects
- **When** `parse_cookies_file(file_path)` is invoked
- **Then** it MUST parse the file and return a list of normalized cookie dictionaries containing `name`, `value`, `domain`, `path`, `secure`, `httpOnly`, `sameSite`, and `expires`.

#### Scenario: Parsing Netscape HTTP format cookies file (Happy Path)
- **Given** a standard Netscape/Curl `cookies.txt` file (tab-delimited, supporting `#` comments)
- **When** `parse_cookies_file(file_path)` is invoked
- **Then** it MUST parse the tab-separated records, ignoring comments and blank lines, and return normalized cookie dictionaries with appropriate booleans and expiration timestamps.

#### Scenario: Handling non-existent or empty files (Error State)
- **Given** a missing file path or a 0-byte file
- **When** `parse_cookies_file(file_path)` is invoked
- **Then** it MUST raise `FileNotFoundError` or `ValueError` with clear diagnostics.

---

### Requirement 2: Playwright Normalization
The module MUST format parsed cookies so they conform strictly to Playwright's `BrowserContext.add_cookies()` requirements.

#### Scenario: Normalizing domains, timestamps, and SameSite (Happy Path)
- **Given** raw cookie dictionaries with varied field names (`expirationDate` vs `expires`, lowercase `samesite`)
- **When** `format_cookies_for_playwright(cookies)` is invoked
- **Then** all domains without leading dots MUST be prefixed with `.`, timestamps MUST be converted to `float`, and `sameSite` MUST map to `"Strict"`, `"Lax"`, or `"None"`.

---

### Requirement 3: YouTube Session Token & Expiration Validation
The module MUST inspect cookie collections to evaluate session health, check for critical YouTube session tokens, and compute expiry status.

#### Scenario: Validating healthy session cookies (Happy Path)
- **Given** cookies containing `LOGIN_INFO`, `SID`, `__Secure-1PSID`, `__Secure-3PSID` with future expiration (> 48 hours)
- **When** `validate_youtube_session_cookies(cookies)` is invoked
- **Then** it MUST return `SessionHealthResult(status=SessionStatus.HEALTHY, min_expiry=..., missing_tokens=[], days_left=...)`.

#### Scenario: Detecting expired session cookies (Error State)
- **Given** cookies where key session tokens have expiration timestamps in the past
- **When** `validate_youtube_session_cookies(cookies)` is invoked
- **Then** it MUST return `SessionHealthResult(status=SessionStatus.EXPIRED, ...)` indicating expired session.

#### Scenario: Detecting missing essential session tokens (Error State)
- **Given** cookies missing `LOGIN_INFO` or `SID` / `__Secure-1PSID`
- **When** `validate_youtube_session_cookies(cookies)` is invoked
- **Then** it MUST return `SessionHealthResult(status=SessionStatus.INCOMPLETE, missing_tokens=["LOGIN_INFO", ...])`.
