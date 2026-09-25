# Visual Coherence and Script Synchronization Specification

## Purpose
Defines the visual coherence subsystem governing narrative beat synchronization, brand-aligned filmic color grading, vertical mobile UI safe-zone enforcement, deterministic 3-tier asset lifecycle resolution, and pre-render continuity validation across image and video modalities.

## Requirements

### Requirement: Narrative Beat and Act Timing Synchronization (`timing_scales_to_audio`)
The system MUST synchronize visual scene pacing and act transitions with voiceover narration audio. Scene durations calculated by `timing_scales_to_audio()` in `src/media/visual_coherence.py` SHALL be proportionally scaled so that total visual presentation duration matches probed narration audio duration within $\pm 0.05\text{ seconds}$. Scene cuts MUST align with natural speech pauses and narrative act boundaries without introducing visual-audio drift. The final scene in a sequence SHALL absorb any residual rounding difference to ensure exact duration equality.

#### Scenario: Proportional scene duration scaling to audio duration (Happy Path)
- **Given** raw scene durations `[3.0, 4.0, 5.0]` (total 12.0 seconds) from narrative script acts
- **And** probed voiceover narration audio with duration of 15.0 seconds
- **When** `timing_scales_to_audio([3.0, 4.0, 5.0], 15.0)` is invoked
- **Then** the scaled durations MUST be proportionally expanded to `[3.75, 5.0, 6.25]`
- **And** the sum of scaled scene durations MUST equal 15.0 seconds within $\pm 0.05\text{ seconds}$
- **And** no individual scene duration SHALL be less than 1.0 second.

#### Scenario: Degenerate or non-positive audio duration fallback (Edge Case)
- **Given** raw scene durations `[4.0, 5.0, 6.0]`
- **And** a target audio duration that is `None`, `0.0`, or negative
- **When** `timing_scales_to_audio` is invoked
- **Then** the system MUST return the raw scene durations unmodified
- **And** the system MUST NOT raise an exception or divide by zero.

#### Scenario: Rounding residual absorption by final scene (Edge Case)
- **Given** three scenes with raw durations `[3.33, 3.33, 3.33]` and a target duration of 10.0 seconds
- **When** `timing_scales_to_audio` scales and rounds durations to 2 decimal places
- **Then** any fractional rounding discrepancy between the sum of scaled scenes and target duration MUST be added to or subtracted from the final scene
- **And** the total duration MUST exactly equal 10.00 seconds.

### Requirement: Filmic Brand-Aligned Color Grading (`build_coherent_color_grade`)
The system MUST generate channel-specific and mood-harmonized Rec.709 color grading filter expressions via `build_coherent_color_grade()` to unify disparate still imagery and stock loop footage into a single aesthetic identity. Color grading filters MUST be injected directly into FFmpeg filterchains (`eq` and `colorbalance` clauses) without crushing blacks or blowing out highlights.

The color curves SHALL adhere to the following channel identities:
1. `horror` (and legacy alias `moku`): moody dark ambient, subdued saturation ($0.88$), neutral brightness ($0.00$), gamma ($0.97$), and crisp shadow balance (`rs=-0.02:gs=0.01:bs=0.02`).
2. `drama` (and legacy alias `aelithia`): warm cinematic hearth tones, lifelike skin tones, contrast ($1.05$), saturation ($0.96$), brightness ($0.01$), gamma ($0.98$), and warm midtone/shadow balance (`rs=0.02:gs=0.01:bs=-0.03`).
3. `scifi`: deep space blacks, cool cyan shadow lift, high micro-contrast ($1.08$), saturation ($0.92$), brightness ($-0.01$), gamma ($0.95$), and cyan-blue balance (`rs=-0.03:gs=0.01:bs=0.04:rh=-0.02:gh=0.02:bh=0.05`).

#### Scenario: Filmic color grade generation for Horror channel (Happy Path)
- **Given** channel identifier `"horror"` or legacy `"moku"`
- **When** `build_coherent_color_grade(channel="horror")` is executed
- **Then** it MUST return an FFmpeg filter expression containing `eq=contrast=1.06:saturation=0.88`
- **And** it MUST contain `colorbalance` with cool shadow offsets `rs=-0.02:gs=0.01:bs=0.02`.

#### Scenario: Filmic color grade generation for Drama channel (Happy Path)
- **Given** channel identifier `"drama"` or legacy `"aelithia"`
- **When** `build_coherent_color_grade(channel="drama")` is executed
- **Then** it MUST return an FFmpeg filter expression containing `eq=contrast=1.05:saturation=0.96:brightness=0.01`
- **And** it MUST contain warm skin tone balance offsets `rs=0.02:gs=0.01:bs=-0.03`.

#### Scenario: Filmic color grade generation for SciFi channel (Happy Path)
- **Given** channel identifier `"scifi"` or `"singularidad"`
- **When** `build_coherent_color_grade(channel="scifi")` is executed
- **Then** it MUST return an FFmpeg filter expression containing `eq=contrast=1.08:saturation=0.92:brightness=-0.01`
- **And** it MUST contain cyan/blue shadow and highlight lift `bs=0.04` and `bh=0.05`.

#### Scenario: Default fallback for unknown or empty channel (Edge Case)
- **Given** an unknown channel string `"unknown_niche"` or an empty string `""`
- **When** `build_coherent_color_grade` is executed
- **Then** the function MUST default safely to the dark ambient horror color grade
- **And** it MUST emit a valid FFmpeg filter string without raising a `KeyError`.

### Requirement: Mobile UI Safe-Zone Viewport Bounding (`enforce_shorts_safe_zone`)
The system MUST compute and enforce strict mobile UI safe-zone margins for vertical 9:16 Shorts ($1080\times 1920$) and horizontal 16:9 videos ($1920\times 1080$) via `enforce_shorts_safe_zone()`. All on-screen graphical elements (kinetic ASS subtitles, HUD overlays, typography badges, and focal character subjects) MUST remain within the computed safe area to prevent occlusion by platform UI overlays (YouTube Shorts action buttons, channel avatars, sound icons, descriptions, and seek bars).

For vertical 9:16 canvases, the safe zone MUST enforce:
- Bottom margin: $MarginV \ge 460\text{px}$ (canonical $\ge 25\%$ of canvas height, protecting against description and sound titles)
- Top margin: $MarginV_{top} \ge 180\text{px}$ (canonical $\ge 10\%$ of canvas height, protecting against header controls)
- Right margin: $MarginH_{right} \ge 130\text{px}$ (protecting against vertical like/comment/share buttons)
- Left margin: $MarginH_{left} \ge 64\text{px}$

For horizontal 16:9 canvases, the safe zone MUST enforce:
- Bottom margin: $MarginV \ge 120\text{px}$
- Top margin: $MarginV_{top} \ge 80\text{px}$
- Lateral margins: $MarginH \ge 80\text{px}$

#### Scenario: Vertical 9:16 Shorts safe zone computation (Happy Path)
- **Given** a canvas resolution of width 1080 and height 1920
- **When** `enforce_shorts_safe_zone(1080, 1920)` is invoked
- **Then** the returned margin dictionary MUST have `bottom >= 460`
- **And** `top >= 180`
- **And** `right >= 130`
- **And** `left >= 64`
- **And** `safe_width` MUST equal `1080 - (left + right)`
- **And** `safe_height` MUST equal `1920 - (top + bottom)`.

#### Scenario: Horizontal 16:9 Longform safe zone computation (Happy Path)
- **Given** a canvas resolution of width 1920 and height 1080
- **When** `enforce_shorts_safe_zone(1920, 1080)` is invoked
- **Then** the returned margin dictionary MUST have `bottom >= 120`
- **And** `top >= 80`
- **And** `left >= 80`
- **And** `right >= 80`
- **And** `safe_width` MUST equal `1920 - 160` (1760px).

#### Scenario: Arbitrary non-standard aspect ratio bounding (Edge Case)
- **Given** an arbitrary non-standard resolution such as $720\times 1280$
- **When** `enforce_shorts_safe_zone(720, 1280)` evaluates the geometry
- **Then** it MUST identify the vertical orientation ($height > width$)
- **And** dynamically scale margins to at least $25\%$ bottom and $10\%$ top
- **And** ensure `safe_width` and `safe_height` are strictly positive integers.

### Requirement: Deterministic 3-Tier Asset Resolution Lifecycle
The system MUST resolve visual assets for each scene through a 3-tier deterministic local resolution hierarchy:
1. **Tier 1 (Curated Local Bank)**: Exact or semantic keyword match from curated physical assets (`assets/loops/` or channel asset banks).
2. **Tier 2 (Canonical Cached Worksets)**: High-resolution cached assets from previous successful runs indexed in local run data.
3. **Tier 3 (Contextual Local Template Fallback)**: Immediate deterministic fallback to validated continuous catalog loops.

Asset resolution MUST NOT invoke external network requests, Playwright browsers, or unauthenticated cloud endpoints. If an asset resolution tier fails, times out, or yields an unreadable file, the system MUST cascade to the next tier deterministically without failing the pipeline.

#### Scenario: Direct Tier 1 asset match resolution (Happy Path)
- **Given** a scene requesting theme `"scp_containment"`
- **And** an existing video loop in `assets/loops/` matching the theme
- **When** the asset resolver processes the scene
- **Then** it MUST resolve the asset to the Tier 1 file path
- **And** no network calls or cache lookups SHALL be initiated.

#### Scenario: Tier 2 cache hit on missing Tier 1 asset (Happy Path)
- **Given** a scene requesting a visual matte not present in Tier 1 curated bank
- **And** a matching cached asset present in Tier 2 cached worksets
- **When** the asset resolver processes the scene
- **Then** it MUST resolve the asset from the local workset cache
- **And** verify file readability and valid aspect ratio.

#### Scenario: Tier 3 deterministic fallback upon missing or corrupted asset (Edge Case)
- **Given** a scene requesting an asset that fails Tier 1 and Tier 2 resolution or times out
- **When** the asset resolver cascades to Tier 3
- **Then** it MUST select a validated continuous catalog loop corresponding to the channel theme
- **And** the pipeline run MUST continue to completion without raising an unhandled exception.

### Requirement: Pre-Render Continuity and Sanity Verification (`validate_visual_continuity`)
The system MUST perform pre-render validation of scene sequences via `validate_visual_continuity()` before passing manifests to rendering engines. The continuity validator MUST verify that:
1. The scene list is non-empty.
2. Every scene has a strictly positive duration ($duration > 0.0\text{ seconds}$).
3. Narrative tension progression is well-formed ($1 \le tension \le 5$).
4. Tension-aware transition durations are computed for all adjacent scene boundaries.

If any continuity rule is violated, the function MUST return `valid: False` with a structured `reason` code.

#### Scenario: Valid scene sequence continuity validation (Happy Path)
- **Given** a list of 4 scene objects with durations `[4.0, 5.0, 3.5, 6.0]` and valid tension levels
- **When** `validate_visual_continuity(scenes)` is executed
- **Then** the returned dictionary MUST indicate `valid: True`
- **And** `scene_count` MUST equal 4
- **And** `total_duration` MUST equal 18.5 seconds
- **And** `recommended_transitions` MUST contain exactly 3 transition duration values.

#### Scenario: Rejection of zero or negative scene duration (Edge Case)
- **Given** a scene sequence containing a scene with duration `0.0` or `-2.5` seconds
- **When** `validate_visual_continuity(scenes)` is executed
- **Then** the returned dictionary MUST indicate `valid: False`
- **And** the `reason` code MUST be `"zero_or_negative_duration"`
- **And** the render pipeline MUST halt before dispatching FFmpeg transcoding.

#### Scenario: Rejection of empty scene sequence (Edge Case)
- **Given** an empty scene sequence `[]`
- **When** `validate_visual_continuity(scenes)` is executed
- **Then** the returned dictionary MUST indicate `valid: False`
- **And** the `reason` code MUST be `"empty_scenes"`.
