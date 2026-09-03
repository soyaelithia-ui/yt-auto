# Capability: Scene Pacing and Shot Count Scaling

## Requirements

### Requirement: Dynamic Shot Count Calculation
The pipeline SHALL dynamically calculate the number of visual scene shots based on total narration audio duration, format orientation, and target pacing bounds without an arbitrary static ceiling.

#### Scenario: Longform video shot count scaling
- **Given** a longform video audio duration of 865.0 seconds (approx 14.4 minutes)
- **When** the scene pacing calculator computes shot progression for longform horizontal orientation
- **Then** the resulting shot count MUST be at least 15 shots and at most 45 shots
- **And** no individual shot duration SHALL exceed 45.0 seconds.

#### Scenario: Short format video shot count scaling
- **Given** a vertical short video audio duration of 44.0 seconds
- **When** the scene pacing calculator computes shot progression for vertical orientation
- **Then** the resulting shot count MUST be between 3 and 5 shots
- **And** no individual shot duration SHALL exceed 15.0 seconds.

### Requirement: Non-Repeating Asset Resolution
When resolving visual assets across consecutive scenes, the resolver MUST enforce asset variety and prevent immediate identical asset repetition.

#### Scenario: Diverse asset assignment across multiple acts
- **Given** a sequence of 8 planned scenes for a longform production
- **And** an asset catalog containing multiple matching visual templates
- **When** the asset assignment engine resolves background loops for each scene
- **Then** no two adjacent scenes SHALL share the same visual asset path
- **And** no single asset SHALL represent more than 25% of the total scene count when alternative catalog assets exist.
