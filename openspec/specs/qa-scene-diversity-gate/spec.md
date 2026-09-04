# Capability: QA Scene Diversity Gate

## Requirements

### Requirement: Longform Video Scene Count Invariant
The QA subsystem MUST evaluate the total count of distinct visual scenes in a production and reject longform videos that fail minimum diversity thresholds.

#### Scenario: Rejection of longform video with insufficient scene count
- **Given** a rendered video with total duration of 600.0 seconds (10.0 minutes)
- **And** a scene manifest containing only 4 visual scene changes
- **When** the `SceneDiversityGate` evaluates the production
- **Then** the gate result MUST return `is_passed = False`
- **And** the failure code MUST be `ERR_QA_SCENE_DIVERSITY_INSUFFICIENT`
- **And** the message MUST report that longform productions requiring at least 6 distinct scenes only received 4.

#### Scenario: Approval of compliant diverse longform video
- **Given** a rendered video with total duration of 610.0 seconds
- **And** a scene manifest containing 16 distinct visual scene transitions
- **When** the `SceneDiversityGate` evaluates the production
- **Then** the gate result MUST return `is_passed = True`
- **And** the result severity MUST be `INFO`.

### Requirement: Asset Dominance Upper Bound
The QA subsystem MUST compute the percentage of total duration occupied by any single asset and reject deliveries exhibiting single-asset dominance.

#### Scenario: Rejection of single-asset dominance in longform production
- **Given** a video of 865.0 seconds
- **And** a single visual asset (`loop_tactical_chamber_horizontal_101.mp4`) covering 865.0 seconds (100% of runtime)
- **When** the `SceneDiversityGate` evaluates asset distribution
- **Then** the gate result MUST return `is_passed = False`
- **And** the failure code MUST be `ERR_QA_ASSET_DOMINANCE_EXCEEDED`
- **And** the message MUST indicate the asset exceeds the 25% duration threshold.

### Requirement: Short Video Scene Count Invariant
The QA subsystem MUST evaluate the total count of distinct visual scenes in vertical Short productions and reject videos that fail the short-form diversity threshold.

#### Scenario: Rejection of Short video with insufficient scene count
- **Given** a rendered vertical Short video with duration of 45.0 seconds
- **And** a scene manifest containing only 1 or 2 visual scene changes
- **When** the `SceneDiversityGate` evaluates the Short production
- **Then** the gate result MUST return `is_passed = False`
- **And** the failure code MUST be `ERR_QA_SHORT_DIVERSITY_INSUFFICIENT`
- **And** the message MUST report that vertical Short productions require at least 3 distinct visual scenes.

#### Scenario: Approval of compliant diverse Short video
- **Given** a rendered vertical Short video with duration of 50.0 seconds
- **And** a scene manifest containing 4 distinct visual scene transitions
- **When** the `SceneDiversityGate` evaluates the production
- **Then** the gate result MUST return `is_passed = True`
- **And** the result severity MUST be `INFO`.

### Requirement: Production Gatekeeper Diversity Enforcement
`lib/qa_gatekeeper.py` MUST actively invoke scene diversity evaluation across production runs (longform and shorts), blocking publish when single-asset dominance exceeds 25% or scene counts fall below thresholds (≥6 longform, ≥3 Shorts).

#### Scenario: Gatekeeper blocks publishing on single-asset dominance
- **Given** a finished video deliverable where a single background asset spans 70% of total runtime
- **When** `lib/qa_gatekeeper.py` audits the production
- **Then** the gatekeeper MUST reject the video deliverable
- **And** the delivery status MUST be marked as failed without uploading or publishing to YouTube.

