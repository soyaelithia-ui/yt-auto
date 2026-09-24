# Specification: YouTube Publishing Resilience (Delta)

## MODIFIED Requirements

### Requirement: Zero-API Upload Policy (Strict Cookie Session Publishing)
Video publishing to YouTube MUST strictly and exclusively utilize browser session cookies (via InnerTube HTTP or Playwright in `src/youtube/`). YouTube Data API v3 MUST NEVER be used to upload video binaries.

1. **Upload Method Restriction**:
   - `upload_video()` MUST prioritize and enforce cookie-based session publishing (`INNERTUBE` / `PLAYWRIGHT`).
   - Any attempt to use YouTube Data API v3 for uploading videos MUST be rejected or disabled.
2. **API Quota Preservation**:
   - YouTube Data API v3 quota is reserved exclusively for:
     a) Telemetry, metadata retrieval, and view/engagement analytics (`videos.list`).
     b) Atomic video deletion during catalog pruning (`videos.delete`).

#### Scenario: Production video upload executes via session cookies
- **Given** a rendered video ready for publication
- **When** `upload_video()` is invoked
- **Then** the publication MUST execute using session cookies (InnerTube / Playwright)
- **And** no YouTube Data API `videos().insert()` request SHALL be dispatched.

#### Scenario: Refusal of API upload flow in production
- **Given** an upload invocation where cookies are missing or invalid
- **When** upload routing is evaluated
- **Then** the system MUST fail fast or mark the job `WAITING_LLM_QUOTA` / `WAITING_YOUTUBE_LIMIT` without falling back to `videos().insert()`.
