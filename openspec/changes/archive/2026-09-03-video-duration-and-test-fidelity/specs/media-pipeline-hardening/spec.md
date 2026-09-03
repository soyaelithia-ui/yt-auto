# Delta for Media Pipeline Hardening

## MODIFIED Requirements

### Requirement: Unit Test Compositor Isolation and Hermetic Execution

Unit tests verifying daemon orchestration, CLI commands, and safety assertions MUST NOT invoke live WebGPU software rasterization (Lavapipe) or FFmpeg encoding for longform video durations (>=600s). MultiSceneCompositor.render MUST be mocked to return a placeholder video artifact in unit tests, preserving sub-second execution speed and zero orphan processes.

#### Scenario: Multi-scene compositor isolation in unit test suite (Happy Path)
- **Given** a unit test orchestrating daemon or safety pipeline execution
- **When** pipeline execution triggers video rendering on a longform lane
- **Then** the compositor MUST be mocked to return placeholder video without invoking FFmpeg or WebGPU software rasterization
- **And** the unit test MUST complete in under 4 seconds.
