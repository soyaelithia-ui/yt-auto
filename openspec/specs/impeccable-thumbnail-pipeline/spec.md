# Impeccable Thumbnail Pipeline Specification

## Purpose
The `impeccable-thumbnail-pipeline` capability delivers automated, high-CTR, niche-tailored YouTube thumbnails. It replaces rudimentary PIL vector silhouettes and heavy blur with modular layouts (analog VHS + general cinematic fallback; former scp/reddit thumbnail modules removed), 3D multi-pass typography, and local-first thematic asset sourcing.

## Requirements

### Requirement: Niche Layout Dispatch & Thematic Compositing
The system MUST dispatch thumbnail composition to specialized layout engines based on channel profile, lane, and narrative archetype.

#### Scenario: Former SCP/Reddit lanes fall back to cinematic (Happy Path)
- **GIVEN** a generation request for former scp/reddit lane ids (e.g. `moku-scp-shorts`, `aelithia-aita-long`)
- **WHEN** the thumbnail engine resolves a layout via `LayoutRegistry.get_layout`
- **THEN** it MUST fall back to `GeneralCinematicLayout` (dedicated `scp_hud` / `reddit_card` modules removed).

#### Scenario: Analog Horror Longform thumbnail composition (Happy Path)
- **GIVEN** a horizontal 16:9 generation request for lane `moku-horror-long`
- **WHEN** the thumbnail engine generates the image
- **THEN** it MUST render `AnalogHorrorVhsLayout` with a camcorder REC indicator, audio frequency badge, CRT scanlines, and classified tape badge.

#### Scenario: Unknown channel archetype fallback (Edge Case)
- **GIVEN** a channel or archetype without a custom layout
- **WHEN** the thumbnail engine generates the image
- **THEN** it MUST fall back to `GeneralCinematicLayout` with high-contrast chiaroscuro grading and 3D typography without crashing.

### Requirement: Multi-Pass 3D Typography Rendering
The typography engine MUST render text hooks using a 4-pass composition: ambient diffuse glow, directional 3D drop shadow, sharp exterior stroke, and high-visibility foreground fill.

#### Scenario: High-contrast 3D text generation (Happy Path)
- **GIVEN** a canvas and hook text string
- **WHEN** `draw_text_with_effects` executes
- **THEN** the text MUST be rendered with drop shadow offset $(8, 12)$, stroke width $\ge 10\text{px}$, and Gaussian-blurred ambient glow.

#### Scenario: Multi-line dramatic title splitting (Edge Case)
- **GIVEN** an interrogative or exclamatory title exceeding 30 characters
- **WHEN** dynamic line breaking executes
- **THEN** the engine MUST split the text into 2 or 3 distinct vertical lines sized to remain strictly within the canvas safe zone.

### Requirement: Thematic Asset Resolution Hierarchy
The asset resolver MUST resolve base imagery through a 3-tier hierarchy: (1) explicit path, (2) curated local thematic asset bank, (3) video climax frame with Chiaroscuro grading, and SHALL NOT draw primitive vector stick-figures.

#### Scenario: Curated local asset resolution (Happy Path)
- **GIVEN** no explicit `base_image_path` and an active lane `moku-scp-shorts`
- **WHEN** the asset resolver locates background imagery
- **THEN** it MUST select an authentic high-resolution backdrop from `assets/thumbnails/templates/scp/` or `assets/visual_bank/`.

#### Scenario: Video climax fallback without primitive silhouettes (Edge Case)
- **GIVEN** an empty asset bank and an active video file
- **WHEN** fallback extraction executes
- **THEN** it MUST extract the climax keyframe and apply Chiaroscuro grading without drawing PIL polygon stick figures.

### Requirement: YouTube Safe Zone Enforcement
The thumbnail generator MUST keep all critical text and badges clear of video player UI overlays.

#### Scenario: 16:9 player badge clearance
- **GIVEN** a 1920x1080 thumbnail canvas
- **WHEN** layout badges and text are positioned
- **THEN** zero graphic elements SHALL intersect the bottom-right timestamp zone $[1570, 930, 1920, 1080]$.

#### Scenario: 9:16 Shorts UI clearance
- **GIVEN** a 1080x1920 vertical canvas
- **WHEN** layout badges and text are positioned
- **THEN** zero graphic elements SHALL intersect the bottom $450\text{px}$ or the right $120\text{px}$ interaction rail.
