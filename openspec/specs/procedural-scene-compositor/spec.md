# Specification: Procedural Scene Compositor

## Capability Overview
The `procedural-scene-compositor` capability orchestrates code-driven multi-scene video rendering using dynamic GLSL fragment shaders, Three.js/WebGL canvases, procedural particle systems, 2.5D camera drift transformations, and frame-accurate FFmpeg `xfade` transitions. It provides 100% code-driven visual synthesis without dependencies on external static image scraping.

## Requirements

### Requirement 1: Dynamic GLSL Shader Compositing and Uniform Injection
The compositor MUST execute multi-scene shader pipelines, dynamically injecting per-frame and per-scene uniforms including normalized elapsed time (`u_time`), canvas dimensions (`u_resolution`), narrative tension level (`u_tension`), and Rec.709 color vector arrays (`u_palette_primary`, `u_palette_accent`).

#### Scenario: Procedural shader scene rendering with active uniform injection (Happy Path)
- **Given** a scene contract specifying shader archetype `"GRAVITATIONAL_SINGULARITY"` with tension level 4
- **When** the compositor renders the scene frame sequence
- **Then** the engine MUST pass dynamic uniform values (`u_tension = 4.0`, `u_time`, `u_resolution`) to the GLSL pipeline
- **And** the rendered frames MUST reflect procedural geometry without static asset lookups.

#### Scenario: Shader compilation failure or missing uniform fallback (Edge Case)
- **Given** an invalid shader definition or compilation syntax error in a custom shader string
- **When** the WebGL/GLSL context compiles the program
- **Then** the compositor MUST catch the compilation error and fall back to the safe baseline shader (`"MONOLITHS_RAYMARCHING"`)
- **And** the compositor MUST log a warning while continuing frame rendering without pipeline abort.

### Requirement 2: 2.5D Procedural Camera Drift and Parallax Motion
The compositor MUST apply continuous 2.5D camera drift transformations across every rendered scene. The camera controller MUST compute smooth translational pan ($dx, dy$), subtle rotational oscillation ($\text{roll} \le 1.5^\circ$), and continuous scale zoom ramps ($\Delta s \in [1.00, 1.15]$) over the scene duration.

#### Scenario: Smooth camera drift execution across scene timeline (Happy Path)
- **Given** a 12.0-second scene rendered at 1080x1920 portrait resolution
- **When** the camera controller generates the per-frame transform matrix
- **Then** the camera translation and zoom MUST follow a continuous non-zero motion vector
- **And** the velocity curve MUST use cubic or cosine easing without sudden discontinuous jumps between adjacent frames.

#### Scenario: Extended scene duration bounding to prevent border clipping (Edge Case)
- **Given** a long scene duration ($> 30.0\text{s}$) where cumulative camera drift could exceed canvas coverage
- **When** transform calculations are evaluated
- **Then** the controller MUST clamp translation displacement within safe maximum offsets ($\le 8\%$ of frame dimensions)
- **And** the rendered frame MUST NOT expose unrendered canvas boundaries or black margins.

### Requirement 3: Volumetric Particle System Simulation
The compositor MUST generate and overlay dynamic volumetric particle systems (such as atmospheric dust motes, bio-luminescent embers, or digital telemetry static) whose velocity, count, and turbulence scale proportionally with the scene's tension level ($T \in [1, 5]$).

#### Scenario: Tension-scaled particle density during dramatic escalation (Happy Path)
- **Given** a scene transitioning from tension $T = 2$ to tension $T = 5$
- **When** the particle generator simulates the overlay layer
- **Then** particle velocity and perturbation frequency MUST scale monotonically with tension score
- **And** maximum particle count MUST remain bounded ($\le 600\text{ particles}$) to ensure real-time render stability.

#### Scenario: Particle rendering under resource constraint (Edge Case)
- **Given** a resource-constrained execution environment or high-resolution render pass
- **When** frame render latency exceeds target frame budget ($\ge 33.3\text{ms}$)
- **Then** the particle emitter MUST dynamically downscale particle count to baseline ($150\text{ particles}$)
- **And** the compositor MUST maintain target video frame rate without dropping frames.

### Requirement 4: Zero-Drop Seamless Crossfade (`xfade`) Transitions
The compositor MUST join sequential scene video buffers into a unified video stream using FFmpeg `xfade` filter transitions with durations between 0.5s and 1.5s (default 0.75s). The compositor MUST compute exact frame counts and cumulative offsets to guarantee 0 dropped frames and strict audio-video synchronization.

#### Scenario: Multi-scene sequential crossfade composition (Happy Path)
- **Given** 3 sequential rendered scenes with durations 10.0s, 12.0s, and 14.0s with transition duration 0.75s
- **When** `MultiActVideoRenderer` executes the FFmpeg `xfade` filtergraph
- **Then** the output video duration MUST equal exactly $10.0 + 12.0 + 14.0 - (2 \times 0.75) = 34.5\text{s}$
- **And** the output video stream MUST contain zero freeze frames or black frames at transition boundaries.

#### Scenario: Short scene duration collision with transition duration (Edge Case)
- **Given** a short scene duration of 1.0s and a requested transition duration of 0.75s ($2 \times 0.75\text{s} > 1.0\text{s}$)
- **When** the transition planner validates the filtergraph
- **Then** the compositor MUST automatically clamp the transition duration to at most $\le 30\%$ of the shortest adjacent scene duration
- **And** the FFmpeg filtergraph MUST construct valid non-negative `offset` parameters.

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
