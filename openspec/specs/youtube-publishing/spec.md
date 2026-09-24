# Specification: YouTube Publishing Resilience

## Capability Overview
The `youtube-publishing` capability handles direct video uploads and metadata publishing via either Playwright browser automation or YouTube Data API v3.

## Requirements

### Requirement 1: Preflight Cookie Session Validation in Playwright Uploader
Before launching Chromium or initiating browser automation, the uploader MUST validate cookie session health.

#### Scenario: Submitting video with expired cookies (Fail-Fast)
- **Given** an expired cookies file configured for a channel
- **When** `upload_video_via_playwright()` or `upload_video()` is called
- **Then** it MUST fail fast with a clear exception before launching the browser or touching the YouTube Studio page.

#### Scenario: Submitting video with Netscape format cookies (Happy Path)
- **Given** a valid Netscape format `cookies.txt` file
- **When** `upload_video_via_playwright()` is called
- **Then** it MUST seamlessly parse and format the cookies, load them into Playwright context, and proceed with publication.

### Requirement 2: Zero-API Upload Policy (Strict Cookie Session Publishing)
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
