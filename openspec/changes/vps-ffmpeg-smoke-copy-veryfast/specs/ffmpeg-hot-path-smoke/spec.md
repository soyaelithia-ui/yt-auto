# ffmpeg-hot-path-smoke Specification

## Purpose
Gate follow-up look changes on live evidence that production FFmpeg uses stream-copy on the cheap path and `veryfast` + CRF 21 on unavoidable re-encodes.

## Requirements

### Requirement: Live argv evidence is mandatory

The smoke MUST inspect FFmpeg argument vectors from a production-like encode (VPS or captured production stderr). The smoke MUST NOT treat unit tests or source literals as sufficient evidence. If argv cannot be recovered, the smoke MUST fail.

#### Scenario: Stderr yields argv (Happy Path)

- **Given** production compose streams FFmpeg stderr
- **When** the smoke runs against that capture
- **Then** it MUST recover at least one FFmpeg argv
- **And** it MUST record pass/fail against the copy and re-encode rules below

#### Scenario: Missing argv (Error)

- **Given** no FFmpeg argv in the capture
- **When** the smoke runs
- **Then** it MUST fail
- **And** it MUST NOT mark copy or re-encode as observed

### Requirement: Cheap path MUST stream-copy

When the encode is beats, or director assembly without HUD and with homogeneous loops, FFmpeg MUST use video stream-copy (`-c:v copy`). The smoke MUST pass this check from live argv. The smoke MUST NOT require a director job when production lanes are beats-only.

#### Scenario: Beats encode copies video (Happy Path)

- **Given** a beats-lane production encode with recovered argv
- **When** the smoke evaluates the video codec flags
- **Then** the argv MUST include `-c:v copy` (or equivalent stream-copy)
- **And** it MUST NOT show a full-frame libx264 re-encode of that cheap path

#### Scenario: Beats-only fleet (Edge Case)

- **Given** production lanes all use the beats visual pipeline
- **When** the smoke finds a beats copy argv and no director job
- **Then** the copy check MUST pass
- **And** the smoke MUST NOT fail solely because director single-pass was not exercised

### Requirement: Unavoidable re-encode MUST use veryfast and CRF 21

If live argv shows a video re-encode, that encode MUST use preset `veryfast` and CRF 21. If no re-encode appears, the smoke MUST record `no re-encode observed` and MUST NOT fail for missing veryfast.

#### Scenario: Re-encode matches defaults (Happy Path)

- **Given** argv for a video re-encode (HUD burn or geometry mismatch)
- **When** the smoke evaluates preset and CRF
- **Then** preset MUST be `veryfast`
- **And** CRF MUST be `21`

#### Scenario: No re-encode in capture (Edge Case)

- **Given** recovered argv with only stream-copy video
- **When** the smoke looks for a re-encode sample
- **Then** it MUST record `no re-encode observed`
- **And** it MUST still pass if the copy check passed

#### Scenario: Wrong preset or CRF (Error)

- **Given** a video re-encode argv with preset `slow` or `ultrafast`, or CRF other than 21
- **When** the smoke evaluates that argv
- **Then** it MUST fail

### Requirement: Fail-closed follow-up gate

A failed smoke MUST block opening follow-up look changes (`planner-hud-layout-channel-accent`, `parametric-generic-thumbnail`). A passing smoke MAY allow those changes. This capability MUST NOT modify `compositor`, `proc_engine`, or `pipeline` modules.

#### Scenario: Failed smoke blocks look work (Error)

- **Given** the smoke failed (missing argv, missing copy, or bad re-encode knobs)
- **When** a follow-up look change is requested
- **Then** that work MUST NOT start

#### Scenario: Pass does not retouch hot path (Happy Path)

- **Given** the smoke passed
- **When** evidence is recorded
- **Then** compositor, proc_engine, and pipeline sources MUST remain unmodified by this change
