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
