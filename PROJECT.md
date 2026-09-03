# Project: yt-auto Visual Pipeline Redesign & Migration

## Architecture
The new Visual Pipeline eradicates browser-based rendering (Playwright/Chromium/SwiftShader), Pillow GIL bottlenecks, and multi-pass intermediate disk transcodings. It replaces them with a zero-copy, deterministic, high-throughput pipeline:

1. **Procedural Base Layer (`src/media/native_procedural.py`)**:
   - Native WebGPU via `wgpu-py` with WGSL fragment shaders (`cosmic_singularity.wgsl`, `dark_forest.wgsl`, `synaptic_network.wgsl`, `tactical_chamber.wgsl`).
   - Hardware GPU execution with automatic fallback to Mesa Lavapipe/llvmpipe software Vulkan rasterizer (`/usr/share/vulkan/icd.d/lvp_icd.json`).
   - 64-byte aligned uniform layout (`std140`) and 256-byte row stride staging buffer alignment.

2. **Vector Overlay Layer (`src/media/svg_overlay.py`)**:
   - Declarative SVG HUD & telemetry rasterization via `resvg-py` (Rust-based SVG 1.1/2.0 engine).
   - In-memory caching for static elements and dynamic XML interpolation for telemetry timestamps/metrics.
   - Vector assets catalog in `assets/svg_overlays/` (`hud_tactical_telemetry.svg`, `scp_classification_stamp.svg`, `biometric_wave.svg`).

3. **In-Memory Frame Compositor (`src/media/inmemory_compositor.py`)**:
   - Zero-allocation reusable NumPy contiguous memory views (`_base_buffer`, `_overlay_buffer`, `_out_buffer`).
   - SIMD Porter-Duff Over alpha blending with sparse alpha fast-path bypass (<1ms).
   - Direct memoryview stream writing to FFmpeg stdin (`pipe:0`).

4. **Unified Atomic FFmpeg Pipeline (`src/media/unified_encoder.py`)**:
   - Single-pass atomic transcoding using `-filter_complex` combining raw RGBA video, `libass` typography burning, voice narration, drone bed, and SFX.
   - Sidechain ducking (`sidechaincompress`) and EBU R128 broadcast loudness normalization (`loudnorm=I=-14:TP=-1.5:LRA=11`).
   - Background daemon thread continuously draining `stderr` to prevent OS pipe buffer deadlocks and handle `BrokenPipeError`.
   - Zero intermediate MP4/WAV files on disk.

5. **Typography & Subtitles (`src/media/subtitles_ass.py`)**:
   - Programmatic `.ass` script generation with word-level karaoke timing (`{\kf<duration>}`).
   - Monotonic timestamp sanitizer enforcing $t_{start}[n] \ge t_{end}[n-1] + \epsilon$.
   - Enforced 260px vertical margin (safe area for YouTube Shorts UI).
   - Hermetic font loading from `assets/fonts/` (`Montserrat-Black.ttf`, `Inter-Bold.ttf`).

6. **Contracts & Deterministic QA (`src/scene_manifest.py` & `src/agents/video_qa.py`)**:
   - Strongly typed `VisualArchetypeId` Enum in Pydantic v2 and Draft-07 JSON Schema (`schemas/scene_manifest.schema.json`).
   - Deterministic multi-tier video QA gate inspecting container (`has_faststart`, `yuv420p`), EBU R128 loudness, black/freeze frames, and A/V sync.
   - Synchronized documentation in `docs/`.

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F01 | Legacy Code & Template Deletion | Physically delete `web_renderer.py`, `realtime_video_engine.py`, `web_templates/`, obsolete dev scripts, and legacy tests. | M1 | Survey 1 / R1 |
| F02 | Media Exports & Registry Refactor | Decouple `src/media/__init__.py`, `loop_worker.py`, `proc_engine.py`, and `src/cli/handlers/loop.py` from legacy renderers. | M1 | Survey 1 / R1 |
| F03 | Pipeline Branch Pruning | Prune orphan `is_multiscene_mode` browser branches in `src/pipeline.py`. | M1 | Survey 1 / R1 |
| F04 | Native Procedural Engine (`wgpu-py`) | Implement `NativeProceduralEngine` with WebGPU adapter discovery and Lavapipe software fallback. | M2 | Survey 2 / R2 |
| F05 | WGSL Shaders Catalog | Implement 4 WGSL shaders (`cosmic_singularity.wgsl`, `dark_forest.wgsl`, `synaptic_network.wgsl`, `tactical_chamber.wgsl`). | M2 | Survey 2 / R2 |
| F06 | SVG Overlay Engine (`resvg-py`) | Implement `SVGOverlayEngine` with XML parameter interpolation and in-memory raster caching. | M2 | Survey 2 / R2 |
| F07 | SVG Vector Assets Catalog | Provision `assets/svg_overlays/` (`hud_tactical_telemetry.svg`, `scp_classification_stamp.svg`, `biometric_wave.svg`). | M2 | Survey 2 / R2 |
| F08 | In-Memory Frame Compositor | Implement `InMemoryCompositor` with zero-allocation NumPy buffers and SIMD alpha blending. | M2 | Survey 2 / R2 |
| F09 | ASS Subtitle Generator | Implement `subtitles_ass.py` with karaoke formatting, safe-area (260px), and font hermeticity. | M3 | Survey 3 / R3 |
| F10 | Monotonic Timestamp Sanitizer | Implement timestamp sanitizer ensuring causality and strict monotonicity in `subtitles_ass.py`. | M3 | Survey 3 / R3 |
| F11 | Unified Atomic FFmpeg Encoder | Implement `unified_encoder.py` with `-filter_complex`, libass, ducking, EBU R128, and async stderr drain. | M3 | Survey 3 / R3 |
| F12 | SceneManifest Contract Synchronization | Synchronize `src/scene_manifest.py` and `schemas/scene_manifest.schema.json` with `VisualArchetypeId`. | M4 | Survey 3 / R4 |
| F13 | Scene Planner Agent Sync | Update `src/agents/scene_planner.py` to resolve strongly typed archetype tokens. | M4 | Survey 3 / R4 |
| F14 | Deterministic Video QA Gate | Integrate `audit_rendered_video_artifact` in `src/agents/video_qa.py` into the production pipeline. | M4 | Survey 3 / R4 |
| F15 | Documentation Synchronization | Update `docs/ARQUITECTURA.md`, `docs/FLUJO_VIDEOS.md`, `docs/INTEGRACIONES_Y_SERVICIOS.md`, `docs/TROUBLESHOOTING.md`, `README.md`. | M4 | Survey 3 / R4 |
| F16 | E2E Testing Suite (Tiers 1–4) | Build opaque-box test runner and test cases covering all features, boundaries, combinations, and real-world workloads. | E2E-TEST | Dual Track |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Saneamiento y Poda Estructural | Physical deletion of legacy files, pruning orphan branches in `src/pipeline.py`, updating media exports and unit tests. (F01, F02, F03) | none | PLANNED |
| M2 | Motor Procedural y Overlays Vectoriales | Implementation of `native_procedural.py`, WGSL shaders, `svg_overlay.py`, SVG assets, and `inmemory_compositor.py`. (F04, F05, F06, F07, F08) | M1 | PLANNED |
| M3 | Pipeline Atómico Unificado de FFmpeg | Implementation of `subtitles_ass.py` (karaoke + sanitizer) and `unified_encoder.py` (atomic FFmpeg + async stderr drain). (F09, F10, F11) | M2 | PLANNED |
| M4 | Sincronización de Contratos y QA Determinista | Pydantic model & JSON Schema synchronization, `scene_planner.py` update, deterministic QA gate in `video_qa.py`, documentation updates. (F12, F13, F14, F15) | M3 | PLANNED |
| E2E | E2E Testing Suite (Tiers 1–4) | Independent opaque-box test runner and comprehensive test suite across Tiers 1–4, publishing `TEST_READY.md`. (F16) | none | PLANNED |
| FINAL | E2E Test Pass & Adversarial Hardening | Phase 1: 100% pass on Tiers 1–4 E2E tests. Phase 2: Tier 5 white-box adversarial stress testing and hardening. | M4, E2E | PLANNED |

---

## Interface Contracts

### 1. `NativeProceduralEngine` ↔ `InMemoryCompositor`
- **Signature:**
  ```python
  def render_frame(
      self,
      width: int,
      height: int,
      time_sec: float,
      duration_sec: float,
      archetype_id: str,
      tension: int = 1,
      seed: int = 42,
      params: Optional[Dict[str, Any]] = None,
      out_buffer: Optional[np.ndarray] = None,
  ) -> np.ndarray:
  ```
- **Data Type:** Returns `np.ndarray` of shape `(height, width, 4)` and `dtype=np.uint8` in RGBA color space.
- **Buffer Invariant:** If `out_buffer` is provided, renders directly into the contiguous slice without reallocating.

### 2. `SVGOverlayEngine` ↔ `InMemoryCompositor`
- **Signature:**
  ```python
  def render_overlay(
      self,
      preset_name: str,
      width: int,
      height: int,
      time_sec: float,
      params: Optional[Dict[str, Any]] = None,
      out_buffer: Optional[np.ndarray] = None,
  ) -> np.ndarray:
  ```
- **Data Type:** Returns `np.ndarray` of shape `(height, width, 4)` and `dtype=np.uint8` in RGBA color space. Returns zero array if `preset_name == "none"` or overlay is inactive.

### 3. `InMemoryCompositor` ↔ `UnifiedEncoder`
- **Signature:**
  ```python
  class InMemoryCompositor:
      def __init__(self, width: int = 1080, height: int = 1920) -> None: ...
      def composite_frame(self, base_rgba: np.ndarray, overlay_rgba: Optional[np.ndarray] = None) -> np.ndarray: ...
      def get_memoryview(self) -> memoryview: ...
  ```
- **Data Flow:** `encoder.write_frame(compositor.get_memoryview())` or `encoder.write_frame(compositor.out_buffer.tobytes())`.

### 4. `ASSSubtitleGenerator` ↔ `UnifiedEncoder`
- **Signature:**
  ```python
  def generate_ass_file(
      self,
      word_timestamps: List[Dict[str, Any]],
      output_path: Path,
      video_width: int = 1080,
      video_height: int = 1920,
      theme_name: str = "scp_emerald",
      words_per_cue: int = 3,
  ) -> Path:
  ```
- **Output:** Writes standard `.ass` script (V4+ Styles) with `MarginV=260` and `fontsdir` pointing to `assets/fonts`.

### 5. `UnifiedEncoder` ↔ File System & Consumers
- **Signature:**
  ```python
  class UnifiedEncoder:
      def __init__(
          self,
          output_mp4: Path,
          width: int = 1080,
          height: int = 1920,
          fps: int = 30,
          crf: int = 18,
          preset: str = "fast",
          voice_wav: Optional[Path] = None,
          drone_wav: Optional[Path] = None,
          sfx_wavs: Optional[List[Tuple[Path, float, float]]] = None,
          ass_subtitle_path: Optional[Path] = None,
          fonts_dir: Optional[Path] = None,
          enable_nvenc: bool = False,
      ) -> None: ...
      def __enter__(self) -> "UnifiedEncoder": ...
      def write_frame(self, frame_data: Union[bytes, memoryview, np.ndarray]) -> None: ...
      def finish(self) -> None: ...
  ```
- **Error Handling:** Raises `RuntimeError` with full captured stderr tail upon subprocess exit or `BrokenPipeError`.

---

## Code Layout
```text
src/
├── agents/
│   ├── scene_planner.py          # Updated with VisualArchetypeId tokens
│   └── video_qa.py               # Deterministic QA gate entry point
├── media/
│   ├── inmemory_compositor.py    # Zero-allocation NumPy frame compositor
│   ├── loop_engine.py            # Offline loop background video engine
│   ├── native_procedural.py      # wgpu-py WebGPU engine with Lavapipe fallback
│   ├── shaders/                  # WGSL fragment shader catalog
│   │   ├── cosmic_singularity.wgsl
│   │   ├── dark_forest.wgsl
│   │   ├── synaptic_network.wgsl
│   │   └── tactical_chamber.wgsl
│   ├── subtitles_ass.py          # libass ASS subtitle generator with karaoke
│   ├── svg_overlay.py            # resvg-py SVG HUD & vector overlay engine
│   ├── thumbnail_engine.py       # Single-frame thumbnail generation
│   └── unified_encoder.py        # Single-pass atomic FFmpeg transcode pipeline
├── pipeline.py                   # Master unified pipeline orchestrator
└── scene_manifest.py             # Pydantic v2 data models with VisualArchetypeId

assets/
├── fonts/
│   ├── Montserrat-Black.ttf
│   └── Inter-Bold.ttf
└── svg_overlays/
    ├── hud_tactical_telemetry.svg
    ├── scp_classification_stamp.svg
    └── biometric_wave.svg

schemas/
└── scene_manifest.schema.json    # Draft-07 JSON Schema synchronized with VisualArchetypeId

tests/
├── e2e/                          # Requirement-driven opaque-box E2E test suite
│   ├── runner.py
│   ├── test_tier1_features.py
│   ├── test_tier2_boundaries.py
│   ├── test_tier3_combinations.py
│   └── test_tier4_workloads.py
├── integration/
│   ├── test_pipeline_determinism.py
│   └── test_unified_encoder.py
└── unit/
    ├── test_inmemory_compositor.py
    ├── test_native_procedural.py
    ├── test_subtitles_ass.py
    └── test_svg_overlay.py
```
