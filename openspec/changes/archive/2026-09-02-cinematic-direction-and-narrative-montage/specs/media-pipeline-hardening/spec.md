# Delta for Media Pipeline Hardening

## ADDED Requirements

### Requirement 10: Orchestrator Pipeline Mode and Lane Config Alignment
The orchestrator in `src/pipeline.py` MUST correctly resolve lane video engine specifications across both `visual_pipeline` and `video_engine` configuration keys. When a lane specifies `"director"` or `"multiscene"`, the pipeline MUST instantiate and dispatch the render workflow through `MultiSceneCompositor` connected to `NativeProceduralEngine`. If a channel config specifies an unrecognized engine mode, the pipeline MUST fail early with a clear validation error rather than silently defaulting to a 6-second static loop.

#### Scenario: Channel with director pipeline dispatches multiscene compositor (Happy Path)
- **Given** a channel lane configuration specifying `"visual_pipeline": "director"`
- **When** the pipeline orchestrator initializes the video render phase
- **Then** `engine_mode` MUST resolve to `"director"` (or `"multiscene"`)
- **And** the pipeline MUST invoke `MultiSceneCompositor` rather than `LoopVideoEngine`.

#### Scenario: Unrecognized engine mode configuration detection (Error State)
- **Given** a channel configuration with an invalid engine string `"unknown_engine"`
- **When** the pipeline validates configuration during initialization
- **Then** the pipeline MUST raise a `ValueError` detailing the invalid engine mode
- **And** execution MUST NOT proceed with silent fallback to static loop mode.
