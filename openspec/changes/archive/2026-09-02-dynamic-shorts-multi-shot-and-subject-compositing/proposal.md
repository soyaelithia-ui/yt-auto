# Proposal: Dynamic Shorts Multi-Shot Cadence, Script Boilerplate Sanitization, and Adaptive Thumbnail Subject Compositing

## Why

### 1. Static Visual Pacing in Loop-Based Shorts
Previously, loop-mode Shorts (30–60s) rendered a single continuous 6-second procedural background stretched across the entire video. While the WebGPU shaders provide atmospheric visuals, holding the exact same camera angle and seed for 45+ seconds leads to visual stagnation and reduced viewer retention on platforms like YouTube Shorts and TikTok. Transitioning to a dynamic 3–4 shot cadence with camera parameter variations and seed offsets keeps the visual storytelling engaging and fluid.

### 2. Leaks of Outro Boilerplate and Social Links into TTS
Scraped or generated stories occasionally contain trailing boilerplate, channel plugs, or community links such as `"Todos los expedientes y archivos se encuentran en Moku Reddit*"`. If not caught by editorial sanitization barriers, these sentences get synthesized into TTS audio, damaging the immersive atmosphere of analog and cosmic horror. Deterministic regex filters and prompt directives must permanently eradicate these outro artifacts before voice generation.

### 3. Empty Thumbnail Focal Centers
Prior thumbnail generation rendered typography over procedural backgrounds without an integrated central subject. User feedback highlighted that thumbnails looked empty in the middle. Rather than relying on slow, inconsistent external image generation APIs, the thumbnail engine needs a procedural `AdaptiveSubjectCompositor` that paints contextually accurate character and entity silhouettes into the focal center with subtle rim lighting and chiaroscuro depth.

---

## What Changes

### 1. Multi-Camera Shot Cadence (`src/pipeline.py`)
- For loop-mode Shorts with narrative audio duration > 14s:
  - Automatically partition total audio duration into 2 to 4 balanced shot segments (8–12 seconds each).
  - Resolve distinct loop video backgrounds with seed variation (`s_idx * 101`) and camera angles.
  - Record the shot breakdown in `visual_plan.json` for deterministic QA inspection.

### 2. Deterministic Outro Sanitization (`src/sanitizer.py`, `src/llm.py`)
- Add regex patterns to `FORBIDDEN_EDITORIAL_PATTERNS` in `src/sanitizer.py` matching:
  - Archive/dossier custody boilerplate: `r'(?i)\b(?:todos\s+los\s+)?(?:expedientes|archivos|relatos)\s+(?:y\s+(?:archivos|grabaciones)\s+)?(?:se\s+encuentran|permanecen\s+archivados)...'`
  - Reddit/handle plugs: `r'(?i)@?(?:MokuRedit|Moku\s*Reddit|Aelithia)\b'`
- Harden LLM prompt directives in `src/llm.py` to prohibit outro handles or subreddit mentions.

### 3. Adaptive Thumbnail Subject Compositor (`src/media/thumbnails/`)
- Implement `AdaptiveSubjectCompositor` in `src/media/thumbnails/subject_extractor.py`:
  - Renders anatomical, thematic silhouettes matching each setting archetype:
    - `maritime_lighthouse`: Coastal cliff observer under the sweeping beacon beam.
    - `tactical_chamber`: Arched concrete tunnel portal with descending steps and explorer silhouette.
    - `dark_forest`: Pine tree treeline with glowing-eyed watcher.
    - `arctic_desolation`: Jagged snow ridge with emaciated humanoid anomaly.
    - `cosmic_singularity`: Deep space event horizon with solitary astronaut.
    - `arcade_vector_flight`: Retro vector spaceship firing laser pulses.
    - `parkour_runner`: Isometric neon voxel platformer silhouette.
    - `cozy_hearth`: Trench coat figure by rainy ambient window.
    - `synaptic_network`: Neural node network with contemplative silhouette.
  - Applies soft chiaroscuro Gaussian mist and channel accent rim lighting.
- Integrate `AdaptiveSubjectCompositor` into `src/media/thumbnails/engine.py`.

---

## Impact

### Affected Areas
| Component / File | Impact Level | Description |
|---|---|---|
| `src/pipeline.py` | MEDIUM | Plans multi-scene shot sequences for loop mode when audio > 14s. |
| `src/sanitizer.py` | LOW | Strips outro Reddit/archive plugs before TTS. |
| `src/llm.py` | LOW | Directs LLM prompts to omit channel handle plugs. |
| `src/media/thumbnails/subject_extractor.py` | MEDIUM | Procedural subject silhouette and rim-light compositor. |
| `src/media/thumbnails/engine.py` | LOW | Injects subject compositor step into cover generation. |
| `tests/unit/` | LOW | Dedicated unit tests for sanitizer, compositor, and shot planning. |
