# Technical Design: Visual Coherence System and Independent Parallel Production Lanes

## 1. Executive Summary & Architecture Context

This technical design formalizes the implementation architecture for the **Visual Coherence System** and **Independent Parallel Production Lanes** within the `yt-auto` media engine.

The system addresses two architectural challenges:
1. **Visual-Script Synchronization Gap**: Narrative pacing, scene tension, color grading, and mobile UI safe-zone margins lacked an authoritative Single Source of Truth (SSOT).
2. **Monolithic Lane Assumptions**: Still-image animation workflows (`image_animation`) and continuous catalog video-loop workflows (`video_loop`) possess fundamentally different CPU, RAM, and turnaround latency characteristics.

By segregating these operational modes into independent parallel lanes that share hardened, low-overhead media tooling (`src/media/visual_coherence.py`, `src/media/unified_encoder.py`, and `src/core/lanes.py`), the pipeline delivers broadcast-grade cinematic motion while guaranteeing compliance with Section 5 of `AGENTS.md` and anti-regression invariant `REG-14` (**$\le 2.0$ CPU Cores**, **$\le 2.0$ GiB RAM** ceiling, and zero idle footprint).

---

## 2. Technical Approach & Architecture Decisions (ADRs)

### ADR-01: Dual Visual Pipeline Taxonomy and Lane Segregation
- **Context**: The existing pipeline utilized generic `"beats"` and `"director"` modes, requiring fragile branching to distinguish between still-image Ken Burns animation and pre-baked video loops.
- **Decision**: Extend `ALLOWED_VISUAL_PIPELINES = frozenset({"beats", "director", "image_animation", "video_loop"})` in `src/core/lanes.py` and declare explicit `visual_pipeline` entries in `config/lanes.json`.
  - `video_loop`: Focuses on seamless video loops (`assets/loops/`), stream-copy composition (`-c:v copy`), and soft subtitle track muxing (`mov_text`). Throughput: $1.2\text{s} - 2.5\text{s}$ per 60s video, consuming $\approx 0.10$ Cores CPU.
  - `image_animation`: Focuses on curated still photography and concept art, smoothstep Ken Burns camera motion, segment splitting, dynamic SVG kinetic typography, and atomic single-pass transcode via `UnifiedEncoder`. Throughput: $20\text{s} - 35\text{s}$ per 60s video, consuming $\approx 1.40 - 1.85$ Cores CPU.
- **Alternatives Considered**:
  - *Alternative A: Dynamic File Extension Sniffing*: Inspecting asset extensions (`.jpg` vs `.mp4`) at runtime in stage 09. *Rejected*: Highly prone to runtime race conditions, ambiguous multi-asset scenes, and violates declarative configuration principles.
  - *Alternative B: Separate Execution Daemons*: Creating independent daemon processes for loop lanes and animation lanes. *Rejected*: Excessive operational complexity and violates anti-bloat directives; concurrency is cleanly managed via semaphores within a single unified orchestrator.
- **Rationale**: Clean segregation allows each pipeline to optimize its critical path while preserving zero cross-lane interference and strict resource budgets.

### ADR-02: SSOT Shared Core Media Tooling
- **Context**: Duplicating audio ducking curves, color grading filters, safe-area math, and FFmpeg subprocess management across separate lane handlers causes code drift and maintenance regressions.
- **Decision**: Unify all foundational media algorithms into two shared modules:
  1. `src/media/visual_coherence.py`: Authoritative SSOT for narrative act duration scaling (`timing_scales_to_audio`), brand-aligned Rec.709 color grading expressions (`build_coherent_color_grade`), mobile UI safe-zone geometry (`enforce_shorts_safe_zone`), and pre-render sequence validation (`validate_visual_continuity`).
  2. `src/media/unified_encoder.py`: Authoritative SSOT for atomic FFmpeg execution, background stderr draining (`_drain_stderr`), sidechain ducking, EBU R128 loudness mastering, and libass subtitle filter burning.
- **Alternatives Considered**:
  - *Alternative A: Custom Rendering Libraries per Channel*: Unique scripts for `horror`, `drama`, and `scifi`. *Rejected*: Violates Section 2 and Section 8 of `AGENTS.md` (code bloat, drift, redundant maintenance).
- **Rationale**: Eliminates code duplication, guarantees unified audio mastering standards across all channels, and adheres to strict DRY principles.

### ADR-03: Smoothstep Ken Burns Camera Motion with Rhythmic Segment Splitting
- **Context**: Linear camera interpolation looks mechanical and unnatural. Furthermore, single FFmpeg `zoompan` filters running continuously for $> 20$ seconds suffer from floating-point coordinate truncation and visual viewer fatigue.
- **Decision**: In `src/media/ken_burns.py`:
  1. Generate smoothstep mathematical easing ($e(t) = t^2(3 - 2t)$) within the FFmpeg `zoompan` expression: `(on/denom)*(on/denom)*(3-2*(on/denom))`.
  2. Automatically split still-image scenes exceeding 15.0 seconds into discrete sub-segments between 12.0 and 15.0 seconds (hard threshold 20.0 seconds) via `plan_ken_burns_still_segments()`.
  3. Alternate pan directions across sub-segments using `KEN_BURNS_PAN_CYCLE` (`center_to_top`, `left_to_right`, `center_to_bottom`, `right_to_left`).
- **Alternatives Considered**:
  - *Alternative A: Intermediate PNG Frame Sequence Dumps*: Generating frame images with Pillow and stitching via FFmpeg. *Rejected*: Strictly prohibited by `REG-03`, `REG-08`, and `AGENTS.md` Section 5. Dumps hundreds of MBs to disk and causes severe I/O thrashing.
  - *Alternative B: Monocular Depth Parallax (3D Mesh)*: Decompressing frames and applying depth maps in Python. *Rejected*: Exceeds the 2.0 GiB RAM ceiling and introduces heavy GPU/C++ library dependencies.
- **Rationale**: Native FFmpeg `zoompan` executes entirely in compiled C within FFmpeg, streaming frames without disk dumps or Python heap memory growth.

### ADR-04: Declarative Vector Typography and HUD Overlays via `SVGOverlayEngine`
- **Context**: Overlaying thematic badges (e.g. SCP classification stamps, analog horror timestamps, narrative meters) must comply with mobile UI safe zones without leaking RAM or using browser runtimes.
- **Decision**: Implement `SVGOverlayEngine` in `src/media/svg_overlay.py` utilizing Rust-based `resvg_py`:
  1. Load and cache XML templates from `assets/svg_overlays/`.
  2. Perform parameter replacement for Mustache `{{param}}` and single-brace `{param}` tokens.
  3. Render vector graphics directly into a pre-allocated contiguous NumPy array (`out_buffer: np.ndarray`, `shape=(height, width, 4)`, `dtype=uint8`), mutating memory in-place.
  4. Cache rendered rasters in an LRU memory cache indexed by `(preset, width, height, params_tuple)` capped at 128 entries.
- **Alternatives Considered**:
  - *Alternative A: Headless Chromium / Playwright SVG Render*: *Rejected*: Strictly prohibited by `REG-01`.
  - *Alternative B: Unconstrained Pillow Rendering*: Rendering text per frame with Pillow. *Rejected*: Strictly prohibited by `REG-03`.
- **Rationale**: `resvg_py` is compiled in Rust, produces pixel-perfect vector rasterization in $< 5\text{ms}$, and avoids all frame-allocation overhead.

### ADR-05: Tension-Aware Scene Transition Harmonization
- **Context**: Fixed-duration scene transitions do not adapt to narrative pacing. A climax needs jarring cuts, whereas atmospheric world-building needs gradual dissolves.
- **Decision**: In `src/media/visual_coherence.py`, `harmonize_scene_transitions()` dynamically evaluates tension delta $\Delta T = |T_{next} - T_{curr}|$:
  - $\Delta T \ge 2$: Fast, jarring cut / short xfade ($0.20\text{s} - 0.35\text{s}$).
  - $\Delta T = 1$: Intermediate dissolve ($0.30\text{s} - 0.50\text{s}$).
  - $\Delta T = 0$: Atmospheric gradual dissolve ($0.35\text{s} - 0.75\text{s}$).
  - Clamping: Transitions are capped at $30\%$ of the shorter adjacent scene duration. Atomic single-pass FFmpeg `xfade` expressions are emitted.
- **Alternatives Considered**:
  - *Alternative A: Random Transition Types*: Selecting wipe, zoom, or slide randomly. *Rejected*: Distracting, unprofessional aesthetic.
- **Rationale**: Direct mathematical coupling between narrative tension and visual transition duration reinforces audience retention and dramatic rhythm.

### ADR-06: Stream-Copy Priority & Soft Subtitle Muxing
- **Context**: Re-encoding video solely to burn subtitle text consumes unnecessary CPU cycles on loop-based formats.
- **Decision**: Enforce `-c:v copy` and soft timed-text muxing (`-c:s mov_text`) on all `video_loop` production runs. Subtitle burning via `libass` is restricted exclusively to re-encoding pipelines (`image_animation`) where video recompression is already unavoidable.
- **Alternatives Considered**:
  - *Alternative A: Burn Subtitles Across All Formats*: *Rejected*: Spikes CPU to 180% and increases rendering time from 1.5s to 30s on catalog loops, violating `REG-13` and `REG-14`.
- **Rationale**: Preserves maximum operational throughput ($> 80\times\text{ realtime}$) and negligible CPU consumption ($< 0.15\text{ Cores}$) for high-volume video-loop publishing.

---

## 3. Data Flow Architecture

The following ASCII diagram illustrates the dual parallel lanes sharing common media tooling under strict hardware resource governance:

```
+===================================================================================================+
|                                    NARRATIVE & AUDIO PREPARATION                                  |
|  [Script Acts & Curation] ------------> [Edge TTS Audio Synthesis]                                |
|  [Scene Tension Levels (1..5)] -------> [EBU R128 Probed Duration]                                |
+===================================================================================================+
                                                |
                                                v
+===================================================================================================+
|                                  SHARED CORE MEDIA TOOLING (SSOT)                                 |
|                                                                                                   |
|  src/media/visual_coherence.py                                                                    |
|  - timing_scales_to_audio(): Normalizes scene durations to narration (diff absorbed by final)    |
|  - build_coherent_color_grade(): Filmic Rec.709 curves (horror, drama, scifi, default)           |
|  - enforce_shorts_safe_zone(): Clamps UI margins (Vertical: Bottom >= 460px, Top >= 180px)        |
|  - validate_visual_continuity(): Validates non-empty, positive durations, well-formed tensions     |
|  - harmonize_scene_transitions(): Calculates tension-differential transition durations           |
|                                                                                                   |
|  src/core/lanes.py & config/lanes.json                                                            |
|  - LaneProfile: Declares visual_pipeline in {"beats", "director", "image_animation", "video_loop"}|
+===================================================================================================+
                                                |
                       +------------------------+------------------------+
                       |                                                 |
                       v                                                 v
+-----------------------------------------------+ +-----------------------------------------------+
|      LANE A: IMAGE-ANIMATION PIPELINE         | |        LANE B: VIDEO-LOOP PIPELINE            |
|       (visual_pipeline: image_animation)      | |         (visual_pipeline: video_loop)         |
+-----------------------------------------------+ +-----------------------------------------------+
| 1. Asset Resolution:                          | | 1. Asset Resolution:                          |
|    - Tier 1: Curated Stills (assets/visuals)  | |    - Tier 1: Curated Loops (assets/loops)     |
|    - Tier 2: Cached Workset Stills            | |    - Tier 2: Cached Workset Loops             |
|    - Tier 3: Thematic Fallback Loops          | |    - Tier 3: Continuous Catalog Fallback      |
|                                               | |                                               |
| 2. Camera Motion Planning:                    | | 2. Stream-Copy Setup:                         |
|    - plan_ken_burns_still_segments()          | |    - Concat demuxer (ffconcat) list           |
|      (splits > 15s into 12-15s sub-segments)  | |    - Zero video re-encoding (-c:v copy)       |
|    - build_ken_burns_zoompan_filter()         | |                                               |
|      (smoothstep easing: t^2 * (3 - 2t))      | | 3. Subtitle Preparation:                      |
|                                               | |    - Generate ASS cues                        |
| 3. Dynamic Vector Overlays:                   | |    - Configure soft muxing (-c:s mov_text)    |
|    - SVGOverlayEngine: XML template cache     | |      (zero libass burn-in on copy path)       |
|    - resvg-py zero-allocation buffer mutate   | |                                               |
|    - Mobile safe-zone viewport clamping       | | 4. Audio Ducking & Mastering:                 |
|                                               | |    - Voice + BGM single-pass mux              |
| 4. Subtitle Preparation:                      | |    - Sidechain ducking (-18 dB)               |
|    - Generate ASS with MarginV >= 240px       | |    - EBU R128 normalization (I=-16 LUFS)      |
|                                               | |                                               |
| 5. Unified Single-Pass Transcode:             | | 5. High-Throughput Assembly:                  |
|    - UnifiedEncoder (-threads 2)              | |    - LoopVideoEngine.compose()                |
|    - Atomic filtergraph: zoompan + xfade +    | |    - Elapsed time: 1.2s - 2.5s                |
|      colorbalance + libass burn + loudnorm    | |    - Peak CPU: ~0.10 Cores                    |
|    - Background _drain_stderr daemon          | |    - Peak RAM: ~150 MiB                       |
|    - Elapsed time: 20s - 35s                  | |                                               |
|    - Peak CPU: ~1.65 Cores (<= 2.0 Cores)     | |                                               |
|    - Peak RAM: ~580 MiB (<= 2.0 GiB)          | |                                               |
+-----------------------------------------------+ +-----------------------------------------------+
                       |                                                 |
                       +------------------------+------------------------+
                                                |
                                                v
+===================================================================================================+
|                              STRICT RESOURCE GOVERNANCE LAYER (REG-14)                            |
|  - Concurrency Semaphores: _SHORT_RENDER_SEMAPHORE = 2, _LONG_RENDER_SEMAPHORE = 1              |
|  - Subprocess Thread Bounding: -threads 2 default, max -threads 4                                 |
|  - Zero Steady-State Idle Footprint: 0.0% CPU when idle; memory_checkpoint() cleans buffers       |
|  - Filesystem Isolation: data/runs/{run_id}/ working directory per execution                      |
|  - Output MP4 Video Artifact Verification & Integrity Audit (scripts/verify_integrity.sh)        |
+===================================================================================================+
```

---

## 4. File Changes (Create / Modify Map)

| File Path | Action | Description & Scope of Changes |
| :--- | :---: | :--- |
| `src/core/lanes.py` | Modify | Update `ALLOWED_VISUAL_PIPELINES = frozenset({"beats", "director", "image_animation", "video_loop"})`. Update `parse_lane()` validation and docstrings. Ensure default fallback lanes preserve valid visual pipelines. |
| `config/lanes.json` | Modify | Update the 6 canonical production lanes to declare explicit `visual_pipeline` properties (`image_animation` for `horror-scp-shorts` and `scifi-singularity-shorts`; `video_loop` for `drama-drama-shorts`; `director` for longform lanes). |
| `src/media/visual_coherence.py` | Modify | Harden SSOT functions: update `timing_scales_to_audio()` with edge-case clamping and residual absorption; enforce exact filmic color balance curves for `horror`, `drama`, and `scifi` in `build_coherent_color_grade()`; enforce safe-zone bounds in `enforce_shorts_safe_zone()` ($MarginV \ge 460\text{px}$ vertical, $\ge 120\text{px}$ horizontal); export `validate_visual_continuity()` and `harmonize_scene_transitions()`. |
| `src/media/ken_burns.py` | Modify | Implement smoothstep mathematical easing ($e(t) = t^2(3 - 2t)$) in `build_ken_burns_zoompan_filter()`; implement segment splitting (12-15s bounds, 20s split threshold) with pan cycle alternation in `plan_ken_burns_still_segments()`; handle degenerate 1-frame boundary conditions safely. |
| `src/media/svg_overlay.py` | Modify | Implement `SVGOverlayEngine` with in-memory XML caching, Mustache parameter interpolation (`{{param}}` and `{param}`), bounded raster caching (max 128 entries), zero-allocation rasterization into pre-allocated NumPy array (`out_buffer`), and shape validation (`shape == (height, width, 4)` and `dtype == uint8`). |
| `src/media/overlays.py` | Modify | Retain atmospheric opacity clamping ($0.15 - 0.35$), multi-plane root discovery, and non-plane0 loop filtering in `resolve_hybrid_motion_loop()`. |
| `src/media/unified_encoder.py` | Modify | Retain single-pass atomic transcode, asynchronous stderr pipe drain thread (`_drain_stderr`), EBU R128 mastering, and context manager lifecycle (`__enter__` / `__exit__`). |
| `src/core/contracts/render.py` | Modify | Verify `RenderSpec` properties, enforce thread bounding ($\le 4$), and support lane-level `visual_pipeline` propagation. |
| `src/pipeline/stages/stage_08_loop.py` | Modify | Inspect `ctx.lane.visual_pipeline`. If `image_animation`, resolve still assets and compile Ken Burns motion metadata into manifest; if `video_loop`, resolve continuous catalog loop and set `stream_copy_mode = True`, `mux_subtitles = True`. |
| `src/pipeline/stages/stage_09_render.py` | Modify | Route execution cleanly based on `ctx.lane.visual_pipeline`: invoke `UnifiedEncoder` for single-pass image animation transcode, or invoke `LoopVideoEngine.render()` with `stream_copy=True` for loop composition. Include automatic fallback to loop composition upon caught rendering exceptions. |
| `tests/unit/test_visual_coherence.py` | Create | New unit test suite verifying `timing_scales_to_audio`, `build_coherent_color_grade`, `enforce_shorts_safe_zone`, `validate_visual_continuity`, `harmonize_scene_transitions`, Ken Burns smoothstep easing, segment splitting, and `SVGOverlayEngine` buffer operations. |
| `tests/unit/test_parallel_lanes.py` | Create | New unit test suite verifying lane configuration parsing for `image_animation` and `video_loop`, semaphore isolation, and CLI runtime `--visual-pipeline` overrides. |

---

## 5. Strict Resource Governance Envelope (AGENTS.md Section 5 & REG-14)

### 5.1. Hard Operational Target Ceiling
In accordance with Section 5 of `AGENTS.md` and invariant `REG-14`:
- **CPU Target Ceiling**: $\le 2.0$ CPU Cores ($\le 200\%$ aggregate thread utilization).
- **RAM Target Ceiling**: $\le 2.0$ GiB RAM ($2,048\text{ MiB}$ resident memory RSS).
- Docker cgroup settings (`cpus: 4.0`, `mem_limit: 6g`) act strictly as host safety buffers against kernel OOM panics; the software pipeline treats 2 Cores and 2.0 GiB RAM as the inviolable operational boundary.

### 5.2. Steady-State Zero Envelope (Idle Efficiency)
- Background schedulers, watchers, and daemons MUST drop to **$0.0\%$ CPU** when no video rendering job is active.
- Persistent GPU contexts, resident PyTorch/TensorFlow runtimes, and thread pools MUST NOT remain alive during idle cycles.
- Subprocesses (FFmpeg, FFprobe) must execute inside context managers. Upon completion or error, standard input, output, and error pipes must be closed, and background stderr reader threads must be joined immediately.
- Stage boundaries MUST invoke `memory_checkpoint()` to explicitly garbage-collect unreferenced data structures.

### 5.3. Stream-Copy Priority & Soft Subtitle Muxing
- The `video_loop` lane strictly enforces `-c:v copy`. By avoiding video frame decoding and re-encoding:
  - CPU consumption drops to $\approx 0.08 - 0.15$ Cores.
  - Video composition completes in $1.2\text{s} - 2.5\text{s}$ ($> 80\times$ realtime).
  - Subtitles are soft-muxed as timed text tracks (`-c:s mov_text`), completely eliminating CPU-intensive `libass` pixel rasterization.

### 5.4. Disk Streaming Without Buffer Loops (Zero In-Memory Frame Arrays)
- Storing uncompressed $1080\times 1920$ RGBA frames in Python memory requires $\approx 8.29\text{ MB}$ per frame. Storing a 30-second short (900 frames) in a Python list or array would consume $> 7.46\text{ GB}$ RAM, causing immediate process termination (`REG-08`).
- All Ken Burns motion, transitions, and color grading filters MUST be compiled into atomic single-pass FFmpeg filtergraphs (`zoompan`, `xfade`, `colorbalance`), allowing FFmpeg's internal C pipeline to stream frames directly from disk to disk within bounded ring buffers.
- Where custom raster overlaying is required (`SVGOverlayEngine`), the engine allocates exactly **one** pre-allocated contiguous array (`_out_buffer` of shape `(1920, 1080, 4)` uint8 $\approx 8.29\text{ MB}$) and streams frames sequentially into `UnifiedEncoder`'s `pipe:0`. Total Python frame buffer memory remains strictly bounded below $10\text{ MiB}$.

### 5.5. Subprocess Thread & Concurrency Bounding
- Audio and video probes (`ffprobe`, loudness analysis) MUST enforce `-threads 2` and skip video frame decoding with `-vn`.
- Rendering FFmpeg commands MUST enforce `-threads 2` (default) up to an absolute maximum ceiling of `-threads 4` during multi-act renders.
- System concurrency is bounded by global semaphores:
  - `_SHORT_RENDER_SEMAPHORE = 2` (maximum 2 concurrent short video renders).
  - `_LONG_RENDER_SEMAPHORE = 1` (maximum 1 concurrent longform video render).

---

## 6. Interfaces & Data Contracts

### 6.1. `LaneProfile` Contract (`src/core/lanes.py`)
```python
ALLOWED_VISUAL_PIPELINES: Final[frozenset[str]] = frozenset(
    {"beats", "director", "image_animation", "video_loop"}
)

@dataclass(frozen=True)
class LaneProfile:
    id: str
    channel: CanonicalChannel | str
    story_type: str
    orientation: str  # "vertical" | "horizontal"
    duration_min_sec: int
    duration_target_sec: int
    duration_max_sec: int
    words_min: int
    words_max: int | None
    words_recondense_max: int
    template: str
    voice_rate: str
    cadence_min_gap_seconds: int
    cadence_initial_offset_seconds: int = 0
    sources: LaneSources = field(default_factory=LaneSources)
    background_audio: LaneBackgroundAudioConfig = field(default_factory=LaneBackgroundAudioConfig)
    enabled: bool = True
    multistory_collection: bool = False
    visual_pipeline: str = "beats"  # "image_animation" | "video_loop" | "beats" | "director"
    qa_profile: str = ""
    review_content_type: str = ""
    topic_filter_mode: str = "off"
    topic_filter_keywords: tuple[str, ...] = ()
    padding_themes: tuple[str, ...] = ()
    voice_profile: str | None = None
    fps: int = 30
```

### 6.2. `VisualCoherenceSpec` (`src/media/visual_coherence.py`)
```python
@dataclass(slots=True, frozen=True)
class SafeZoneMargins:
    top: int
    bottom: int
    left: int
    right: int
    safe_width: int
    safe_height: int

@dataclass(slots=True, frozen=True)
class VisualContinuityReport:
    valid: bool
    reason: str | None
    scene_count: int
    total_duration: float
    tensions: list[int]
    recommended_transitions: list[float]

def timing_scales_to_audio(
    raw_durations: Sequence[float],
    target_duration: float | None,
) -> list[float]: ...

def build_coherent_color_grade(
    accent_hex: str = "#00FF88",
    primary_hex: str = "#030A14",
    channel: str = "horror",
) -> str: ...

def enforce_shorts_safe_zone(width: int, height: int) -> dict[str, int]: ...

def harmonize_scene_transitions(
    scenes: Sequence[Any],
    default_transition: float = 0.5,
) -> list[float]: ...

def validate_visual_continuity(scenes: Sequence[Any]) -> dict[str, Any]: ...
```

### 6.3. `KenBurnsMotionSpec` (`src/media/ken_burns.py`)
```python
KEN_BURNS_ZOOM_START: float = 1.00
KEN_BURNS_ZOOM_END: float = 1.10
KEN_BURNS_MIN_DURATION_SEC: float = 12.0
KEN_BURNS_FPS: int = 30
KEN_BURNS_SEGMENT_TARGET_SEC: float = 13.0
KEN_BURNS_SEGMENT_MAX_SEC: float = 15.0
KEN_BURNS_SPLIT_THRESHOLD_SEC: float = 20.0
KEN_BURNS_PAN_CYCLE: tuple[str, ...] = (
    "center_to_top",
    "left_to_right",
    "center_to_bottom",
    "right_to_left",
)

def build_ken_burns_zoompan_filter(
    width: int,
    height: int,
    fps: int,
    total_frames: int,
    zoom_start: float = 1.00,
    zoom_end: float = 1.10,
    pan_direction: str = "center_to_top",
) -> str: ...

def plan_ken_burns_still_segments(
    duration_sec: float,
    fps: int | None = None,
    pan_direction: str = "center_to_top",
) -> list[tuple[float, int, str]]: ...
```

### 6.4. `SVGOverlaySpec` (`src/media/svg_overlay.py`)
```python
class SVGOverlayEngine:
    def __init__(self, assets_dir: Path | str | None = None) -> None: ...
    def load_template(self, preset_name: str) -> str: ...
    def interpolate_template(
        self,
        svg_text: str,
        params: dict[str, Any] | None = None,
        time_sec: float = 0.0,
    ) -> str: ...
    def render_overlay(
        self,
        preset_name: str,
        width: int,
        height: int,
        time_sec: float = 0.0,
        params: dict[str, Any] | None = None,
        out_buffer: np.ndarray | None = None,
    ) -> np.ndarray: ...
```

### 6.5. `RenderEngine` / `BaseVideoCompositor` Interface (`src/media/interface.py`)
```python
class BaseVideoCompositor(ABC):
    @abstractmethod
    def render(
        self,
        manifest_path: Path | str,
        output_video_path: Path | str,
        **extra_kwargs: Any,
    ) -> dict[str, Any]:
        """Render a video from a validated scene_manifest.json file."""
        pass
```

---

## 7. Testing Strategy

The test suite enforces full verification across unit, integration, guardrail, and smoke test layers:

### 7.1. Unit Testing
- `tests/unit/test_visual_coherence.py`:
  - `test_timing_scales_to_audio_proportional`: Validates that `[3.0, 4.0, 5.0]` scaled to 15.0s yields `[3.75, 5.0, 6.25]` and matches total audio duration within $\pm 0.05$s.
  - `test_timing_scales_to_audio_rounding_residual`: Asserts fractional discrepancies are absorbed by the final scene.
  - `test_timing_scales_to_audio_degenerate`: Ensures non-positive or null durations return raw durations safely without ZeroDivisionError.
  - `test_build_coherent_color_grade_channels`: Verifies correct `eq` and `colorbalance` strings for `horror`, `drama`, `scifi`, and unknown channel fallback.
  - `test_enforce_shorts_safe_zone_vertical`: Checks vertical canvas safe zones ($bottom \ge 460\text{px}$, $top \ge 180\text{px}$, $right \ge 130\text{px}$, $left \ge 64\text{px}$).
  - `test_enforce_shorts_safe_zone_horizontal`: Checks horizontal canvas safe zones ($bottom \ge 120\text{px}$, $top \ge 80\text{px}$, lateral $\ge 80\text{px}$).
  - `test_validate_visual_continuity_valid_and_invalid`: Confirms rejection of empty scene sequences and zero/negative durations with structured reason codes.
  - `test_harmonize_scene_transitions_tension_differential`: Asserts tension jump $\ge 2$ generates short transitions ($0.20 - 0.35$s), steady tension generates gradual dissolves ($0.35 - 0.75$s), and ultra-short scenes are capped at $30\%$.
  - `test_ken_burns_zoompan_smoothstep`: Asserts presence of smoothstep easing `(on/denom)*(on/denom)*(3-2*(on/denom))` and valid dimensions.
  - `test_ken_burns_still_segments_split`: Confirms scenes $> 15$s are split into 12-15s segments with alternating pan directions, while scenes $< 15$s remain single.
  - `test_svg_overlay_interpolation_and_buffer_reuse`: Validates mustache template interpolation and in-place mutation of pre-allocated NumPy array without memory re-allocation.
- `tests/unit/test_parallel_lanes.py`:
  - `test_lane_profile_parsing_visual_pipeline`: Parses lanes declaring `image_animation` and `video_loop`, rejecting invalid paradigms.
  - `test_config_lanes_json_declares_six_canonical_lanes`: Loads `config/lanes.json` and asserts all 6 canonical lanes have valid visual pipelines.
  - `test_concurrency_render_semaphore_isolation`: Verifies that concurrent rendering respects `_SHORT_RENDER_SEMAPHORE = 2`.

### 7.2. Anti-Regression Guardrail Verification
- `tests/unit/test_anti_regression_guardrails.py`:
  - `REG-01`: Zero Playwright imports in media pipeline.
  - `REG-02`: Zero legacy web renderers or HTML templates.
  - `REG-03`: Zero Pillow frame-by-frame subtitle rasterization loops.
  - `REG-04`: Single-pass atomic FFmpeg filtergraphs without intermediate disk chunks.
  - `REG-05`: Subtitle safe-area margins ($MarginV \ge 240\text{px}$).
  - `REG-06`: Asynchronous stderr reader thread prevents pipe deadlocks.
  - `REG-07`: Zero WGSL shaders on disk.
  - `REG-08`: In-memory compositor buffer reuse (`shape=(1920, 1080, 4)`).
  - `REG-13`: Stream-copy hot path preserves `-c:v copy` and soft `mov_text` muxing without subtitle burn.
  - `REG-14`: Inviolable resource target ceiling ($\le 2$ Cores CPU, $\le 2.0$ GiB RAM).

### 7.3. Generate-Only Smoke Testing
- Full offline dry run across all six canonical lanes using `main.py run --lane <lane_id> --generate-only`:
  - Validates that `video_loop` completes in $< 5.0\text{s}$ with stream-copy.
  - Validates that `image_animation` completes with valid MP4 output and peak RAM $< 800\text{ MiB}$.
  - Confirms zero network requests or browser subprocesses are spawned.

---

## 8. Threat Matrix & Rollback Plan

### 8.1. Threat Matrix

| # | Threat / Failure Mode | Severity | Probability | Mitigation Strategy (Planned Safe Behavior) |
|---|-----------------------|:---:|:---:|--------------------------------------------|
| **TM-01** | **RAM Exhaustion from In-Memory Frames** | High | Low | Enforce native FFmpeg filtergraphs (`zoompan`, `xfade`, `colorbalance`) for disk streaming. Where buffers are required, mutate a single contiguous array (`(1920, 1080, 4)` uint8 = 8.29 MB) in-place (`REG-08`). |
| **TM-02** | **OS Pipe Deadlock on Stderr Buffer** | High | Low | `UnifiedEncoder` spawns background daemon thread `_drain_stderr` reading from `proc.stderr` continuously, preventing the OS 64KB pipe buffer from blocking (`REG-06`). |
| **TM-03** | **CPU Spike Exceeding 2 Cores** | High | Low | Bound FFmpeg subprocesses with `-threads 2` (max `-threads 4`), bound concurrent runs with `_SHORT_RENDER_SEMAPHORE = 2`, and skip video frame decoding during probes with `-vn` (`REG-14`). |
| **TM-04** | **Platform UI Occlusion of Badges & Subtitles** | Med | Low | `enforce_shorts_safe_zone()` enforces $MarginV \ge 460\text{px}$ on vertical 9:16 canvases, clamping typography and HUD overlays out of YouTube Shorts button areas (`REG-05`). |
| **TM-05** | **Missing or Corrupt Still Asset in Animation Lane** | Med | Low | Deterministic 3-tier asset resolution hierarchy: Tier 1 (Curated) $\to$ Tier 2 (Cached Workset) $\to$ Tier 3 (Thematic Video Loop Fallback). System degrades gracefully to stream-copy loop without crashing queue item. |
| **TM-06** | **Concurrent Work Directory Collisions** | Med | Low | Every run operates inside an isolated, timestamped directory `data/runs/{run_id}/`. Database transactions use SQLite WAL mode with worker leases. |
| **TM-07** | **FFmpeg 6.1 Libass Filter Path Escaping Failure** | Med | Low | Use unquoted filter syntax conforming to `REG-12`: unquoted absolute path with escaped colons and backslashes (`libass_filter_clause()`). |

### 8.2. Rollback Plan
1. **Tier 1 (Instantaneous Configuration Rollback)**:
   - If `image_animation` encounters issues in production, channels can be instantly switched back to `video_loop` by editing `config/lanes.json` or passing `--visual-pipeline video_loop` on the CLI. No code deployment or database schema migration is required.
2. **Tier 2 (Runtime Graceful Degradation)**:
   - If Ken Burns filter compilation or SVG overlay rendering throws an unhandled exception, `stage_08_loop.py` and `stage_09_render.py` catch the error, log a structured observability event, and fall back to catalog loop stream-copy composition.
3. **Tier 3 (Atomic Git Reversion)**:
   - Because all changes adhere to existing schema contracts (`RenderSpec`, `LaneProfile`, `BaseVideoCompositor`), reverting the git commit restores previous behavior cleanly with zero residual database corruption.
