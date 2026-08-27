# Specialized 4-Agent Pipeline, System Prompts, Color Matrices & Fallback Protocols

**Document ID:** `ARCH-M3-AGENTS-PROMPTS-COLOR-2026`  
**Milestone:** M3 (Specialized 4-Agent Pipeline, System Prompts & Theme Color Systems)  
**System Target:** `yt-auto` (Premium Multi-Lane Dual-Engine Video Production Platform)  
**Assurance Level:** High-Assurance / Deterministic / Fail-Closed  

---

## 1. Architectural Overview & Collaboration Topology

The specialized agent pipeline orchestrates the transformation of uncurated story narratives into broadcast-ready, multi-scene video manifests and conducts automated forensic quality control. Rather than delegating video production to an unconstrained end-to-end model, the system decouples responsibility across four specialized single-responsibility agents executing in a strictly validated Directed Acyclic Graph (DAG).

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 INGESTION & CURATION LAYER                             │
│                  (Reddit / PullPush / SCP Wiki / Crom API -> SimHash Deduplication)    │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ Raw Story Text
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ AGENT 1: CINEMATIC SCRIPT CURATOR (`CinematicScriptCurator`)                           │
│ - Segment into Dramatic Acts (Act I: Exposition -> Act IV: Aftermath)                  │
│ - Scene pacing: 45-90s per visual beat for Longform, 8-15s for Shorts                  │
│ - Spoken text sanitized to Spanish Neutral (Zero meta-chatter, zero channel filler)    │
│ - Explicit tension curve grading (Levels 1 to 5)                                       │
│ Output Contract: `cinematic_script.json` (Validated against `script_curator.schema`)   │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                     ┌──────────────────────┴──────────────────────┐
                     │                                             │
                     ▼                                             ▼
┌──────────────────────────────────────────┐  ┌──────────────────────────────────────────┐
│ AUDIO SYNTHESIS SUBSYSTEM                │  │ AGENT 2: ART DIRECTOR / MOOD VISUAL      │
│ - Neural Edge-TTS Synthesis              │  │ (`ArtDirectorMoodVisual`)                │
│ - WordBoundary Timestamp Extraction      │  │ - 5-Color Rec.709 Palette Quintets       │
│ - Multi-voice lane rotation              │  │ - Volumetric Lighting & Temperature (K)  │
│ - EBU R128 Master Voice Pre-conditioning │  │ - Weather Layers & Particle Dynamics     │
│ Output: `narration.wav`, `timestamps.json`│  │ - Positive / Negative Prompt Directives  │
└────────────────────┬─────────────────────┘  │ Output: `visual_plan.json`               │
                     │                        │ (Validated vs `art_director.schema`)     │
                     │                        └────────────────────┬─────────────────────┘
                     └──────────────────────┬──────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ AGENT 3: SCENE PLANNER / COMPOSITOR (`ScenePlannerCompositor`)                         │
│ - Engine Selection: Hybrid Cinematic Parallax vs Pure Procedural WebGL/Canvas          │
│ - Exact frame-accurate timeline calculation synchronized to audio word boundaries      │
│ - Camera motion trajectory (3D Ken Burns, Bezier easing, Parallax amplitudes)          │
│ - Sidechain compression ducking parameters (-18 dB, 20ms attack, 350ms release)        │
│ - Safe Area Boundary Protection (16:9 Landscape vs 9:16 Vertical Shorts)               │
│ Output Contract: `scene_manifest.json` (Validated against `scene_planner.schema`)      │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ DUAL RENDERING ENGINES & MASTER FFMPEG COMPOSITOR                                      │
│ - Hybrid Engine: AI Matte + Monocular Depth Map + GLSL Volumetric Raymarch + Particles │
│ - Procedural Engine: Headless Playwright WebGL / Three.js / Canvas2D Virtual Time       │
│ - FFmpeg Postprocessing: CRF 18-20, Lanczos 36-tap, Rec.709 deband, EBU R128 mastering │
│ Output Artifact: `master_render.mp4`                                                   │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ AGENT 4: VISUAL & AUDIO QA AUDITOR (`VisualAudioQAAuditor`)                            │
│ - Tier 1: Audio Signal Physics (-14 LUFS, <= -1.5 dBTP, Phase >= 0.2, STFT Whistle)   │
│ - Tier 2: Video Container & Luminance (1080p, Rec.709, Avg Lum >= 22, Faststart moov)  │
│ - Tier 3: Programmatic Vision AI Review (Keyframe Contact Sheet, Subtitle Legibility)  │
│ Output Contract: `qa_audit_report.json` (Validated against `video_qa.schema`)          │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                      ┌─────────────────────┴─────────────────────┐
                      │                                           │
             [overall_pass == true]                      [overall_pass == false]
                      ▼                                           ▼
┌──────────────────────────────────────────┐  ┌──────────────────────────────────────────┐
│ TELEGRAM PREVIEW & VERIFIED UPLOAD       │  │ FAIL-CLOSED QUARANTINE & AUDIT ALARM     │
│ - Dispatch keyframe contact sheet        │  │ - Zero-upload perimeter enforcement      │
│ - Automated CodeReviewVerdict approval   │  │ - Diagnostic telemetry log emitted       │
│ - Verified Google Drive & YouTube Upload │  │ - Rejection reasons registered in DB     │
└──────────────────────────────────────────┘  └──────────────────────────────────────────┘
```

---

## 2. Agent 1: Cinematic Script Curator (`CinematicScriptCurator`)

### 2.1 Mission & Architectural Scope
The **Cinematic Script Curator** ingests unstructured raw narrative text (Reddit submissions, SCP documentation, Creepypasta logs, or AITA relationship threads) and translates it into a four-act dramatic screenplay optimized for high viewer retention, vocal naturalism, and precise visual synchronization.

### 2.2 Tension Level Grading Matrix (Levels 1 to 5)
Every scene within the screenplay is graded on a discrete 1-to-5 tension scale that directly drives downstream camera velocity, lighting turbulence, audio ducking, and shader parameters:

| Level | Name | Narrative State | Vocal & Rhythmic Characteristics | Downstream Dynamic Modulation |
|---|---|---|---|---|
| **1** | **Calm Baseline** | World-building, normal environment, baseline establishing shots. | Steady, measured, natural conversational tempo (135–140 WPM). | Slow camera pan/drift ($Z=1.00 \rightarrow 1.04$), deep volumetric haze, stable soft lighting. |
| **2** | **Subtle Disquiet** | Discovery of anomalous detail, odd discrepancy, rising doubt. | Slight vocal deceleration, elongated pauses at sentence boundaries. | Moderate zoom ($Z=1.00 \rightarrow 1.08$), desaturated shadows, slow particulate drift. |
| **3** | **Escalating Dread** | Confirmation of threat, isolation, irreversible threshold crossed. | Tightened phrasing, increased vocal gravity and breath tension. | Multi-axis parallax ($Z=1.00 \rightarrow 1.12$), volumetric flicker, increased shader turbulence. |
| **4** | **Imminent Peril** | Direct confrontation, physical chase, cognitive panic, moral ultimatum. | Rapid rhythmic delivery (155–165 WPM), short punchy clauses. | Rapid camera dolly ($Z=1.00 \rightarrow 1.16$), emergency color shifts, heavy particle density. |
| **5** | **Peak Terror / Climax** | Maximum horror, existential reveal, lethal turning point. | High vocal intensity, abrupt chilling breaks, decisive devastation. | Dutch angle tilt (3–7°), chromatic aberration spikes, harsh directional flash/strobe. |

### 2.3 Verbatim System Prompt
```markdown
You are the Cinematic Script Curator for an automated high-end audiovisual production studio. Your mission is to structure raw narrative source material into a gripping, professionally paced cinematic script in neutral Spanish (Español Neutro).

### STRICT OPERATIONAL RULES:
1. Zero Conversational Meta-Chatter: NEVER include greetings, introductory filler ("¡Hola a todos!", "Bienvenidos a mi canal"), rhetorical channel chatter ("No olvides suscribirte"), or self-referential commentary ("En esta historia veremos..."). The narration must dive immediately into the world of the story from word zero.
2. Direct Hook (0-3 Seconds): The opening sentence must immediately seize attention, establishing an intriguing premise or anomaly without preamble.
3. Dramatic Act Segmentation:
   - For Longform (600s - 1800s): Divide the narrative into 4 distinct acts:
     * Act I (Exposition & Inception): World baseline, introducing the setting and central subject (Tension 1 -> 2).
     * Act II (Rising Action & Investigation): Escalating anomalies, psychological dread, deepening conflict (Tension 2 -> 3).
     * Act III (Confrontation & Peak Climax): Maximum danger, direct contact, turning point (Tension 4 -> 5).
     * Act IV (Aftermath & Horrifying Revelation): Lingering cosmic dread, irreversible consequences, closing chilling thought (Tension 3 -> 2).
   - For Shorts (45s - 58s): Structure into 3 tightly compressed beats (Hook [Tension 3], Core Anomaly [Tension 4-5], Twist/Chilling Outro [Tension 4]).
4. Pacing & Scene Shift Cadence:
   - For longform: Each scene within an act must represent a visual/thematic shift of 45 to 90 seconds (approximately 110–220 spoken words at 145 WPM).
   - For shorts: Each scene/beat represents 8 to 15 seconds (approximately 20–40 spoken words).
5. Tension Level Grading: Every scene must have an integer tension_level between 1 and 5.
6. Spanish Neutrality (Español Neutro): Use grammatically clean, natural standard Spanish. Avoid regional slang (che, tío, chaval, güey, parcero). Maintain correct orthography and punctuation (¿?, ¡!, acentos).
7. Zero Structural Tags in Spoken Text: The narration_text must contain ONLY clean, speakable text for Text-to-Speech synthesis. No markdown tags, no [Scene 1] markers, no stage directions in brackets.
8. Output Format: You must respond EXCLUSIVELY with a single, valid JSON object matching the requested schema. No surrounding commentary or markdown code blocks.
```

### 2.4 Input & Output Data Contracts
- **Input Contract:** `CinematicScriptCuratorInput` containing `raw_source_text`, `story_title`, `channel_lane`, `target_format` (`longform` | `short`), `target_duration_sec`, and optional `target_wpm`.
- **Output Contract:** `cinematic_script.json` (Validated against `schemas/script_curator.schema.json`).

### 2.5 Fail-Closed 3-Tier Fallback Protocol
1. **Tier 1 (AI Retry with Constrained Sampling):** On schema validation error or timeout, re-invoke with temperature reduced to 0.1 and explicit json-mode schema enforcement.
2. **Tier 2 (Algorithmic Partitioning & Lexical Tension Grading):** If the LLM provider fails (HTTP 5xx, quota exhaustion, circuit breaker trip), execute `src/sanitizer.py` and `src/curators/beats.py`:
   - Strip all markdown, editorial headers, and unpronounceable characters.
   - Partition text into 4 acts based on canonical word distribution (20% Act I, 35% Act II, 30% Act III, 15% Act IV).
   - Chunk paragraphs into 45–90 second segments (~145 words/min).
   - Assign tension scores via lexical sentiment matching using a domain horror/drama keyword dictionary.
3. **Tier 3 (Fail-Closed Quarantine):** If the algorithm produces fewer than the required scenes or encounters un-sanitizable strings, the pipeline halts immediately with a `ScriptIntegrityViolation` error before any audio or video render costs are incurred.

---

## 3. Agent 2: Art Director / Mood Visual (`ArtDirectorMoodVisual`)

### 3.1 Mission & Architectural Scope
The **Art Director / Mood Visual** agent consumes the structured `cinematic_script.json` and crafts an exhaustive, per-scene aesthetic blueprint. It determines exact Rec.709 5-color palettes, lighting rigs (color temperature in Kelvin, key direction, volumetric density), atmospheric weather effects, camera framing, focal length, depth of field, and image generation prompts with strict positive and negative rules.

### 3.2 Visual Quality Standards
- **Color Gamut:** Strictly bounded within studio standard Rec.709 color space.
- **Luminance Thresholds:** Average perceptual scene luminance must satisfy $Y_{\text{avg}} \ge 22.0$ (on a 0–255 scale) with dark ratio ($Y < 20$) $\le 0.45$. Featureless crushed black zones ($Y < 16$) are strictly prohibited.
- **Optics & Composition:** 35mm / 50mm / 85mm anamorphic camera models with authentic optical depth of field (f/1.4 to f/8.0).

### 3.3 Verbatim System Prompt
```markdown
You are the Art Director / Mood Visual Director for a cinematic video production studio specializing in psychological horror, cosmic horror, classified SCP containment archives, and high-tension human drama.

### MISSION:
Read the structured cinematic script and produce an exhaustive visual direction manifest for every scene.

### CORE ART DIRECTION PRINCIPLES:
1. Tension-to-Visual Synchronicity:
   - Tension 1-2: Expansive, deep atmospheric perspective, cooler desaturated tones, subtle volumetric fog, slow camera drift.
   - Tension 3-4: Chiaroscuro lighting, tighter framing (medium close-up, claustrophobic angles), heavy shadow casting, particulate turbulence (dust motes, spores).
   - Tension 5: Extreme Dutch angles, harsh directional contrast, flashing emergency amber/red, chromatic aberration fringes, shallow depth-of-field (f/1.4).
2. Color Palette Cohesion: You must assign 5 exact hex codes per scene (primary, secondary, accent, shadow, highlight) adhering to the lane's specific theme matrix.
3. Lighting Rig Specification: Explicitly describe key light, fill light, rim light, color temperature (in Kelvin: e.g. 2800K warm tungsten vs 6500K overcast cold daylight), and volumetric intensity.
4. Cinematic Composition: Choose from established cinematography shot types (Extreme Wide Establishing, Low-Angle Hero/Menace, Dutch Angle Claustrophobia, Over-the-Shoulder Surveillance, Macro Detail).
5. Image Generation Prompts:
   - Positive Prompt: Highly detailed, cinematic photograph, 35mm lens, master lighting, rich texture, 8k resolution, Rec.709 color grade.
   - Negative Prompt: Explicitly ban: "cartoon, anime, 3d render, blender, oversaturated, neon rainbow, blurry, low-res, deformed hands, grain noise dithering, watermark, text logo".
6. Output Format: Respond EXCLUSIVELY with a single valid JSON object matching the visual_plan.json schema.
```

### 3.4 Input & Output Data Contracts
- **Input Contract:** `cinematic_script.json` + `theme_lane` identifier (`cosmic_horror` | `creepypasta` | `scp_foundation` | `drama_aita`).
- **Output Contract:** `visual_plan.json` (Validated against `schemas/art_director.schema.json`).

### 3.5 Fail-Closed 3-Tier Fallback Protocol
1. **Tier 1 (AI Retry):** Retry generation with strict json-mode and clamped prompt parameters.
2. **Tier 2 (Theme Lane Preset Matrix Lookup):** If the AI service is unavailable, map `theme_lane` and `tension_level` directly into the deterministic `THEME_LANE_PRESETS` catalog. Assign pre-approved 5-color hex tuples, lighting temperatures, and prompt templates.
3. **Tier 3 (Fail-Closed Quarantine):** If a scene requires an uncataloged theme lane or generates invalid hex codes outside Rec.709 color space, reject the run and abort render.

---

## 4. Agent 3: Scene Planner / Compositor (`ScenePlannerCompositor`)

### 4.1 Mission & Architectural Scope
The **Scene Planner / Compositor** synthesizes narrative beats, visual direction manifests, and speech audio durations into the canonical, executable `scene_manifest.json`. It performs rendering engine selection (`hybrid_cinematic` vs `procedural_webgl` / `procedural_canvas` / `procedural_css`), assigns layered assets, configures 3D Ken Burns trajectories, binds transition filters, and sets dynamic audio sidechain ducking levels.

### 4.2 Engine Selection Decision Logic
- **`hybrid_cinematic`:** Selected for photorealistic narrative scenery, architectural interior/exterior scenes, and atmospheric character moments. Executes monocular depth estimation, layer slicing (FG/MG/BG), Bezier-eased camera translation, GLSL volumetric god rays, and GPU particle overlays.
- **`procedural_webgl` / `procedural_canvas` / `procedural_css`:** Selected for abstract cosmic voids, mathematical non-Euclidean anomalies, SCP terminal CRT readouts, or audio-reactive emotional wave ribbons:
  * `cosmic_horror_three.html`: Raymarched relativistic black hole accretion disk with gravitational lensing.
  * `dark_forest_canvas.html`: Generative organic swaying fog and procedural silhouetted forest.
  * `scp_terminal_css.html`: Classified security terminal with real-time phosphor flicker, scanlines, and clearance clearance badges.
  * `drama_waves_canvas.html`: Multi-frequency harmonic sine wave ribbons with smooth chromatic shifts.

### 4.3 Verbatim System Prompt
```markdown
You are the Scene Planner & Compositor Architect of an enterprise automated video rendering pipeline.

### MISSION:
Synthesize the cinematic_script.json, visual_plan.json, and TTS audio duration metadata into the canonical, executable scene_manifest.json visual contract.

### COMPOSITION RULES:
1. Engine Assignment:
   - Assign hybrid_cinematic for realistic scenes with concrete background assets.
   - Assign procedural_webgl or procedural_canvas for cosmic voids, technical SCP terminals, or abstract tension transitions.
2. Timing & Pacing Enforcement:
   - For Longform: Ensure scene durations fall strictly between 45.0s and 90.0s per primary environment change.
   - For Shorts: Ensure shot cadences fall strictly between 8.0s and 15.0s per visual beat.
   - The cumulative duration of all scenes MUST equal total_audio_duration_sec ± 0.05s.
3. Motion Dynamics (Ken Burns 3D):
   - For rising tension (Level 1 -> 3): Smooth slow zoom-in (zoom_start: 1.0, zoom_end: 1.08, pan_direction: "center_to_top").
   - For high climax (Level 4 -> 5): Accelerated multi-axis parallax (zoom_start: 1.0, zoom_end: 1.15, orbital_drift: true).
4. Transition Selection:
   - Level 1-2: crossfade (0.8s - 1.2s).
   - Level 3-4: dip_to_black (0.4s) or defocus_blur (0.5s).
   - Level 5: chromatic_glitch (0.2s) or hard cut.
5. Audio Sidechain Ducking:
   - Target dialogue LUFS: -14.0 LUFS.
   - Ambient music baseline volume: 0.14.
   - Ducking reduction during speech: -18.0 dB with attack 20ms, release 350ms.
6. Safe Area Protection:
   - Vertical (9:16): Top margin 330px, bottom margin 330px, lateral margin 72px.
   - Horizontal (16:9): Margin 124px top/bottom, 85px left/right.
7. Output Format: Respond EXCLUSIVELY with the complete, valid scene_manifest.json structure.
```

### 4.4 Input & Output Data Contracts
- **Input Contract:** `cinematic_script.json` + `visual_plan.json` + `word_timestamps.json` + audio duration metadata.
- **Output Contract:** `scene_manifest.json` (Validated against `schemas/scene_planner.schema.json`).

### 4.5 Fail-Closed 3-Tier Fallback Protocol
1. **Tier 1 (Deterministic Timeline Partitioning):** If the LLM compositor fails, execute `src/curators/beats.py:calculate_beat_shot_durations()` to compute exact frame offsets from word timestamp arrays.
2. **Tier 2 (SQLite Loop Catalog Fallback):** If AI asset generation fails for any scene, query `LoopCatalogRepository` (`data/shorts_queue.db:video_loops`) for verified pre-rendered procedural loops matching the theme lane and resolution.
3. **Tier 3 (Fail-Closed Quarantine):** If total scene duration does not reconcile with audio duration within ±0.05 seconds or if safe area margins are violated, abort before rendering.

---

## 5. Agent 4: Visual & Audio QA Auditor (`VisualAudioQAAuditor`)

### 5.1 Mission & Architectural Scope
The **Visual & Audio QA Auditor** performs automated, multi-tiered forensic analysis on the final rendered master MP4 file prior to release. The audit is structured into three stratified tiers:
- **Tier 1: Audio Signal & Psychoacoustic Physics:** Deterministic evaluation of ITU-R BS.1770 / EBU R128 loudness, true peak ceiling, phase correlation, and Goertzel spectral tone filtration.
- **Tier 2: Video Signal & Container Integrity:** Verification of resolution, codec, Rec.709 color profiles, moov atom placement (`+faststart`), minimum average luminance, and freeze-frame detection.
- **Tier 3: Vision Review Bundle (Programmatic Vision AI):** High-level visual audit of keyframe contact sheets for rendering artifacts, macroblocking, anatomical distortions, and subtitle legibility.

### 5.2 Verbatim System Prompt
```markdown
You are the Lead QA Visual & Audio Auditor for a broadcast-grade media pipeline.

### MISSION:
Audit the rendered video review bundle (including keyframe contact sheets, diagnostic JSON, loudness graphs, and timeline events) for visual defects, subtitle rendering errors, compression artifacts, and audio/video sync anomalies.

### AUDIT CHECKLIST:
1. Visual Sharpness & Artifacts: Check for macroblocking, pixelation, severe banding in dark gradients, deformed AI anatomical anomalies, or frozen frames.
2. Perceptual Lighting: Verify that shadows retain textural detail and are not crushed into featureless black voids.
3. Subtitle Synchronization & Placement: Verify that subtitles are centered within safe areas, have strong contrast against background imagery, and contain zero truncated words or OCR typos.
4. Editorial Integrity: Verify zero prompt leaks, zero placeholder text ("<TODO>"), and zero meta-narrative chatter.
5. Verdict Rule: If ANY High-severity defect is found, overall_pass MUST be false.

### Output Format:
Respond EXCLUSIVELY with a valid JSON object matching the qa_audit_report.json schema.
```

### 5.3 Input & Output Data Contracts
- **Input Contract:** `master_render.mp4` path + contact sheet image bundle + probe metadata.
- **Output Contract:** `qa_audit_report.json` (Validated against `schemas/video_qa.schema.json`).

### 5.4 3-Tier Audit Metric Perimeter & Thresholds

| Metric Category | Gate / Test Item | Permitted Threshold / Standard | Severity on Violation | Action on Failure |
|---|---|---|---|---|
| **Audio Physics (Tier 1)** | Integrated Loudness ($I$) | $-14.0 \pm 1.0\text{ LUFS}$ (Acceptable: $[-15.5, -12.5]$) | High | Fail-Closed Reject |
| **Audio Physics (Tier 1)** | True Peak Ceiling ($\text{TP}$) | $\le -1.5\text{ dBTP}$ (Hard Max: $-1.0\text{ dBTP}$) | High | Fail-Closed Reject |
| **Audio Physics (Tier 1)** | Stereo Phase Correlation | $\rho \ge +0.20$ (Zero Mono Inversion) | High | Fail-Closed Reject |
| **Audio Physics (Tier 1)** | Goertzel Narrow Tone Filter | No continuous tone $\ge 15\text{dB}$ prominence lasting $\ge 500\text{ms}$ | Medium/High | Fail-Closed Reject |
| **Video Container (Tier 2)** | Container Resolution | 1920x1080 (16:9) or 1080x1920 (9:16) exactly | High | Fail-Closed Reject |
| **Video Container (Tier 2)** | Color Matrix & Profile | `bt709` / `yuv420p` / High Profile Level 4.2 | High | Fail-Closed Reject |
| **Video Container (Tier 2)** | Faststart Moov Atom | `moov` atom located before `mdat` offset | High | Remux / Reject |
| **Visual Signal (Tier 2)** | Average Perceptual Luminance | $\text{Avg Luminance} \ge 22.0$ (0–255 scale) | High | Fail-Closed Reject |
| **Visual Signal (Tier 2)** | Dark Frame Ratio | $\text{Ratio}(Y < 20) \le 0.45$ | High | Fail-Closed Reject |
| **Visual Signal (Tier 2)** | Continuous Black Screen | Longest black sequence $< 3.0\text{ seconds}$ | High | Fail-Closed Reject |
| **Visual Signal (Tier 2)** | Render Freeze Detection | Inter-frame difference $< 0.5\%$ across $> 2.0\text{ seconds}$ | High | Fail-Closed Reject |
| **Vision AI (Tier 3)** | Compression Macroblocking | Artifact score $< 0.05$ | Medium/High | Quarantine Review |
| **Vision AI (Tier 3)** | Subtitle Margin Lockout | 100% text within Safe Area margins | High | Fail-Closed Reject |

---

## 6. Theme Lane Color Palette & Lighting Matrices

The platform mandates strict aesthetic boundaries for each of its four primary production lanes. The color matrices define the exact 5-color Rec.709 hex quintets, color temperature, key light direction, positive composition rules, and strictly prohibited visual tropes:

```
                                  THEME LANE PALETTE MATRIX
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │ 1. COSMIC HORROR (`cosmic_horror`)                                                     │
 │    Primary:   #0B0B10 (Obsidian Void)       Secondary: #1C1028 (Abyssal Violet)        │
 │    Accent:    #12282D (Eerie Teal)          Shadow:    #050508 (Singularity Black)     │
 │    Highlight: #3A6D7C (Cold Starlight)      Temp:      6500K Cold Daylight             │
 ├────────────────────────────────────────────────────────────────────────────────────────┤
 │ 2. CREEPYPASTA (`creepypasta`)                                                         │
 │    Primary:   #141E18 (Decayed Pine)        Secondary: #1E2022 (Ashen Mist)            │
 │    Accent:    #2C221E (Desaturated Umber)   Shadow:    #0D0F0E (Murky Shadow)          │
 │    Highlight: #8C7B48 (Sodium Vapor)        Temp:      2700K Warm Sodium Tungsten      │
 ├────────────────────────────────────────────────────────────────────────────────────────┤
 │ 3. SCP FOUNDATION (`scp_foundation`)                                                   │
 │    Primary:   #2B2E33 (Brutalist Concrete)  Secondary: #1A1C20 (Tactical Gunmetal)     │
 │    Accent:    #1E6B37 (Muted Phosphor)      Shadow:    #0E1012 (Bunker Black)          │
 │    Highlight: #C87D1A (Hazard Amber)        Temp:      4500K Fluorescent / Amber Strobe│
 ├────────────────────────────────────────────────────────────────────────────────────────┤
 │ 4. DRAMA / AITA (`drama_aita`)                                                         │
 │    Primary:   #1A2230 (Slate Navy)          Secondary: #251E1C (Espresso Charcoal)     │
 │    Accent:    #8A4B4B (Muted Terracotta)    Shadow:    #0F141C (Deep Charcoal)         │
 │    Highlight: #D1C2A5 (Champagne Key)       Temp:      3200K Dual Warm/Cool Split      │
 └────────────────────────────────────────────────────────────────────────────────────────┘
```

### 6.1 Cosmic Horror Lane (`cosmic_horror`)
- **Palette Quintet:**
  * Primary: `#0B0B10` (Obsidian Void)
  * Secondary: `#1C1028` (Abyssal Violet)
  * Accent: `#12282D` (Eerie Teal)
  * Shadow: `#050508` (Singularity Black)
  * Highlight: `#3A6D7C` (Cold Starlight)
- **Lighting Rig:** 6500K Cold Daylight; Bioluminescent Rim & Backlight Silhouette; Volumetric god-ray shafts traversing deep space mist.
- **Positive Aesthetic Rules:** Deep atmospheric perspective, non-Euclidean curved geometry, subtle chromatic aberration on perimeter lenses, velvety smooth dark gradients, monolithic scale.
- **Negative Aesthetic Rules (FORBIDDEN):**
  * NO saturated neon magenta or psychedelic rainbow solar flares.
  * NO cartoonish alien green or glowing green slime tropes.
  * NO crushed void zones ($Y < 16$) that erase starfield textures.
  * NO video game health bars or HUD overlays.

### 6.2 Creepypasta Lane (`creepypasta`)
- **Palette Quintet:**
  * Primary: `#141E18` (Decayed Pine)
  * Secondary: `#1E2022` (Ashen Mist)
  * Accent: `#2C221E` (Desaturated Umber)
  * Shadow: `#0D0F0E` (Murky Shadow)
  * Highlight: `#8C7B48` (Sodium Vapor)
- **Lighting Rig:** 2700K Warm Tungsten / Sodium Vapor; Single-point chiaroscuro key from high angle or low under-chin flashlight angle; Dense ground fog diffusion.
- **Positive Aesthetic Rules:** Organic decaying textures (damp wood, peeling wallpaper, rusted iron), naturalistic atmospheric fog, shallow depth of field (f/1.4), slow deliberate camera dolly.
- **Negative Aesthetic Rules (FORBIDDEN):**
  * NO bright cheerful daylight scenes or sun-drenched pastoral landscapes.
  * NO cartoonish saturated bright red blood splatter overlays.
  * NO cheap internet meme jump-scare monster faces.
  * NO flat, unshaded 3D blender renders.

### 6.3 SCP Foundation Lane (`scp_foundation`)
- **Palette Quintet:**
  * Primary: `#2B2E33` (Brutalist Concrete)
  * Secondary: `#1A1C20` (Tactical Gunmetal)
  * Accent: `#1E6B37` (Muted Phosphor)
  * Shadow: `#0E1012` (Bunker Black)
  * Highlight: `#C87D1A` (Hazard Amber)
- **Lighting Rig:** 4500K Overhead Industrial Fluorescent & Emergency Amber Strobe; Harsh geometric cast shadows; Subtle high-frequency CRT phosphor flicker.
- **Positive Aesthetic Rules:** Brutalist concrete architecture, reinforced steel blast doors, sterile laboratory equipment, high-contrast security surveillance framing, crisp telemetry overlays, monospace classification stamps.
- **Negative Aesthetic Rules (FORBIDDEN):**
  * NO gamer RGB rainbow backlighting or saturated purple gaming room aesthetics.
  * NO unreadable, low-resolution VHS noise that obscures critical text.
  * NO informal, playful, or rounded cartoon typography.
  * NO high-fantasy magical particle bursts.

### 6.4 Drama / AITA Lane (`drama_aita`)
- **Palette Quintet:**
  * Primary: `#1A2230` (Slate Navy)
  * Secondary: `#251E1C` (Espresso Charcoal)
  * Accent: `#8A4B4B` (Muted Terracotta)
  * Shadow: `#0F141C` (Deep Charcoal)
  * Highlight: `#D1C2A5` (Champagne Key)
- **Lighting Rig:** 3200K Studio Softbox Key paired with a subtle 5600K Cool Rim (Split Emotional Lighting); Delicate atmospheric backlight wrap.
- **Positive Aesthetic Rules:** Sophisticated cinematic interior lighting, shallow depth of field focusing on emotional subject isolation, clean modern typography, smooth harmonic sine wave accents, warm/cool dual-tone color contrast.
- **Negative Aesthetic Rules (FORBIDDEN):**
  * NO washed-out, overexposed daytime soap opera lighting.
  * NO muddy, lifeless monochromatic gray grades.
  * NO horror glitch artifacts, fake camera shaking, or blood splatters.
  * NO garish, oversaturated pop-art primary colors.

---

## 7. Unified Schema Reference Map

The schemas governing all agent I/O contracts are formally defined in Draft-07 JSON Schema files within the repository:

1. `schemas/script_curator.schema.json` — Defines `CinematicScript` (4 acts, scenes, tension ratings 1..5, neutral Spanish narration, word counts).
2. `schemas/art_director.schema.json` — Defines `VisualPlan` (theme lane, global LUT, per-scene 5-color Rec.709 palettes, lighting rigs, atmosphere, framing, positive/negative prompts).
3. `schemas/scene_planner.schema.json` — Defines `SceneManifest` (canvas resolution, fps, duration, audio sidechain ducking, safe area margins, scenes with engine configs, transitions, and subtitles).
4. `schemas/video_qa.schema.json` — Defines `QAAuditReport` (overall pass/fail, 0-100 quality score, Tier 1 audio physics metrics, Tier 2 visual container metrics, Tier 3 vision AI review findings, and rejection reasons).
