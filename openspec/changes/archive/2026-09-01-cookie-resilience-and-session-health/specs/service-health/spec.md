# Specification: Service Health Diagnostics

## Capability Overview
The `service-health` capability provides operational status diagnostics for external authentication mechanisms (YouTube OAuth API tokens, Google Drive API / Service Accounts, and Playwright session cookies).

## Requirements

### Requirement 1: Deep Cookie Session Health Checks
The `check_cookies(channel)` health check MUST perform deep validation using the `cookie-management` layer instead of shallow JSON parsing.

#### Scenario: Channel with valid, unexpired cookies (Happy Path)
- **Given** a valid cookie file for a channel with active YouTube session tokens
- **When** `check_cookies(channel="moku")` is invoked
- **Then** it MUST return `{"ok": True, "detail": "Cookies OK (activas, N días restantes)"}`.

#### Scenario: Channel with expired cookies (Failure State)
- **Given** a cookie file whose session tokens have expired
- **When** `check_cookies(channel="moku")` is invoked
- **Then** it MUST return `{"ok": False, "detail": "Cookies expiradas: <filename>"}`.

#### Scenario: Channel with missing critical tokens (Failure State)
- **Given** a cookie file missing `LOGIN_INFO` or `SID`
- **When** `check_cookies(channel="moku")` is invoked
- **Then** it MUST return `{"ok": False, "detail": "Cookies incompletas (falta LOGIN_INFO)"}`.

#### Scenario: Channel with Netscape .txt cookies file (Happy Path)
- **Given** a channel configured with `secrets/cookies.txt` (Netscape format)
- **When** `check_cookies(channel="moku")` is invoked
- **Then** it MUST parse the Netscape format and report valid health status without JSON errors.
