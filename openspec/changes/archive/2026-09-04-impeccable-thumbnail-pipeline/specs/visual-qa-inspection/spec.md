# Delta for Visual QA Inspection

## ADDED Requirements

### Requirement: Automated Thumbnail Quality & Safe-Zone Inspection
The visual QA inspector MUST audit rendered thumbnail artifacts for valid aspect-ratio resolution, minimum file size, luminance dynamic range, and player safe-zone compliance.

#### Scenario: Valid horizontal 16:9 thumbnail passes QA (Happy Path)
- **GIVEN** a rendered 1920x1080 JPEG thumbnail exceeding 40 KB with high luminance contrast
- **WHEN** thumbnail audit is executed
- **THEN** the auditor MUST evaluate the check as passed with zero errors.

#### Scenario: Valid vertical 9:16 Shorts thumbnail passes QA (Happy Path)
- **GIVEN** a rendered 1080x1920 JPEG thumbnail exceeding 40 KB for a vertical Shorts lane
- **WHEN** thumbnail audit is executed
- **THEN** the auditor MUST recognize the 9:16 aspect ratio and evaluate the check as passed.

#### Scenario: Low contrast or blank thumbnail rejection (Edge Case)
- **GIVEN** a thumbnail with standard deviation of color channels < 18.0 or file size < 40 KB
- **WHEN** thumbnail audit is executed
- **THEN** the auditor MUST flag a QA violation and reject the thumbnail artifact.

#### Scenario: Safe-zone boundary violation rejection (Edge Case)
- **GIVEN** a thumbnail where primary text or badges penetrate the YouTube timestamp boundary
- **WHEN** thumbnail audit is executed
- **THEN** the auditor MUST flag a safe-zone violation in the inspection report.
