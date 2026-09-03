# Delta for Adaptive Narrative Curation

## MODIFIED Requirements

### Requirement: Semantic Scene Segmentation, Storyboard Montage, and Timing Bounds

The narrative curator MUST segment full narration scripts into discrete semantic scene acts based on narrative storyboarding rather than fixed arithmetic intervals. For vertical Shorts, each scene duration MUST satisfy 8.0s <= duration <= 15.0s (3 to 5 scenes). For longform productions (10–15 minutes), the curator MUST define between 5 and 8 semantic story scenes (60.0s <= duration <= 150.0s) corresponding to major plot milestones, each specifying narrative location, dramatic objective, and scene transition reason. Scene cuts MUST occur strictly at sentence or paragraph boundaries and MUST NOT split sentences mid-clause.

#### Scenario: Semantic segmentation of vertical Short narration (Happy Path)
- **Given** a voiceover script containing 120 words configured for vertical format at 160 WPM (~45 seconds total)
- **When** semantic scene segmentation is executed
- **Then** the curator MUST produce between 3 and 5 sequential scene contracts
- **And** every individual scene contract MUST have a calculated duration between 8.0s and 15.0s
- **And** the sum of scene durations MUST equal the total narration duration within +- 0.5s.

#### Scenario: Short residual clause boundary handling (Edge Case)
- **Given** a closing loop connector phrase containing only 4 words (~1.5s speech) at the end of a script
- **When** scene segmentation executes
- **Then** the curator MUST merge the short phrase with the preceding scene rather than creating a sub-8.0s orphan scene
- **And** the resulting merged scene duration MUST NOT exceed the 15.0s ceiling.

#### Scenario: Longform storyboard montage structure compilation (Happy Path)
- **Given** a 12-minute longform narrative script
- **When** the curator compiles the narrative storyboard
- **Then** the curator MUST produce between 5 and 8 sequential scene acts
- **And** each scene act MUST have an assigned duration between 60.0s and 150.0s
- **And** each scene act MUST declare an explicit transition reason and setting archetype.

## ADDED Requirements

### Requirement: Longform Narrative Word Budget and Minimum Duration Gate

Longform narrative generation templates MUST provide at least 2,800 words across structured dramatic beats to ensure speech synthesis reliably reaches at least 600 seconds (10 minutes) at Spanish speech delivery cadence. Furthermore, the pipeline orchestrator MUST enforce an early pre-render gate validating that audio duration is at least 600.0s for all longform lanes, including directed runs.

#### Scenario: Longform narrative template word count calibration (Happy Path)
- **Given** a longform topic for Aelithia or Moku
- **When** narrative generation is executed
- **Then** the produced script MUST contain >= 2,800 words across structured dramatic beats.

#### Scenario: Directed execution minimum duration enforcement (Happy Path)
- **Given** a directed run on a longform lane
- **When** the synthesized audio duration is < 600.0s
- **Then** the pipeline MUST fail closed with early pre-render rejection.

#### Scenario: Directed execution passes gate when duration meets threshold (Happy Path)
- **Given** a directed run on a longform lane with audio >= 600.0s
- **When** duration validation executes
- **Then** the pipeline MUST proceed to subtitle and video rendering.
