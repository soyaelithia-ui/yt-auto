# Delta for Adaptive Narrative Curation

## MODIFIED Requirements

### Requirement 3: Semantic Scene Segmentation, Storyboard Montage, and Timing Bounds
(Previously: Divided longform scripts into 45-90s blocks without narrative storyboard montage structure or transition causality)

The narrative curator MUST segment full narration scripts into discrete semantic scene acts based on narrative storyboarding rather than fixed arithmetic intervals. For vertical Shorts, each scene duration MUST satisfy $8.0\text{s} \le \text{duration} \le 15.0\text{s}$ (3 to 5 scenes). For longform productions (10–15 minutes), the curator MUST define between 5 and 8 semantic story scenes ($60.0\text{s} \le \text{duration} \le 150.0\text{s}$) corresponding to major plot milestones, each specifying narrative location, dramatic objective, and scene transition reason. Scene cuts MUST occur strictly at sentence or paragraph boundaries and MUST NOT split sentences mid-clause.

#### Scenario: Semantic segmentation of vertical Short narration (Happy Path)
- **Given** a voiceover script containing 120 words configured for vertical format at 160 WPM (~45 seconds total)
- **When** semantic scene segmentation is executed
- **Then** the curator MUST produce between 3 and 5 sequential scene contracts
- **And** every individual scene contract MUST have a calculated duration between 8.0s and 15.0s
- **And** the sum of scene durations MUST equal the total narration duration within $\pm 0.5\text{s}$.

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

### Requirement 6: Upstream Archetype and Visual Intent Resolution
The narrative curator and art director MUST explicitly resolve and assign visual archetype tokens and tension ratings during script curation, eliminating downstream heuristic regex keyword matching in scene planning.

#### Scenario: Explicit archetype propagation to scene contract (Happy Path)
- **Given** a curated narrative act set in an underground bunker
- **When** the art director generates the scene visual contract
- **Then** the contract MUST contain explicit archetype `"tactical_chamber"` and tension level
- **And** the planner MUST use the assigned archetype without evaluating regex pattern rules on voiceover text.

#### Scenario: Unrecognized setting intent fallback (Edge Case)
- **Given** an abstract or surreal scene description without a direct archetype mapping
- **When** visual archetype resolution runs
- **Then** the engine MUST assign the closest atmospheric fallback archetype (`"dark_forest"` or `"cosmic_singularity"`) based on tension score.
