# Delta for Procedural Scene Compositor

## MODIFIED Requirements

### Requirement: Production FFmpeg Scene Synthesis
Production scene synthesis MUST use FFmpeg lavfi/catalog procedural loops, concat demuxer stream-copy when homogeneous, `DIRECTOR_SINGLE_PASS` assembly, and FFmpeg `drawtext`/`drawbox` HUD. `NativeProceduralEngine`, WebGPU, GLSL, and WebGL MUST NOT run on the production hot path unless `ENABLE_NATIVE_PROCEDURAL` is explicitly enabled and MUST stay quarantined under `src/media/_legacy`.
(Previously: Production MUST execute GLSL/WebGL/Three.js pipelines and delegate every scene to NativeProceduralEngine.)

#### Scenario: Production compositor uses FFmpeg lavfi stream-copy DIRECTOR_SINGLE_PASS and drawtext
- **Given** `ENABLE_NATIVE_PROCEDURAL` is unset
- **When** `MultiSceneCompositor` renders procedural scenes
- **Then** production MUST use FFmpeg lavfi/catalog, `DIRECTOR_SINGLE_PASS`, and `drawtext`/`drawbox` HUD
- **And** homogeneous loops without `niche_hud` MUST stream-copy (`-c:v copy`)
- **And** `NativeProceduralEngine` MUST NOT load.

#### Scenario: NativeProceduralEngine WebGPU GLSL WebGL remain opt-in only
- **Given** `ENABLE_NATIVE_PROCEDURAL` is explicitly enabled
- **When** `MultiSceneCompositor` initializes with native rendering
- **Then** `NativeProceduralEngine` / WebGPU / GLSL / WebGL MAY run from `src/media/_legacy`
- **And** production defaults MUST remain FFmpeg when the flag is unset.
