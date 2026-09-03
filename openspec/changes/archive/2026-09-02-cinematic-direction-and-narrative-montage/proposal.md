# Proposal: Cinematic Direction and Narrative Montage Pipeline Evolution

## Motivation
Production validation of longform channels (`moku-horror-long`, `aelithia-aita-long`) revealed that generated videos looped a single 6-second static procedural clip for 14+ minutes with near-zero luminance (crushed black screen on `maritime_lighthouse.wgsl`). The 3 specialized agents (`CinematicScriptCuratorAgent`, `ArtDirectorMoodAgent`, `ScenePlannerCompositorAgent`) were bypassed due to configuration mismatches between `config/lanes.json` (`visual_pipeline: "director"`) and `src/pipeline.py` (`lane.video_engine`), defaulting to `"loop"`. Furthermore, scene segmentation relied on naive 11-second arithmetic cuts rather than semantic storyboards, scene archetype selection used brittle regex keyword searches, and the WebGPU native procedural engine discarded art director metadata due to a 64-byte uniform buffer bottleneck.

## Goals
1. **Narrative Storyboard Montage**: Replace blind 11-second arithmetic segmentation in `ScriptCurator` with semantic storyboards (5–8 scenes for 10–14m longform, 60–150s per scene) aligned with narrative turning points.
2. **Semantic Visual Attribution**: Eliminate crude regex keyword archetype matching in `ScenePlanner`, binding scene archetypes directly from curated storyboards and art direction.
3. **Photometric Luminance Floor**: Ensure dark WGSL shaders enforce a minimum 15%–25% luminance floor and sRGB gamma curve to guarantee visibility on mobile OLED screens.
4. **WebGPU Uniform Buffer Adapter**: Implement a deterministic mapping from art direction metadata (tension curve, Kelvin temperature, palette accents) into the fixed 64-byte uniform buffer expected by native shaders.
5. **Runtime Engine Dispatch Alignment**: Align `config/lanes.json` and `src/pipeline.py` so lanes configured with director/multiscene activate `MultiSceneCompositor` with `NativeProceduralEngine`.

## Capabilities

### Modified Capabilities
- `adaptive-narrative-curation`: Add semantic storyboard montage rules and eliminate regex keyword scene selection.
- `procedural-scene-compositor`: Add photometric luminance floor requirement, WebGPU 64-byte uniform adapter, and native engine delegation.
- `media-pipeline-hardening`: Align orchestrator lane configuration dispatch and prevent silent fallback to static loops for director lanes.

## Non-Goals
- Adding any new agents (maintain existing 3 agents).
- Integrating external image/video generation APIs (Midjourney, DALL-E, etc.).
- Modifying TTS, EBU R128 audio mastering, libass subtitles, or QA gating.

## Performance Impact
Multi-scene native procedural rendering runs locally via WebGPU/Mesa Lavapipe. Task concurrency will be bounded to prevent CPU/RAM saturation during parallel scene rendering.

## Rollback Plan
If native multi-scene dispatch fails or causes performance regression, lane configuration can be reverted to `"loop"` mode per-channel without code rollback.
