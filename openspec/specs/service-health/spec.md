# Specification: Service Health Diagnostics

## Capability Overview
The `service-health` capability provides operational status diagnostics for external authentication mechanisms (YouTube OAuth API tokens, Google Drive API / Service Accounts, and Playwright session cookies).

## Requirements

### Requirement: Deep Cookie Session Health Checks
(Reason: Extends check_cookies to emit structured operational incidents into system_events)

The `check_cookies(channel)` health check MUST perform deep validation using the `cookie-management` layer (`validate_youtube_session_cookies`) and MUST emit structured operational incident events into `system_events` when cookies are decayed or expiring soon, subject to a stateful 1-hour deduplication window per channel.

1. When `check_cookies(channel)` evaluates a channel's session cookies:
   - If session status is `SessionStatus.EXPIRED`, `SessionStatus.INCOMPLETE`, or `SessionStatus.INVALID`, the check MUST return `{"ok": False, "detail": ...}` AND MUST emit a `cookie_failure` event to `system_events` with level `'ERROR'`.
   - If session status is `SessionStatus.EXPIRING_SOON` (< 48 hours remaining), the check MUST return `{"ok": True, "detail": ...}` AND MUST emit a `cookie_warning` event to `system_events` with level `'WARNING'`.
   - If session status is `SessionStatus.HEALTHY`, the check MUST return `{"ok": True, "detail": ...}` without emitting failure or warning incidents.
2. The health check MUST accept canonical channel identifiers (`"horror"`, `"drama"`, `"scifi"`) as well as backward-compatible aliases.
3. Incident emission MUST be non-blocking and isolated in `try/except` guards so database write issues never fail the diagnostic return.

#### Scenario: Channel with valid, unexpired cookies (Happy Path)
- **Given** a valid cookie file for a channel with active YouTube session tokens (> 48 hours remaining)
- **When** `check_cookies(channel="horror")` is invoked
- **Then** it MUST return `{"ok": True, "detail": "Cookies OK (activas, N días restantes)"}`
- **And** zero incident events SHALL be emitted to `system_events`.

#### Scenario: Channel with expired cookies emits cookie_failure event (Failure State)
- **Given** a cookie file whose session tokens have expired
- **When** `check_cookies(channel="horror")` is invoked
- **Then** it MUST return `{"ok": False, "detail": "Cookies expiradas: <filename>"}`
- **And** an event with `event_type = 'cookie_failure'` and `level = 'ERROR'` MUST be emitted into `system_events`
- **And** `channel` MUST equal `"horror"`.

#### Scenario: Channel with missing critical tokens emits cookie_failure event (Failure State)
- **Given** a cookie file missing `LOGIN_INFO` or `SID`
- **When** `check_cookies(channel="horror")` is invoked
- **Then** it MUST return `{"ok": False, "detail": "Cookies incompletas (falta LOGIN_INFO)"}`
- **And** an event with `event_type = 'cookie_failure'` and `level = 'ERROR'` MUST be emitted into `system_events`.

#### Scenario: Channel with cookies expiring within 48 hours emits cookie_warning (Warning State)
- **Given** a cookie file whose session tokens have 32 hours remaining before expiration
- **When** `check_cookies(channel="horror")` is invoked
- **Then** it MUST return `{"ok": True, "detail": "Cookies por expirar (restan 32.0 horas)"}`
- **And** an event with `event_type = 'cookie_warning'` and `level = 'WARNING'` MUST be emitted into `system_events`.

#### Scenario: Channel with Netscape .txt cookies file (Happy Path)
- **Given** a channel configured with `secrets/cookies.txt` (Netscape format)
- **When** `check_cookies(channel="horror")` is invoked
- **Then** it MUST parse the Netscape format and report valid health status without JSON errors.

---

### Requirement: Stateful 1-Hour Deduplication for Cookie Incidents
The operational health emission subsystem MUST enforce a 1-hour deduplication window per channel for cookie incidents to avoid log pollution from frequent background polling.

1. When a `cookie_failure` or `cookie_warning` condition is detected:
   - The system MUST inspect the most recent incident emitted for the same `channel` and `event_type`.
   - If an incident with the identical `event_type` was emitted $< 3,600\text{ seconds}$ (1 hour) ago, the duplicate emission SHALL be suppressed.
   - If the session status transitions between states (e.g. from `EXPIRING_SOON` to `EXPIRED`, or from `EXPIRED` back to `HEALTHY`), the deduplication suppression MUST be bypassed, immediately emitting the new event.

#### Scenario: Frequent health checks suppress duplicate cookie incidents within 1 hour
- **Given** a channel with expired cookies for which a `cookie_failure` event was emitted at $T = 0$
- **When** `check_cookies` is invoked again at $T = 5\text{ minutes}$ and $T = 30\text{ minutes}$
- **Then** `check_cookies` MUST return `{"ok": False, ...}` on each invocation
- **But** zero additional `cookie_failure` rows SHALL be inserted into `system_events`.

#### Scenario: Status transition bypasses deduplication window immediately
- **Given** a channel with expiring cookies whose initial `cookie_warning` was emitted at $T = 0$
- **When** at $T = 20\text{ minutes}$ the session tokens expire completely
- **And** `check_cookies` is invoked
- **Then** a `cookie_failure` event MUST be emitted immediately to `system_events` without waiting for the 1-hour window to elapse.
