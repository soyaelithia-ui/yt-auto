# Specification: Adaptive Narrative Curation

## Capability Overview
The `adaptive-narrative-curation` capability provides autonomous topic-agnostic narrative orchestration, converting open-domain inputs, lore archives, or incident prompts into structured multi-act cinematic script contracts. It enforces a standardized 5-phase tension progression curve (levels 1–5), granular 8–15s semantic scene segmentation calibrated to words-per-minute (WPM) delivery, and deterministic ITU-R BT.709 (Rec.709) color-palette and visual atmosphere mapping.

## Requirements

### Requirement 1: Open-Domain Topic Orchestration and Archetype Mapping
The narrative curator MUST synthesize multi-act script contracts from arbitrary open-domain topic strings, lore prompts, or incident summaries without relying on hardcoded static niche templates. When a specific archetype is not provided, the engine SHALL dynamically determine the best-fit narrative archetype or synthesize a generic high-dread procedural narrative structure.

#### Scenario: Open-domain topic synthesis with dynamic archetype selection (Happy Path)
- **Given** an open-domain topic prompt `"Deep sea seismic resonance anomaly detected at Mariana Trench"`
- **When** `CosmicNarrativeEngine.generate_script` or `CinematicScriptCurator.curate_script` processes the topic
- **Then** the engine MUST generate a complete `CosmicScriptContract` structured across narrative phases
- **And** the script metadata MUST reflect the curated title and topic-aligned telemetry header
- **And** the generated narrative MUST NOT contain hardcoded placeholder strings or unmapped template variables.

#### Scenario: Empty or malformed topic input fallback (Edge Case)
- **Given** an empty string, whitespace-only string, or `None` passed as the topic parameter
- **When** script generation is invoked
- **Then** the engine MUST select a default canonical archetype preset (e.g. `HYDROACOUSTIC_TELEMETRY`)
- **And** the engine MUST populate standard title templates and telemetry headers without raising unhandled exceptions.

### Requirement 2: 5-Phase Tension Curve Scoring (Levels 1–5)
The narrative engine MUST evaluate and assign discrete tension scores strictly between 1 (baseline calm/exposition) and 5 (maximum climax/rupture) across all narrative phases:
1. Phase 1 (Baseline / Exposition): Tension 1–2
2. Phase 2 (Micro-anomaly / Subtle Deviation): Tension 2–3
3. Phase 3 (Escalation / Containment Warping): Tension 3–4
4. Phase 4 (Climax / Catastrophic Rupture): Tension 5
5. Phase 5 (Ambiguity / Redaction & Loop Hook): Tension 3–2

#### Scenario: Sequential tension progression validation (Happy Path)
- **Given** a 4-act or 5-phase narrative script generation request
- **When** the tension curve is compiled across sequential acts
- **Then** each scene MUST have an integer tension score $T \in [1, 5]$
- **And** the tension score MUST escalate progressively to reach $T = 5$ at the climax act
- **And** the final act MUST de-escalate or resolve into an ambiguous loop hook with tension $T \in [2, 3]$.

#### Scenario: Erratic or inverted tension input normalization (Edge Case)
- **Given** an external raw script input containing irregular tension scores (e.g. $[5, 1, 5, 1]$ or out-of-range values like $T = 7$)
- **When** tension normalization runs
- **Then** the engine MUST clamp all values to $[1, 5]$
- **And** the engine MUST smooth abrupt step jumps ($\Delta T > 2$) using monotonic easing to preserve narrative dramatic pacing.

### Requirement 3: Semantic Scene Segmentation and Timing Bounds
The narrative curator MUST segment full narration scripts into discrete semantic scene acts where each individual scene duration satisfies $8.0\text{s} \le \text{duration} \le 15.0\text{s}$ for vertical Short formats (or $45.0\text{s} \le \text{duration} \le 90.0\text{s}$ for longform formats). Scene splitting MUST occur along natural linguistic boundaries (sentences, clauses, or terminal punctuation) and MUST calculate durations using calibrated delivery rates ($150\text{ WPM} \le \text{WPM} \le 175\text{ WPM}$).

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

### Requirement 4: Rec.709 Color-Palette and Visual Atmosphere Mapping
The narrative curator and art director MUST map each curated scene's theme lane and tension score to an ITU-R BT.709 (Rec.709) compliant color palette specification. The visual specification MUST define primary, secondary, accent, shadow, and highlight hex colors, color temperature in Kelvin ($3000\text{K} \le K \le 7000\text{K}$), designated 3D LUT profile names, and volumetric atmospheric particle parameters.

#### Scenario: Visual mood specification generation for high-tension scene (Happy Path)
- **Given** a scene with theme `"cosmic_horror"` and tension score $T = 5$
- **When** `ArtDirectorMoodAgent.plan_visuals` compiles the visual mood specification
- **Then** the output MUST include valid Rec.709 hex color strings (`#041421`, `#00e5a3`, etc.)
- **And** the color temperature MUST evaluate to nominal Kelvin calibration ($6500\text{K}$)
- **And** the output schema MUST strictly validate against `schemas/art_director.schema.json`.

### Requirement 5: High-Retention Conversational and Incident Narrative Hook Synthesis
The narrative curator MUST synthesize Short narrative scripts calibrated strictly between 115 and 145 words (40–55 seconds duration at 160–175 WPM) utilizing conversational 0–2s opening hooks, canonical incident crossovers (e.g. Incident 096-1-A, Incident Clef-Kondraki, SCP-1048, SCP-027, SCP-001), and seamless syntactic loop connectors ending with open trailing clauses without channel handle outro CTAs.

#### Scenario: Generation of SCP Short with high-retention hook and seamless loop (Happy Path)
- **Given** an SCP topic request for `"SCP-1048"` or `"Incidente 096-1-A"`
- **When** `MokuHorrorCurator.build_short_narrative` generates the script
- **Then** the resulting text word count MUST satisfy $115 \le \text{word\_count} \le 145$
- **And** the narration MUST end with an open loop connector (`...`)
- **And** the text MUST NOT contain handle outros (e.g. `@moku`) or subscribe CTAs.

#### Scenario: General horror creepypasta fallback with retention mechanics (Edge Case)
- **Given** a non-SCP creepypasta topic `"la criatura del sotano"`
- **When** `MokuHorrorCurator.build_short_narrative` generates the script
- **Then** the narrative MUST open with an immediate atmospheric hook within the first sentence
- **And** the word count MUST satisfy $115 \le \text{word\_count} \le 145$
- **And** the script MUST terminate on a seamless syntactic connector.

