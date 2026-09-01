# Spec: Operational and YouTube Publishing Policy

## Requirement: Zero-Quota Direct Session Publication
Video publishing in automated production MUST use direct authenticated session contexts (Playwright with decrypted Netscape/JSON cookies or InnerTube) as the primary channel to avoid exhausting YouTube Data API v3 daily upload quotas (10,000 units / ~6 uploads limit).

### Scenario: Direct Session Video Publication
- **Given** a rendered and approved video artifact
- **When** the upload stage is triggered
- **Then** `SessionUploader` MUST authenticate using valid session cookies (`LOGIN_INFO`, `SAPISID`, `__Secure-3PSID`)
- **And** the video MUST be published without consuming YouTube Data API v3 quota units.

## Requirement: Proactive Session Health Validation
Before claiming a job or initiating video rendering, the pipeline MUST inspect session cookies via `SessionHealthValidator`. If session cookies have expired or remain valid for less than 48 hours, the system MUST flag `EXPIRING_SOON` or `EXPIRED`, notify the operator via Telegram `/health`, and halt upload progression safely.

### Scenario: Expiring Session Preflight Detection
- **Given** a channel with session cookies expiring in 36 hours
- **When** `SessionHealthValidator.validate_channel(channel)` is invoked
- **Then** the result status MUST be `EXPIRING_SOON`
- **And** a warning MUST be logged and dispatched to Telegram operators prior to job claiming.

## Requirement: Telegram Human-in-the-Loop Review
Every production deliverable MUST be dispatched to the Telegram Review Bot (`review/telegram_bot.py`) with zero-copy local file transport (`file:///`) or proxy streaming, providing interactive 2x2 inline keyboards (`✅ Publicar`, `❌ Rechazar`, `🔄 Rehacer`, `ℹ️ Ver Detalles`). Automatic publication MUST only proceed upon explicit operator approval or scheduled auto-publish sweep timers.

### Scenario: Interactive Operator Approval
- **Given** a deliverable registered in `review_state.db` under `WAITING_REVIEW`
- **When** the operator taps `✅ Publicar`
- **Then** the bot MUST trigger atomic 2PC publication reconciliation and upload the video to YouTube.
