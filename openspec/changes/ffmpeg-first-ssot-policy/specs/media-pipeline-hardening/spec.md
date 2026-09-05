# Delta for Media Pipeline Hardening

## MODIFIED Requirements

### Requirement: High-Throughput Rawvideo Stream Piping with Multi-Scene Pipe Isolation
Production video MUST NOT require piping uncompressed `rawvideo rgb24` frames into FFmpeg stdin. Homogeneous procedural loops MUST use catalog/lavfi files and concat demuxer `-c:v copy` when `stream_copy_mode`. Raw pixel stdin (`rawvideo rgb24` or `yuv420p`) MAY run only when `ENABLE_NATIVE_PROCEDURAL` is explicitly enabled.
(Previously: Production MUST pipe rawvideo rgb24/yuv420p into FFmpeg stdin for all multi-scene renders.)

#### Scenario: Production director path does not use rawvideo stdin (Happy Path)
- **Given** `ENABLE_NATIVE_PROCEDURAL` is unset and a multi-scene procedural manifest without `niche_hud`
- **When** `DIRECTOR_SINGLE_PASS` assembles the video
- **Then** FFmpeg MUST ingest catalog/lavfi media via concat demuxer
- **And** the pipeline MUST NOT require `-f rawvideo -pix_fmt rgb24` stdin.

### Requirement: Multi-Layer Procedural Atmospheric Shaders
Production loop synthesis MUST resolve catalog rows as FFmpeg lavfi. The nine WGSL archetypes MAY compile only when `ENABLE_NATIVE_PROCEDURAL` is set and MUST remain quarantined under `src/media/_legacy`. Production MUST NOT require Mesa Lavapipe or `.wgsl` compilation.
(Previously: Visual engine MUST support nine WGSL archetypes as production MUST, including maritime_lighthouse on Lavapipe.)

#### Scenario: Production catalog uses FFmpeg lavfi (Happy Path)
- **Given** `ENABLE_NATIVE_PROCEDURAL` is unset and a story referencing maritime settings
- **When** the procedural loop engine resolves the video
- **Then** the loop MUST be synthesized as FFmpeg lavfi/catalog
- **And** WGSL/Lavapipe MUST NOT be required.

### Requirement: Orchestrator Pipeline Mode and Lane Config Alignment
The orchestrator in `src/pipeline.py` MUST correctly resolve lane video engine specifications across both `visual_pipeline` and `video_engine` configuration keys. When a lane specifies `"director"` or `"multiscene"`, the pipeline MUST instantiate `MultiSceneCompositor` defaulting to `ProceduralVideoEngine()`. `NativeProceduralEngine` MUST be used only when `ENABLE_NATIVE_PROCEDURAL` is explicitly enabled.
(Previously: director/multiscene MUST connect MultiSceneCompositor to NativeProceduralEngine.)

#### Scenario: Channel with director pipeline defaults to ProceduralVideoEngine
- **Given** a channel lane configuration specifying `"visual_pipeline": "director"` and `ENABLE_NATIVE_PROCEDURAL` unset
- **When** the pipeline orchestrator initializes the video render phase
- **Then** the pipeline MUST invoke `MultiSceneCompositor` rather than `LoopVideoEngine`
- **And** the compositor MUST default to `ProceduralVideoEngine()` not `NativeProceduralEngine`.

#### Scenario: Native procedural remains opt-in (Edge Case)
- **Given** `ENABLE_NATIVE_PROCEDURAL` is explicitly enabled
- **When** `MultiSceneCompositor` initializes with native rendering
- **Then** `NativeProceduralEngine` MAY be used from `src/media/_legacy`
- **And** production defaults MUST remain FFmpeg when the flag is unset.
