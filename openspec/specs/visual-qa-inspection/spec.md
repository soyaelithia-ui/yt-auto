# Specification: Visual QA Inspection

## Capability Overview
The `visual-qa-inspection` capability provides automated post-render verification of generated video media, extracting canonical keyframes and detecting visual anomalies including black screen segments and frozen video frames via FFmpeg analysis filters.

## Requirements

### Requirement 1: Canonical 5-Point Keyframe Extraction
The visual QA inspector MUST extract exactly 5 PNG keyframe images at deterministic temporal intervals (10%, 30%, 50%, 70%, 90% of duration) from the rendered video into a designated output directory.

#### Scenario: Keyframe extraction from rendered video (Happy Path)
- **Given** a valid 60-second MP4 video file at 1080x1920 resolution
- **When** keyframe extraction is executed
- **Then** the system MUST extract 5 distinct PNG images at timestamps 6.0s, 18.0s, 30.0s, 42.0s, and 54.0s
- **And** all 5 extracted PNG files MUST exist on disk with 1080x1920 resolution.

#### Scenario: Keyframe extraction from ultra-short video (Edge Case)
- **Given** a valid short video file with a duration of 0.8 seconds
- **When** keyframe extraction is executed
- **Then** the system MUST calculate non-colliding fractional timestamps within [0.0s, 0.8s]
- **And** the system MUST write 5 valid PNG keyframes without out-of-bounds seeking errors.

### Requirement 2: Black Screen Artifact Detection
The visual QA inspector MUST evaluate video streams with the FFmpeg `blackdetect` filter and flag any continuous black segment lasting $d \ge 0.5\text{ seconds}$ ($pic\_th \ge 0.98$, $pix\_th \le 0.10$).

#### Scenario: Video with no black screen artifacts (Happy Path)
- **Given** a rendered video containing active visuals with zero black segments $\ge 0.5\text{s}$
- **When** black screen detection is executed
- **Then** the detector MUST return an empty list of black intervals and indicate check pass.

#### Scenario: Video containing a 1.2-second black screen anomaly (Edge Case)
- **Given** a rendered video containing an unrendered black sequence from $t=14.0\text{s}$ to $t=15.2\text{s}$
- **When** black screen detection is executed
- **Then** the detector MUST flag a QA violation with start time 14.0s, end time 15.2s, and duration 1.2s
- **And** the overall QA status MUST evaluate to failed.

### Requirement 3: Freeze Frame Artifact Detection
The visual QA inspector MUST evaluate video streams with the FFmpeg `freezedetect` filter and flag any frozen static sequence lasting $d \ge 2.0\text{ seconds}$.

#### Scenario: Active dynamic video passes freeze detection (Happy Path)
- **Given** a rendered video with continuous motion and scene transitions
- **When** freeze frame detection is executed with threshold $d=2.0\text{s}$
- **Then** the detector MUST detect zero freeze intervals and mark the freeze check as passed.

#### Scenario: Pipeline visual stall produces 3.5-second freeze (Edge Case)
- **Given** a rendered video where the visual stream stalls from $t=20.0\text{s}$ to $t=23.5\text{s}$ while audio continues
- **When** freeze frame detection is executed
- **Then** the detector MUST capture a freeze interval starting at 20.0s with duration 3.5s
- **And** the inspection report MUST record a high-severity defect.

### Requirement 4: Aggregated QA Inspection Reporting
The visual QA inspector MUST produce a structured JSON report containing keyframe paths, detection findings, duration, resolution, and overall verdict.

#### Scenario: Aggregation of clean inspection run (Happy Path)
- **Given** a video that passes both blackdetect and freezedetect filters with 5 valid keyframes
- **When** report compilation executes
- **Then** the report MUST set `overall_pass: true` and include file paths to all 5 keyframes.

#### Scenario: Inspection of unreadable or corrupted video file (Edge Case)
- **Given** a corrupted 0-byte or unreadable MP4 file
- **When** visual QA inspection is invoked
- **Then** the inspector MUST raise or catch `FFprobeError` / `FFmpegExecutionError`
- **And** the inspection report MUST set `overall_pass: false` with detailed error telemetry.
