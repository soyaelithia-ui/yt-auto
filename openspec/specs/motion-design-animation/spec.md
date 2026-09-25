# Motion Design and Animation Engine Specification

## Purpose
Defines the motion design and animation engine governing smoothstep Ken Burns camera motion planning, still asset segment splitting to eliminate FFmpeg precision drift, bounded LRU vector overlay rasterization, zero-allocation NumPy RGBA frame buffers, graceful rasterizer fallback, and tension-aware transition harmonization.

## Requirements

### Requirement: Smoothstep Ken Burns Camera Motion Planning (`build_ken_burns_zoompan_filter`)
The system MUST generate atomic single-pass FFmpeg `zoompan` filter expressions using smoothstep mathematical easing ($e(t) = t^2(3 - 2t)$) via `build_ken_burns_zoompan_filter()`. Camera motion SHALL accelerate smoothly from a rest state and decelerate gently at scene termination, avoiding linear robotic motion artifacts. Camera panning MUST cycle deterministically through alternating pan trajectories (`KEN_BURNS_PAN_CYCLE`: `center_to_top`, `left_to_right`, `center_to_bottom`, `right_to_left`, and `static_push`). Default zoom parameters SHALL scale from $1.00$ to $1.10$ unless overridden. Intermediate PNG frame dump sequences are strictly prohibited.

#### Scenario: Smoothstep zoompan expression compilation (Happy Path)
- **Given** video dimensions $1080\times 1920$, 30 FPS, total frames 150 (5.0 seconds)
- **And** zoom factors `zoom_start=1.00`, `zoom_end=1.10` with pan direction `"left_to_right"`
- **When** `build_ken_burns_zoompan_filter(1080, 1920, 30, 150, 1.00, 1.10, "left_to_right")` is invoked
- **Then** the output string MUST be a valid FFmpeg `zoompan` filter string
- **And** it MUST contain the smoothstep expression `(on/149)*(on/149)*(3-2*(on/149))`
- **And** the `x` expression MUST contain `(iw-iw/zoom)*`
- **And** the `s` parameter MUST specify `1080x1920`.

#### Scenario: Vertical pan direction centering (Happy Path)
- **Given** video dimensions $1080\times 1920$, 30 FPS, 300 frames
- **And** pan direction `"center_to_top"`
- **When** `build_ken_burns_zoompan_filter` executes
- **Then** the `x` expression MUST center horizontally using `(iw-iw/zoom)/2`
- **And** the `y` expression MUST pan vertically from center towards top using `(ih-ih/zoom)/2*(1-` smoothstep easing.

#### Scenario: Single-frame or degenerate frame count handling (Edge Case)
- **Given** a degenerate input where `total_frames` is 1 or less
- **When** `build_ken_burns_zoompan_filter` executes
- **Then** the function MUST clamp the denominator to at least 1
- **And** avoid division by zero errors in the generated FFmpeg expression.

### Requirement: Still Asset Segment Splitting for Drift Prevention (`plan_ken_burns_still_segments`)
To eliminate FFmpeg floating-point coordinate precision loss and avoid visual viewer fatigue, still image scenes exceeding 15.0 seconds MUST be automatically split into discrete sub-segments between 12.0 and 15.0 seconds (hard threshold 20.0 seconds) via `plan_ken_burns_still_segments()`. Each sub-segment SHALL receive a unique pan direction chosen sequentially from `KEN_BURNS_PAN_CYCLE` so that long still scenes cut rhythmically between alternating camera angles.

#### Scenario: Long still image split into rhythmic sub-segments (Happy Path)
- **Given** a still image scene with duration of 32.0 seconds
- **When** `plan_ken_burns_still_segments(duration_sec=32.0)` is invoked
- **Then** the planner MUST partition the duration into 3 sub-segments
- **And** each sub-segment duration MUST be within the range $[10.0, 15.0]$ seconds
- **And** the sum of sub-segment durations MUST equal 32.0 seconds within $\pm 0.05\text{ seconds}$
- **And** adjacent sub-segments MUST have different pan directions.

#### Scenario: Short still scene remaining unsplit (Happy Path)
- **Given** a still image scene with duration of 9.0 seconds ($< 15.0\text{ seconds}$)
- **When** `plan_ken_burns_still_segments(duration_sec=9.0)` is invoked
- **Then** the planner MUST return exactly 1 segment of 9.0 seconds
- **And** no artificial cuts SHALL be introduced.

#### Scenario: Split threshold boundary handling (Edge Case)
- **Given** a still image scene of exactly 20.0 seconds (the hard split threshold)
- **When** `plan_ken_burns_still_segments(duration_sec=20.0)` is invoked
- **Then** the planner MUST split the scene into 2 segments of 10.0 seconds each
- **And** no individual segment SHALL exceed 15.0 seconds.

### Requirement: Vector Overlay Engine Caching and Rendering (`vector_overlay_engine_caching_and_rendering`)

The system MUST provide a high-performance, memory-bounded vector overlay engine (`SVGOverlayEngine` in `src/media/svg_overlay.py`) capable of dynamic template interpolation and zero-allocation frame rasterization while strictly adhering to project resource limits ($\le 2\text{ CPU Cores}$, $\le 2.0\text{ GiB RAM}$).

The engine MUST fulfill the following architectural requirements:
1. **Dynamic Parameter Interpolation**:
   - The engine MUST load SVG XML templates from `assets/svg_overlays/` or resolve them via `GraphicsBank`.
   - Template placeholders MUST support both double-brace `{{param}}` and single-brace `{param}` syntax.
   - If dynamic parameters are provided, placeholders MUST be substituted with sanitized string values.
   - If dynamic parameters are omitted or missing, the template MUST retain default fallback text or clean defaults without corrupting XML syntax or raising unhandled exceptions.
2. **Bounded LRU Raster Cache**:
   - The engine MUST maintain an in-memory raster cache indexed by composite key `(preset_name, width, height, tuple(sorted(params.items())))`.
   - The cache MUST be strictly bounded at a maximum capacity of **128 items** ($\le 128$ cached RGBA raster arrays $\approx 1.06\text{ GiB}$ worst-case ceiling, operational steady-state $< 200\text{ MiB}$).
   - Upon reaching 128 entries, insertion of a new rasterization MUST evict the least recently used (LRU) entry.
   - The engine MUST provide `clear_cache()` and `cache_info()` methods to allow pipeline stages to inspect and flush cache state.
3. **Zero-Allocation In-Place NumPy Buffers**:
   - `render_overlay(preset_name, width, height, params=None, out_buffer=None)` MUST accept a pre-allocated contiguous NumPy array `out_buffer` of shape `(height, width, 4)` and `dtype=uint8`.
   - When `out_buffer` is provided, the engine MUST rasterize directly into `out_buffer` (or copy into it in-place) and return the identical array instance (`out_buffer is result`).
   - Accumulating lists or arrays of uncompressed video frames in Python heap memory is strictly prohibited (`REG-08`).
4. **Graceful Rasterization Fallback**:
   - The primary rasterization backend SHALL be Rust-based `resvg_py` for sub-millisecond vector rendering.
   - If `resvg_py` is not installed or raises an import error, the engine MUST fall back gracefully to a secondary rasterizer (such as Pillow/PIL rasterization or synthetic test mock), log a warning event, and successfully return valid RGBA NumPy frame data. The absence of `resvg_py` MUST NOT crash rendering pipelines or cause test suite failures.
5. **Mobile Safe-Zone Viewport Compliance**:
   - Vector overlays rendered by the engine MUST comply with safe-zone margins computed by `enforce_shorts_safe_zone()` ($MarginV_{bottom} \ge 460\text{px}$, $MarginV_{top} \ge 180\text{px}$, $MarginH_{right} \ge 130\text{px}$, $MarginH_{left} \ge 64\text{px}$ for 9:16).

#### Scenario: SVG template loading and dynamic parameter interpolation (Happy Path)
- **Given** an SVG template containing tokens `{{rec_time}}` and `{battery_pct}`
- **And** parameters `{"rec_time": "00:14:28:09", "battery_pct": "78%"}`
- **When** `interpolate_template(svg_text, params)` is executed
- **Then** the output SVG text MUST have all placeholder tokens replaced with their parameter values
- **And** no residual `{{rec_time}}` or `{battery_pct}` tokens SHALL remain.

#### Scenario: Zero-allocation rasterization into pre-allocated NumPy buffer (Happy Path)
- **Given** a pre-allocated contiguous NumPy array `out_buffer` of shape `(1920, 1080, 4)` and `dtype=uint8`
- **When** `render_overlay("rec_analog_hud", 1080, 1920, params=params, out_buffer=out_buffer)` is executed
- **Then** the engine MUST render the vector graphic directly into `out_buffer`
- **And** the return value MUST be the identical array instance (`out_buffer is result`)
- **And** total heap memory allocated for frame pixels MUST NOT grow.

#### Scenario: Bounded LRU cache eviction at 128 items (Happy Path)
- **Given** an `SVGOverlayEngine` instance with 128 unique cached raster entries
- **When** a 129th unique overlay request is rendered
- **Then** the cache MUST evict the least recently used entry
- **And** `cache_info().currsize` MUST NOT exceed 128
- **And** peak memory consumption MUST remain within the $\le 2.0\text{ GiB}$ system budget.

#### Scenario: Graceful rasterization fallback when resvg_py is uninstalled (Edge Case)
- **Given** an execution environment where `resvg_py` is not installed or import is mocked to fail
- **When** `render_overlay` is invoked with valid SVG overlay preset
- **Then** the engine MUST catch the missing dependency, emit a warning log, and use the fallback rasterizer
- **And** return a valid `(height, width, 4)` uint8 NumPy array
- **And** MUST NOT raise an unhandled `ImportError` or terminate the pipeline.

#### Scenario: Missing preset or null overlay rendering (Edge Case)
- **Given** a preset name of `"none"`, `""`, or `None`
- **And** a pre-allocated `out_buffer`
- **When** `render_overlay` is invoked
- **Then** the engine MUST zero-fill `out_buffer` to complete transparency
- **And** return the cleared buffer without raising an exception.

#### Scenario: Buffer dimension mismatch detection (Edge Case)
- **Given** a pre-allocated buffer of shape `(1280, 720, 4)` but requested width 1080 and height 1920
- **When** `render_overlay` is invoked with the mismatched buffer
- **Then** the engine MUST raise a `ValueError` identifying the shape mismatch
- **And** prevent buffer overrun or memory corruption.

### Requirement: Tension-Aware Scene Transition Harmonization (`harmonize_scene_transitions`)
The system MUST dynamically calculate transition durations between adjacent scenes using `harmonize_scene_transitions()` based on the absolute emotional tension differential ($\Delta T = |T_{next} - T_{curr}|$).
1. High tension differentials ($\Delta T \ge 2$) MUST generate fast, punchy cuts or short crossfades ($0.20\text{s} - 0.35\text{s}$).
2. Moderate tension differentials ($\Delta T = 1$) MUST generate intermediate dissolves ($0.30\text{s} - 0.50\text{s}$).
3. Steady tension levels ($\Delta T = 0$) MUST generate gradual, atmospheric dissolves ($0.35\text{s} - 0.75\text{s}$).

Transitions MUST be bounded by at most $30\%$ of the shorter adjacent scene duration to prevent overlapping cuts from collapsing scene visibility. Transitions SHALL be compiled into single-pass atomic FFmpeg `xfade` expressions without intermediate file writes.

#### Scenario: High tension differential transition calculation (Happy Path)
- **Given** adjacent scenes $S_1$ (tension 1, duration 5.0s) and $S_2$ (tension 4, duration 4.0s) with $\Delta T = 3$
- **When** `harmonize_scene_transitions([S_1, S_2], default_transition=0.5)` is invoked
- **Then** the computed transition duration MUST be between $0.20\text{s}$ and $0.35\text{s}$
- **And** reflect an abrupt, punchy pacing cut.

#### Scenario: Steady tension atmospheric dissolve calculation (Happy Path)
- **Given** adjacent scenes $S_1$ (tension 2, duration 8.0s) and $S_2$ (tension 2, duration 7.0s) with $\Delta T = 0$
- **When** `harmonize_scene_transitions([S_1, S_2], default_transition=0.5)` is invoked
- **Then** the computed transition duration MUST be between $0.35\text{s}$ and $0.75\text{s}$
- **And** preserve atmospheric visual continuity.

#### Scenario: Ultra-short scene transition capping (Edge Case)
- **Given** adjacent scenes where the shorter scene duration is only $0.80\text{ seconds}$
- **When** `harmonize_scene_transitions` evaluates the boundary
- **Then** the transition duration MUST be capped at $30\%$ of $0.80\text{s}$ ($0.24\text{ seconds}$)
- **And** prevent the transition duration from consuming the scene.

#### Scenario: Single scene or empty sequence handling (Edge Case)
- **Given** a scene sequence with fewer than 2 scenes
- **When** `harmonize_scene_transitions` is invoked
- **Then** it MUST return an empty list `[]` without raising an index error.
