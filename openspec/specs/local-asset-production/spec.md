# Specification: Local Asset Production

## Capability Overview
The `local-asset-production` capability governs deterministic, local-first media generation across all YouTube production lanes. This specification ensures:
1. Eradication of all remaining real-time graphics assets (`assets/svg_overlays`, `assets/overlays`), procedural WGSL shaders, shader seeds, and shader uniform parameters across schemas and narrative modules.
2. Refocusing creative agents (`AtmosphericDirectorAgent`, `SeoOptimizerAgent`) strictly onto narrative curation and catalog loop mapping, eliminating image diffusion prompts and typography design.
3. Standardizing `LocalAIThumbnailBank` as the authoritative text-free, unbranded, watermark-free cover generator with zero typography rendering.
4. Mandating local video loop composition via `LoopVideoEngine` and stream-copy (`-c:v copy`), guaranteeing compliance with the operational ceiling of $\le 2.0$ CPU Cores and $\le 2.0$ GiB RAM.
5. Standardizing bounded agent execution and recovery in coordination with `agentic-harness`.

---

## Requirements

### Requirement: no runtime graphics
(Previously: Banned imports or exposition of Ken Burns, hybrid frame generation, SVG/in-memory overlays, HUD drawtext/drawbox, or procedural video renderers without explicit filesystem eradication assertions or schema uniform purging.)

The production source tree, schemas, and asset directories MUST NOT import, expose, stage, or contain Ken Burns, hybrid frame generation, SVG/in-memory overlays, HUD drawtext/drawbox, procedural video renderers, WGSL shaders, shader seeds, or shader uniform parameters.

The legacy overlay directories `assets/svg_overlays/` and `assets/overlays/` MUST be permanently deleted and MUST NOT exist in the repository.
Anti-regression guardrails (`src/verification/guardrails.py`) and verification test suites (`tests/unit/test_zero_procedural_math_video_policy.py`) MUST assert that `assets/svg_overlays/` and `assets/overlays/` do not exist on disk.
Schemas (`schemas/art_director.schema.json`, `schemas/scene_planner.schema.json`, `src/narrative/schema.json`) and narrative engines (`src/narrative/archetypes.py`, `src/narrative/engine.py`) MUST NOT contain `shader_sequence`, `shader_id`, `shader_params`, `shader_seed`, or `uniform_params`.

#### Scenario: Staged or existing overlay directory triggers guardrail violation
- **Given** the repository state being evaluated by `guardrails.py` or `test_zero_procedural_math_video_policy.py`
- **When** either `assets/svg_overlays/` or `assets/overlays/` exists on disk or is staged
- **Then** the check MUST fail with a descriptive violation message
- **And** automated CI/pre-commit MUST reject the commit.

#### Scenario: WGSL shader or uniform parameter rejected in schema validation
- **Given** an art director response or scene planner payload containing `uniform_params`, `shader_seed`, or WGSL archetype identifiers
- **When** the payload is validated against `schemas/art_director.schema.json` or `schemas/scene_planner.schema.json`
- **Then** JSON Schema validation MUST fail
- **And** the agent harness MUST reject the payload.

#### Scenario: Narrative engine emits clean scene structures without shader sequences
- **Given** a narrative archetype loaded from `src/narrative/archetypes.py`
- **When** the narrative engine generates scene acts
- **Then** the scenes MUST NOT contain `shader_sequence` or `shader_id` assignments
- **And** the output manifest MUST specify clean editorial acts with `catalog_loop` visual directives.

---

### Requirement: local video only
(Previously: Accepted only `director` or `video_loop` composing through `LoopVideoEngine` without explicit stream-copy mandates or resource ceilings.)

Production lanes MUST accept only `director` or `video_loop`. Both MUST resolve local video assets exclusively (`assets/loops/horizontal/`, `assets/loops/vertical/`) and compose through `LoopVideoEngine`.

All composition passes MUST use stream-copy (`-c:v copy`) whenever input geometry matches output specifications, bypassing video re-encoding and eliminating CPU rendering churn. Subtitles on loop pathways MUST be multiplexed as soft timed text streams (`-c:s mov_text`) without video filter pixel rasterization.

Media composition and background execution MUST operate strictly under the operational resource ceiling:
- Aggregate CPU utilization MUST NOT exceed 2 CPU cores (≤ 200%).
- Resident memory (RSS) MUST NOT exceed 2.0 GiB (2,048 MiB peak).
- Steady-state idle resource footprint MUST drop to 0% CPU and 0 MiB active allocations.

#### Scenario: Retired visual pipeline rejected before execution
- **Given** a lane configured with `visual_pipeline: image_animation`
- **When** the lane configuration is parsed
- **Then** validation MUST fail before execution begins.

#### Scenario: Director lane assembles local loops via stream-copy without re-encoding
- **Given** a horizontal director lane with curated local act video loops
- **When** stages 8 and 9 execute
- **Then** `LoopVideoEngine.compose()` MUST emit an FFmpeg invocation containing `-c:v copy`
- **And** the FFmpeg invocation MUST NOT contain video filtergraph re-encoding clauses.

#### Scenario: Composition maintains execution within 2 CPU cores and 2.0 GiB RAM ceiling
- **Given** an active video composition running through `LoopVideoEngine`
- **When** resource consumption is profiled during peak assembly
- **Then** aggregate CPU usage MUST NOT exceed 2.0 Cores (200%)
- **And** resident memory (RSS) MUST NOT exceed 2,048 MiB peak.

#### Scenario: Subtitles soft-muxed without video re-encoding
- **Given** a video loop lane with active subtitle dialogue cues
- **When** video composition executes
- **Then** subtitles MUST be multiplexed as `-c:s mov_text`
- **And** stream-copy `-c:v copy` MUST be preserved on the video track.

---

### Requirement: text-free thumbnail bank
(Previously: Resolved local AI-bank images or fallback without drawing title text, badges, watermarks, or captions.)

Thumbnail generation MUST resolve exclusively from `LocalAIThumbnailBank` (`assets/thumbnails/ai_bank/`) or deterministic text-free fallback templates (`assets/thumbnails/templates/`).

All thumbnail assets in the bank MUST adhere to a strict text-free contract:
1. **Filename Sanitization**: The asset filename MUST NOT contain forbidden tokens: `text`, `title`, `caption`, `subtitle`, `badge`, `watermark`, `logo`, or `overlay`.
2. **Metadata Verification**: Each candidate asset MUST have an accompanying JSON sidecar file explicitly declaring `{"text_free": true}`. Assets without this sidecar or declaring `false` MUST be excluded.
3. **Deterministic Selection**: Candidate resolution MUST be deterministic, using content hashes derived from `channel_id`, `archetype`, and `selection_key`.
4. **Zero Typography Rendering**: Thumbnail engines (`ThumbnailEngine`, `ResilientThumbnailEngine`) MUST NEVER load font files, compute text layout bounding boxes, draw text, render badges, or burn titles/captions onto images.
5. **Image Verification**: All selected assets MUST pass image readability verification (`Image.verify()`) without corruption.

#### Scenario: Declared text asset in sidecar rejected
- **Given** a bank image whose sidecar JSON declares `text_free: false`
- **When** `LocalAIThumbnailBank.candidates()` or `is_text_free()` evaluates the asset
- **Then** the asset MUST be excluded from candidate selection.

#### Scenario: Asset filename containing forbidden token rejected
- **Given** an image file named `cover_title_badge.png` in the thumbnail bank directory
- **When** `LocalAIThumbnailBank.is_text_free()` evaluates the path
- **Then** the filename MUST fail validation due to forbidden tokens `title` and `badge`
- **And** the asset MUST NOT be returned in candidates.

#### Scenario: Deterministic selection without font or badge drawing
- **Given** a thumbnail request for channel `horror` with archetype `cosmic_horror`
- **When** `ThumbnailEngine.render()` processes the request
- **Then** the engine MUST resolve a verified text-free asset via hash selection
- **And** the engine MUST NOT execute any PIL `ImageDraw.Draw.text()` or font loading operations
- **And** the output image MUST remain completely unbranded and text-free.

#### Scenario: Fallback to text-free template when bank candidates are absent
- **Given** an empty thumbnail bank folder for a given archetype
- **When** `ThumbnailEngine` resolves an asset
- **Then** the engine MUST fall back to a clean template in `assets/thumbnails/templates/`
- **And** verify that the template contains zero typography before export.

---

### Requirement: Refocused Creative Agents (Zero Diffusion Prompts and Zero Typography Design)
All creative production agents MUST be strictly decoupled from graphic design, typography rendering, and image diffusion prompt generation.

1. **AtmosphericDirectorAgent Refocusing**:
   - `AtmosphericDirectorAgent` MUST NOT generate image diffusion prompts (`positive_prompt`, `negative_prompt`), camera lens parameters (`focal_length_mm`, `depth_of_field`), or pseudo-shader uniforms.
   - The agent MUST focus exclusively on narrative mood evaluation, mapping scenes to curated catalog loop categories (`cosmic_horror`, `dark_ambient`, `tactical_chamber`, `dramatic_interior`), and acoustic soundscape selection (`drone_abyss`, `dark_ambient`, `tension_pulse`).
2. **SeoOptimizerAgent Refocusing**:
   - `SeoOptimizerAgent` MUST NOT output typography styling, font choices, badge configurations, or headline overlay layouts.
   - Thumbnail requests emitted by `SeoOptimizerAgent` MUST declare only semantic archetype, focal subject, and `text_free=True`.
3. **Schema Enforcement**:
   - Schemas governing creative agents (`schemas/art_director.schema.json`) MUST forbid diffusion prompt objects and shader fields (`additionalProperties: false`).

#### Scenario: Atmospheric director emits pure catalog loop and soundscape selection
- **Given** a narrative script provided to `AtmosphericDirectorAgent`
- **When** the agent processes the script
- **Then** the emitted result MUST contain `loop_category`, `audio_theme`, `mood_summary`, and `accent_hex`
- **And** the result MUST NOT contain `image_prompts`, `positive_prompt`, `negative_prompt`, or `uniform_params`.

#### Scenario: Output containing diffusion prompts rejected by art director schema
- **Given** an agent response containing an `image_prompts` object with diffusion text
- **When** validated against `schemas/art_director.schema.json`
- **Then** JSON schema validation MUST fail with an unexpected property error
- **And** trigger failure recovery in the agentic harness.

#### Scenario: SEO optimizer requests text-free cover without typography directives
- **Given** a story being packaged by `SeoOptimizerAgent`
- **When** the agent emits thumbnail metadata directives
- **Then** the request MUST contain `text_free: True`
- **And** MUST NOT contain headline layout coordinates, font names, or badge labels.

---

### Requirement: bounded agent recovery
Agent execution MUST record every failure decision and MUST not exceed configured attempt/correction budgets, governed comprehensively by `openspec/specs/agentic-harness/spec.md`.

#### Scenario: transient failure
- **Given** a transient provider error on attempt one
- **When** the recovery policy has remaining attempts
- **Then** it retries and records `action: retry`.

#### Scenario: contract failure
- **Given** a response validation failure and one correction budget
- **When** the agent retries
- **Then** it sends one correction prompt and records `action: correct`.

#### Scenario: saturation
- **Given** a quota/rate-limit error
- **When** the agent handles it
- **Then** it stops immediately, records `provider_saturation`, and trips the instance circuit breaker.
