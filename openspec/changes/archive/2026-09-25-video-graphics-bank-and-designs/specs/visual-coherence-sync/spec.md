# Visual Coherence and Script Synchronization Specification (Delta)

## Purpose
Defines the visual coherence subsystem governing narrative beat synchronization, brand-aligned filmic color grading, vertical mobile UI safe-zone enforcement, deterministic 3-tier asset lifecycle resolution, graphic overlay safe-zone and opacity coherence, and pre-render continuity validation across image and video modalities.

## ADDED Requirements

### Requirement: Overlay Safe Zone and Opacity Coherence (`overlay_safe_zone_and_opacity_coherence`)
The system MUST enforce that all graphic overlays, vector HUD templates, and static atmospheric textures registered in the graphics bank or injected during composition adhere strictly to mobile platform safe-zone boundaries and atmospheric opacity clamping rules.

1. **Safe-Zone Geometry Enforcement**:
   - For vertical 9:16 canvases ($1080\times 1920$):
     - All critical graphic text, telemetry readouts, status icons, and bounding cards MUST be contained within the safe area:
       - Bottom margin: $MarginV_{bottom} \ge 460\text{px}$ (elements MUST NOT extend below $y = 1460\text{px}$, preventing occlusion by YouTube Shorts title, sound pill, and seekbar).
       - Top margin: $MarginV_{top} \ge 180\text{px}$ (elements MUST NOT extend above $y = 180\text{px}$, protecting against platform header and search controls).
       - Right margin: $MarginH_{right} \ge 130\text{px}$ (elements MUST NOT extend right of $x = 950\text{px}$, protecting against vertical like/comment/share/remix action buttons).
       - Left margin: $MarginH_{left} \ge 64\text{px}$ (elements MUST NOT extend left of $x = 64\text{px}$).
   - For horizontal 16:9 canvases ($1920\times 1080$):
     - Elements MUST be bounded by $MarginV_{bottom} \ge 120\text{px}$, $MarginV_{top} \ge 80\text{px}$, and lateral $MarginH \ge 80\text{px}$.

2. **Atmospheric Opacity Clamping (`clamp_atmospheric_overlay_opacity`)**:
   - Atmospheric overlay textures (`dark_vignette`, `soft_vignette`, `film_grain`, `tv_static`, `particles`, `particles_dust`, `particles_embers`, `god_rays`) MUST have their operational opacity clamped to the range $[0.15, 0.35]$ (canonical default $0.25$).
   - If a visual plan or scene config requests an opacity $> 0.35$, the value MUST be clamped to $0.35$ to prevent obscuring underlying narrative imagery, subject faces, and subtitle readability.
   - If a requested opacity is $< 0.15$ (and non-zero), the value MUST be clamped to $0.15$ to ensure that composited textures remain perceptible and do not waste FFmpeg filter processing cycles.
   - A requested opacity of `0.0` or `None` SHALL disable the atmospheric overlay entirely.

#### Scenario: Opacity clamping within permissible band (Happy Path)
- **Given** an atmospheric overlay request with `opacity=0.28`
- **When** `clamp_atmospheric_overlay_opacity(0.28)` is invoked
- **Then** the returned opacity MUST be exactly `0.28`.

#### Scenario: Opacity clamping for atmospheric overlay exceeding maximum (Happy Path)
- **Given** an atmospheric overlay request with `opacity=0.65`
- **When** `clamp_atmospheric_overlay_opacity(0.65)` is invoked
- **Then** the returned opacity MUST be clamped to `0.35`
- **And** the narration subtitle layer MUST remain clearly legible.

#### Scenario: Opacity clamping for atmospheric overlay below minimum (Happy Path)
- **Given** an atmospheric overlay request with `opacity=0.05`
- **When** `clamp_atmospheric_overlay_opacity(0.05)` is invoked
- **Then** the returned opacity MUST be raised to `0.15`.

#### Scenario: Safe-zone validation of 9:16 vector HUD overlay elements (Happy Path)
- **Given** an SVG overlay preset `rec_analog_hud` for vertical canvas $1080\times 1920$
- **When** evaluated against safe zone bounds
- **Then** all top telemetry elements MUST reside at $y \ge 180\text{px}$
- **And** all bottom timestamp elements MUST reside at $y \le 1460\text{px}$
- **And** lateral elements MUST reside between $x = 64\text{px}$ and $x = 950\text{px}$
- **And** the asset MUST be verified as `safe_zone_compliant: True`.

#### Scenario: Detection and rejection of safe-zone boundary violation in vector HUD (Edge Case)
- **Given** a candidate vector HUD containing interactive text placed at $y = 1600\text{px}$ ($MarginV_{bottom} = 320\text{px} < 460\text{px}$)
- **When** `GraphicsBank.validate_bank()` or safe-zone linting checks the asset
- **Then** the system MUST flag the asset as non-compliant (`safe_zone_compliant: False`)
- **And** rendering engines MUST reject or reposition the overlay on vertical mobile channels.

---

## MODIFIED Requirements

### Requirement: Mobile UI Safe-Zone Viewport Bounding (`enforce_shorts_safe_zone`)
(Previously: Governed subtitle and character framing safe zones without explicit coordination with graphics bank vector HUDs and framing templates)

The system MUST compute and enforce strict mobile UI safe-zone margins for vertical 9:16 Shorts ($1080\times 1920$) and horizontal 16:9 videos ($1920\times 1080$) via `enforce_shorts_safe_zone()`. All on-screen graphical elements—including kinetic ASS subtitles, vector HUD overlays, graphic framing badges, typography cards, and focal character subjects—MUST remain within the computed safe area to prevent occlusion by platform UI overlays (YouTube Shorts action buttons, channel avatars, sound icons, descriptions, and seek bars).

For vertical 9:16 canvases, the safe zone MUST enforce:
- Bottom margin: $MarginV \ge 460\text{px}$ (canonical $\ge 25\%$ of canvas height, protecting against description and sound titles)
- Top margin: $MarginV_{top} \ge 180\text{px}$ (canonical $\ge 10\%$ of canvas height, protecting against header controls)
- Right margin: $MarginH_{right} \ge 130\text{px}$ (protecting against vertical like/comment/share buttons)
- Left margin: $MarginH_{left} \ge 64\text{px}$

For horizontal 16:9 canvases, the safe zone MUST enforce:
- Bottom margin: $MarginV \ge 120\text{px}$
- Top margin: $MarginV_{top} \ge 80\text{px}$
- Lateral margins: $MarginH \ge 80\text{px}$

#### Scenario: Vertical 9:16 Shorts safe zone computation for graphic overlays (Happy Path)
- **Given** a canvas resolution of width 1080 and height 1920
- **When** `enforce_shorts_safe_zone(1080, 1920)` is invoked
- **Then** the returned margin dictionary MUST have `bottom >= 460`
- **And** `top >= 180`
- **And** `right >= 130`
- **And** `left >= 64`
- **And** `safe_width` MUST equal `1080 - (left + right)`
- **And** `safe_height` MUST equal `1920 - (top + bottom)`.

#### Scenario: Horizontal 16:9 Longform safe zone computation for graphic overlays (Happy Path)
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
