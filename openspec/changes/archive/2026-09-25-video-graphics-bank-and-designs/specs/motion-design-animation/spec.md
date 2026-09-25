# Motion Design and Animation Engine Specification (Delta)

## Purpose
Defines the motion design and animation engine governing smoothstep Ken Burns camera motion planning, still asset segment splitting, bounded LRU vector overlay rasterization, zero-allocation NumPy RGBA frame buffers, graceful rasterizer fallback, and tension-aware transition harmonization.

## MODIFIED Requirements

### Requirement: Vector Overlay Engine Caching and Rendering (`vector_overlay_engine_caching_and_rendering`)
(Previously: `Dynamic Kinetic SVG Typography and HUD Overlays (SVGOverlayEngine)`)

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
