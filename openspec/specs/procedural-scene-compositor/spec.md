# Specification: Procedural Scene Compositor

## Capability Overview
The `procedural-scene-compositor` capability orchestrates code-driven multi-scene video rendering using FFmpeg lavfi/catalog procedural loops, concat demuxer stream-copy when homogeneous, `DIRECTOR_SINGLE_PASS` assembly, and FFmpeg `drawtext`/`drawbox` HUD. NativeProceduralEngine, WebGPU, GLSL, and WebGL MAY run only when `ENABLE_NATIVE_PROCEDURAL` is explicitly enabled and MUST stay quarantined under `src/media/_legacy`. It provides 100% code-driven visual synthesis without dependencies on external static image scraping.

## Requirements

### Requirement 1: Dynamic GLSL Shader Compositing and Uniform Injection
Production scene synthesis MUST use FFmpeg lavfi/catalog procedural loops. GLSL/WebGL pipelines and uniform injection (`u_time`, `u_resolution`, `u_tension`, `u_palette_primary`, `u_palette_accent`) MAY run only when `ENABLE_NATIVE_PROCEDURAL` is explicitly enabled and MUST stay quarantined under `src/media/_legacy`. Production MUST NOT require a WebGL/GLSL context.

#### Scenario: Production scenes render via FFmpeg without GLSL
- **Given** `ENABLE_NATIVE_PROCEDURAL` is unset
- **When** the compositor renders a procedural scene
- **Then** frames MUST be produced via FFmpeg lavfi/catalog
- **And** a WebGL/GLSL context MUST NOT be required.

#### Scenario: GLSL remains opt-in (Edge Case)
- **Given** `ENABLE_NATIVE_PROCEDURAL` is enabled
- **When** the quarantined native engine renders
- **Then** GLSL/WebGL MAY run from `src/media/_legacy`
- **And** production defaults MUST remain FFmpeg when the flag is unset.

### Requirement 2: 2.5D Procedural Camera Drift and Parallax Motion
Opt-in native procedural rendering MAY apply continuous 2.5D camera drift: translational pan ($dx, dy$), rotational oscillation ($\text{roll} \le 1.5^\circ$), and scale zoom ramps ($\Delta s \in [1.00, 1.15]$). Production FFmpeg lavfi/catalog loops MUST NOT require a WebGL camera controller.

#### Scenario: Production loops do not require a WebGL camera
- **Given** `ENABLE_NATIVE_PROCEDURAL` is unset
- **When** FFmpeg lavfi/catalog loops render
- **Then** a WebGL camera controller MUST NOT be required.

### Requirement 3: Volumetric Particle System Simulation
Opt-in native procedural rendering MAY overlay volumetric particle systems scaled with tension ($T \in [1, 5]$). Production FFmpeg lavfi/catalog loops MUST NOT require a particle simulator.

#### Scenario: Production loops do not require a particle simulator
- **Given** `ENABLE_NATIVE_PROCEDURAL` is unset
- **When** FFmpeg lavfi/catalog loops render
- **Then** a particle simulator MUST NOT be required.

### Requirement 4: Zero-Drop Seamless Crossfade (`xfade`) Transitions
Production assembly MUST use `DIRECTOR_SINGLE_PASS`. Homogeneous procedural loops with `stream_copy_mode` MUST concatenate via concat demuxer `-c:v copy`. The same WxH/codec/pix_fmt/time_base gate applies to `MultiActVideoRenderer` when HUD is off and `MULTIACT_XFADE=0`; mismatched loops MUST degrade to one `encode_defaults` (`veryfast` / CRF 21) re-encode with `setsar=1` (never silent corrupt concat). FFmpeg `xfade` (0.5s–1.5s, default 0.75s) MAY run when explicitly opted in; when used, the compositor MUST compute exact frame counts and offsets for zero dropped frames and A/V sync.

#### Scenario: Multi-scene sequential single-pass composition (Happy Path)
- **Given** 3 sequential rendered scenes with matching WxH/codec/pix_fmt/time_base and no `niche_hud`
- **When** `MultiSceneCompositor` assembles via `DIRECTOR_SINGLE_PASS`
- **Then** assembly MUST stream-copy (`-c:v copy` / `loop_stream_copy`)
- **And** MUST NOT require `xfade`.

### Requirement 5: Photometric Luminance Floor and Gamma Calibration
Production FFmpeg procedural loops MUST enforce a minimum baseline luminance floor of at least 0.15 (15% normalized luminance) across background scenery, silhouettes, and horizons, and MUST encode with standard sRGB gamma transfer characteristics to prevent black crushing on mobile OLED displays. Opt-in WGSL shaders MUST apply the same floor when `ENABLE_NATIVE_PROCEDURAL` is set.

#### Scenario: Production loops enforce luminance floor
- **Given** nocturnal FFmpeg catalog scenery
- **When** background pixels outside direct light sources are evaluated
- **Then** the ambient pixel luminance value MUST NOT fall below 0.15.

### Requirement 6: WebGPU 64-Byte Uniform Buffer Layout Adapter
When `ENABLE_NATIVE_PROCEDURAL` is enabled, the quarantined native procedural engine MAY map art director parameters into the rigid 64-byte (16 float32) WebGPU uniform buffer layout. Production MUST NOT require this adapter.

#### Scenario: Production path does not require the WebGPU uniform adapter
- **Given** `ENABLE_NATIVE_PROCEDURAL` is unset
- **When** `MultiSceneCompositor` renders
- **Then** the 64-byte WebGPU uniform adapter MUST NOT be required.

### Requirement 7: Native Multi-Scene Compositor Delegation
`MultiSceneCompositor` MUST default to `ProceduralVideoEngine()` (FFmpeg lavfi/catalog). `NativeProceduralEngine` (WebGPU / Mesa Lavapipe), GLSL, and WebGL MUST NOT be constructed on the production hot path unless `ENABLE_NATIVE_PROCEDURAL` is explicitly enabled. Opt-in native code MUST remain quarantined under `src/media/_legacy` and MUST NOT be deleted. Bounded task concurrency ($N \le 2$ concurrent scene render jobs) still applies.

#### Scenario: Multi-scene render executes via ProceduralVideoEngine (Happy Path)
- **Given** a scene manifest containing 6 sequential procedural scenes and `ENABLE_NATIVE_PROCEDURAL` unset
- **When** `MultiSceneCompositor` renders the video sequence
- **Then** each scene MUST be rendered by `ProceduralVideoEngine` (FFmpeg lavfi/catalog)
- **And** `NativeProceduralEngine` MUST NOT be loaded.

#### Scenario: Native procedural engine remains opt-in (Edge Case)
- **Given** `ENABLE_NATIVE_PROCEDURAL` is explicitly enabled
- **When** `MultiSceneCompositor` initializes with native rendering
- **Then** `NativeProceduralEngine` MAY be used from `src/media/_legacy`
- **And** production defaults MUST remain FFmpeg when the flag is unset.

### Requirement: Niche HUD Dispatch Without Browser
The **MultiAct** filtergraph path and **`DIRECTOR_SINGLE_PASS`** / `MultiSceneCompositor` assembly MUST support niche HUD overlays via FFmpeg `drawtext`/`drawbox` only (no Playwright/Chromium). Geometry MUST be selected only by theme-agnostic `niche_hud.hud_layout` (`top_bar` | `card` | `bottom_bar`; default `top_bar`). Planner `niche_hud` dict is preferred when present on `NarrativeSceneAct` / scene manifest; otherwise MultiAct uses default layout + act badge/site/telemetry/color fields. `story_type` / niche-name strings MUST NOT choose HUD geometry or accent-color fallbacks.

- `top_bar`: top header bar with site, badge, optional high-tension alert
- `card`: centered card with badge / site / telemetry
- `bottom_bar`: bottom bar on landscape; top safe bar on vertical Shorts

HUD re-encode MUST use shared `encode_defaults` (`veryfast` + CRF 21).

**DIRECTOR_SINGLE_PASS HUD burn:** When planner/manifest `niche_hud` is present, `MultiSceneCompositor` MUST consume it via shared `niche_hud_from_mapping` + `build_niche_hud_filter` and fuse the drawtext/drawbox snippets into **one** assembly `filter_complex` (homogeneous HUD concat, scale+concat, or opt-in xfade) — not N per-scene encodes, and not Playwright/wgpu/Pillow frame loops. Homogeneous loops **without** `niche_hud` MUST still stream-copy (`-c:v copy` / `loop_stream_copy`).

#### Scenario: top_bar layout produces header HUD filter
- **Given** a scene with `niche_hud.hud_layout = "top_bar"` and tension ≥ 4
- **When** `MultiActVideoRenderer.build_scene_hud_filter` runs
- **Then** the filtergraph MUST include drawbox/drawtext HUD elements and an alert indicator
- **And** MUST NOT import Playwright or Chromium.

#### Scenario: DIRECTOR_SINGLE_PASS burns planner niche_hud in one filter_complex
- **Given** procedural scenes with planner `niche_hud` and `DIRECTOR_SINGLE_PASS` enabled
- **When** `MultiSceneCompositor` assembles loops via single-pass
- **Then** the assembly MUST include drawtext/drawbox HUD elements in a single `filter_complex`
- **And** MUST use `encode_defaults` (`veryfast` + CRF 21) for that one encode
- **And** MUST NOT perform N per-scene video encodes for HUD
- **And** MUST NOT import Playwright, Chromium, or wgpu on that path

#### Scenario: DIRECTOR_SINGLE_PASS without niche_hud still stream-copies
- **Given** homogeneous procedural loops (matching WxH/codec/pix_fmt/time_base) with no `niche_hud`
- **When** `MultiSceneCompositor` assembles via single-pass
- **Then** assembly MUST use stream-copy (`-c:v copy` / `loop_stream_copy`) without a HUD `filter_complex`

#### Scenario: MultiAct stream-copy when HUD is off (vertical or horizontal)
- **Given** `DIRECTOR_SINGLE_PASS=1`, `MULTIACT_XFADE=0`, no burned ASS, and planner HUD disabled (`niche_hud` is null / `hud_enabled: false` / `hud_layout: none`)
- **When** `MultiActVideoRenderer` composites acts whose catalog loops match the target canvas (1080x1920 or 1920x1080) and share codec/pix_fmt/time_base
- **Then** assembly MUST trim+concat with `-c:v copy` and MUST NOT emit a `filter_complex` re-encode

#### Scenario: MultiAct inhomogeneous loops degrade to encode_defaults
- **Given** any act/loop that differs in WxH, codec, pix_fmt, or time_base
- **When** `MultiActVideoRenderer` composites
- **Then** assembly MUST NOT stream-copy
- **And** MUST re-encode once with `encode_defaults` (`veryfast` + CRF 21)
- **And** the scale/concat graph MUST include `setsar=1` on each input
- **And** FFmpeg failures MUST raise (no silent corrupt concat)

#### Scenario: Shorts niche HUD respects shared safe-zone margins
- **Given** a vertical Shorts canvas (e.g. 1080x1920) and any HUD layout (`top_bar` / `card` / `bottom_bar`)
- **When** `build_niche_hud_filter` / `MultiActVideoRenderer.build_scene_hud_filter` runs
- **Then** drawbox/drawtext HUD geometry MUST stay inside the shared thumbnail `AspectLayoutManager` safe-zone (clear of YouTube Shorts top chrome, right rail, and bottom caption/channel UI)
- **And** fontsize/stroke MUST use the shared HUD typography constants across niches
- **And** missing/default accents MUST resolve from lane/channel palette when available
- **And** MUST NOT reintroduce slow presets, wgpu, Pillow frame loops, or default-on `DIRECTOR_XFADE`
