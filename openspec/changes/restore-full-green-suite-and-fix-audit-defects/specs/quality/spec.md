# Delta Spec: Audit Remediation & Test Stability

## MODIFIED Requirements

### Requirement: Service Supervisor Concurrency Guard
`deploy/ctl.sh` MUST detect Docker Compose v2 container names matching `yt-automation` with any standard prefix or suffix delimiter (`_` or `-`).

#### Scenario: Compose v2 container running
- GIVEN a running Docker container named `yt-auto-yt-automation-1`
- WHEN `deploy/ctl.sh start` is executed without `YT_FORCE_HOST=1`
- THEN the script MUST abort with an error code and refuse host service startup.

### Requirement: Playwright Uploader Error Capture Safety
`upload_video_via_playwright` MUST safely handle `screenshot_dir` when `None`, never creating paths formatted as `"None/..."`.

#### Scenario: Upload failure with default screenshot directory
- GIVEN `screenshot_dir=None`
- WHEN an exception occurs during the upload workflow
- THEN no invalid directory error is raised and error handling completes cleanly.

### Requirement: Channel Ownership Validation
`src/youtube/control.py` MUST verify that any video targeted for deletion belongs to the configured channel before executing the deletion call.

#### Scenario: Deletion with matching ownership
- GIVEN a video belonging to `UC_expected`
- WHEN `delete_video` or `_verify_ownership` is invoked with canonical channel matching `UC_expected`
- THEN ownership is confirmed and deletion proceeds.

### Requirement: Full Repository Anti-Regression Green Pass
The full repository test suite (`pytest`) MUST pass with 0 failures on `main`.

#### Scenario: Full test execution
- GIVEN standard repository test configuration
- WHEN `pytest` executes without filter flags
- THEN all tests pass or xfail/skip as explicitly marked; zero tests fail.
