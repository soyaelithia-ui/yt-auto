# Delta for Procedural Scene Compositor

## ADDED Requirements

### Requirement 5: Photometric Luminance Floor and Gamma Calibration
All procedural WGSL shaders (including nocturnal, maritime, and cosmic archetypes) MUST enforce a minimum baseline luminance floor of at least 0.15 (15% normalized luminance) across background scenery, silhouettes, and horizons. Rendered frames MUST be encoded with standard sRGB gamma transfer characteristics to prevent black crushing on mobile OLED displays.

#### Scenario: Low-key atmospheric shader enforces luminance floor (Happy Path)
- **Given** the `maritime_lighthouse` or `cosmic_horror` shader rendering a nocturnal scene
- **When** the fragment shader evaluates background pixels outside direct light sources
- **Then** the ambient pixel luminance value MUST NOT fall below 0.15
- **And** horizon silhouettes and ocean wave textures MUST remain distinguishable.

#### Scenario: Peak highlight preservation without clipping (Edge Case)
- **Given** a scene with intense localized light beams (e.g. lighthouse lantern at night)
- **When** tone-mapping and luminance adjustments are applied
- **Then** highlight regions MUST retain gradient falloff without harsh white saturation clipping.

### Requirement 6: WebGPU 64-Byte Uniform Buffer Layout Adapter
The native procedural engine MUST map high-level art director parameters (tension score, color temperature, palette vectors, speed multiplier) into the rigid 64-byte (16 float32) WebGPU uniform buffer layout matching WGSL shader struct definitions without causing buffer size or alignment violations.

#### Scenario: Art director visual parameters translated to uniform struct (Happy Path)
- **Given** an art direction specification with tension $T = 4$, Kelvin temperature $4500\text{K}$, and primary accent hex `#ff6600`
- **When** the uniform adapter packs the buffer for `NativeProceduralEngine`
- **Then** the resulting byte buffer MUST measure exactly 64 bytes
- **And** packed float positions MUST match WGSL shader struct layout definitions.

#### Scenario: Missing optional art director attributes (Edge Case)
- **Given** a visual contract omitting color temperature or tension values
- **When** the uniform buffer is assembled
- **Then** the adapter MUST populate safe default constants (e.g. $T = 2.0$, $5500\text{K}$) without failing.

### Requirement 7: Native Multi-Scene Compositor Delegation
`MultiSceneCompositor` MUST delegate individual scene rendering directly to `NativeProceduralEngine` (WebGPU / Mesa Lavapipe) with bounded task concurrency ($N \le 2$ concurrent scene render jobs) rather than falling back to CPU-based PIL generation.

#### Scenario: Multi-scene render executes via native procedural engine (Happy Path)
- **Given** a scene manifest containing 6 sequential procedural scenes
- **When** `MultiSceneCompositor` renders the video sequence
- **Then** each scene MUST be rendered by `NativeProceduralEngine`
- **And** maximum concurrent worker threads MUST NOT exceed the configured concurrency ceiling.
