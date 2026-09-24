# Tasks: Visual Coherence System and Independent Parallel Production Lanes

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~1,150 - 1,450 lines (~650 lines source, ~550 lines tests, ~150 lines config/schemas) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | 4 Chained PRs (discrete work units aligned with feature-branch-chain) |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Foundation Data Contracts & Declarative Lane Matrix | PR 1 | `.venv/bin/pytest tests/unit/test_parallel_lanes.py tests/unit/test_channels_lanes.py -v` | In-memory lane parser, configuration loader, and contract validator | Revert `src/core/lanes.py`, `config/lanes.json`, `src/core/contracts/render.py` |
| 2 | Core Media Engines (Visual Coherence SSOT & Motion Design) | PR 2 | `.venv/bin/pytest tests/unit/test_visual_coherence.py tests/unit/test_ken_burns_canonical.py tests/unit/test_svg_overlay.py -v` | Standalone media algorithm test harness, synthetic NumPy buffer mutator, and FFmpeg filtergraph parser | Revert `src/media/visual_coherence.py`, `src/media/ken_burns.py`, `src/media/svg_overlay.py` |
| 3 | Pipeline Integration, Stage Segregation & Lane Fallbacks | PR 3 | `.venv/bin/pytest tests/unit/test_parallel_lanes.py tests/unit/test_anti_regression_guardrails.py -k "reg13 or reg14 or reg08 or reg04" -v` | Synthetic `PipelineContext` pipeline runner with isolated temp directories (`data/runs/{run_id}/`) | Revert `src/pipeline/stages/stage_08_loop.py`, `src/pipeline/stages/stage_09_render.py` |
| 4 | Verification, Anti-Regression Guardrails & Smoke Testing | PR 4 | `.venv/bin/pytest tests/unit/test_anti_regression_guardrails.py tests/unit/test_visual_coherence.py tests/unit/test_parallel_lanes.py -v && ./scripts/verify_integrity.sh` | Headless offline pipeline runner with Linux `/proc` resource monitor, smoke harness, and integrity gate | Revert branch commits; fallback to existing baseline |

---

## Phase 1: Foundation & Contracts

- [x] 1.1 **[RED]** Create new test module `tests/unit/test_parallel_lanes.py` defining contract and configuration assertions:
  - `test_allowed_visual_pipelines_contains_dual_paradigms`: Asserts that `{"image_animation", "video_loop"}.issubset(ALLOWED_VISUAL_PIPELINES)`.
  - `test_parse_lane_image_animation`: Asserts `parse_lane()` parses `"visual_pipeline": "image_animation"` cleanly without validation error.
  - `test_parse_lane_video_loop`: Asserts `parse_lane()` parses `"visual_pipeline": "video_loop"` cleanly without validation error.
  - `test_parse_lane_unsupported_visual_pipeline_raises`: Asserts `parse_lane()` with `"visual_pipeline": "unsupported_webgl"` raises `ValueError` listing allowed options.
  - `test_canonical_six_lanes_have_valid_visual_pipelines`: Loads `config/lanes.json` via `load_lanes()` and verifies that all six canonical production lanes define valid `visual_pipeline` properties from `ALLOWED_VISUAL_PIPELINES`.
  - `test_renderspec_visual_pipeline_contract`: Asserts `RenderSpec` includes `visual_pipeline: str = "beats"` and correctly inherits from `PipelineContext.lane.visual_pipeline`.
  - Concrete edit target: `tests/unit/test_parallel_lanes.py` (new test file).
  - Concrete inspection targets: `src/core/lanes.py` (read-only), `config/lanes.json` (read-only), `src/core/contracts/render.py` (read-only).

- [x] 1.2 **[GREEN]** Extend visual pipeline taxonomy in `src/core/lanes.py`:
  - Update `ALLOWED_VISUAL_PIPELINES: Final[frozenset[str]] = frozenset({"beats", "director", "image_animation", "video_loop"})`.
  - Update `LaneProfile` dataclass annotations and docstring documentation to formalize `image_animation` (stills + Ken Burns) and `video_loop` (stream-copy loop).
  - Update `parse_lane()` validation logic and exception message to include all four valid visual pipeline identifiers.
  - Ensure `FALLBACK_LANE_DOCUMENTS` default visual pipeline properties remain valid and non-breaking.
  - Concrete edit target: `src/core/lanes.py`.

- [x] 1.3 **[GREEN]** Declare explicit visual pipelines in `config/lanes.json`:
  - Configure canonical thematic lane documents with explicit `visual_pipeline` attributes:
    - `horror-scp-shorts`: `"visual_pipeline": "image_animation"`
    - `horror-horror-long`: `"visual_pipeline": "director"`
    - `drama-drama-shorts`: `"visual_pipeline": "video_loop"`
    - `drama-aita-long`: `"visual_pipeline": "director"`
    - `scifi-singularity-shorts`: `"visual_pipeline": "image_animation"`
    - `scifi-singularity-long`: `"visual_pipeline": "director"`
  - Ensure all other lane parameters (word budgets, cadence gaps, resolutions) remain intact.
  - Concrete edit target: `config/lanes.json`.

- [x] 1.4 **[GREEN]** Update `RenderSpec` data contract in `src/core/contracts/render.py`:
  - Add `visual_pipeline: str = "beats"` field to `RenderSpec` with validation ensuring it belongs to `ALLOWED_VISUAL_PIPELINES`.
  - Update `RenderSpec.from_pipeline_context(ctx)` to extract `visual_pipeline=ctx.lane.visual_pipeline`.
  - Concrete edit target: `src/core/contracts/render.py`.

- [x] 1.5 **[VERIFY]** Run Phase 1 foundation test suite:
  - Command: `.venv/bin/pytest tests/unit/test_parallel_lanes.py tests/unit/test_channels_lanes.py -v`.
  - Assert 100% pass across all lane contract checks.

---

## Phase 2: Core Media Engines

- [x] 2.1 **[RED]** Create new test module `tests/unit/test_visual_coherence.py` covering visual-script sync, color curves, safe zones, and continuity:
  - `test_timing_scales_to_audio_proportional`: Validates that raw durations `[3.0, 4.0, 5.0]` scaled to 15.0s yield `[3.75, 5.0, 6.25]`, sum equals 15.0 within $\pm 0.05$s, and each duration $\ge 1.0$s.
  - `test_timing_scales_to_audio_rounding_residual`: Asserts that fractional rounding discrepancies (e.g. `[3.33, 3.33, 3.33]` to 10.0s) are fully absorbed by the final scene to equal exactly 10.00s.
  - `test_timing_scales_to_audio_degenerate`: Ensures `target_duration` of `None`, `0.0`, or negative returns raw durations safely without raising `ZeroDivisionError`.
  - `test_build_coherent_color_grade_horror`: Channel `"horror"` or `"moku"` generates `eq=contrast=1.06:saturation=0.88` and cool shadow `colorbalance=rs=-0.02:gs=0.01:bs=0.02`.
  - `test_build_coherent_color_grade_drama`: Channel `"drama"` or `"aelithia"` generates `eq=contrast=1.05:saturation=0.96:brightness=0.01` and warm skin balance `colorbalance=rs=0.02:gs=0.01:bs=-0.03`.
  - `test_build_coherent_color_grade_scifi`: Channel `"scifi"` or `"singularidad"` generates `eq=contrast=1.08:saturation=0.92:brightness=-0.01` and cyan/blue lift `bs=0.04:rh=-0.02:gh=0.02:bh=0.05`.
  - `test_build_coherent_color_grade_fallback`: Unknown channel `"unknown_niche"` or empty string defaults safely to dark ambient horror color grading without `KeyError`.
  - `test_enforce_shorts_safe_zone_vertical`: Resolution 1080x1920 enforces `bottom >= 460`, `top >= 180`, `right >= 130`, `left >= 64`, `safe_width == 1080 - (left + right)`, and `safe_height == 1920 - (top + bottom)`.
  - `test_enforce_shorts_safe_zone_horizontal`: Resolution 1920x1080 enforces `bottom >= 120`, `top >= 80`, `left >= 80`, `right >= 80`, and `safe_width == 1760`.
  - `test_enforce_shorts_safe_zone_arbitrary_aspect`: Resolution 720x1280 scales margins dynamically ($25\%$ bottom, $10\%$ top) with positive integer dimensions.
  - `test_validate_visual_continuity_valid`: Sequence of 4 scenes with durations `[4.0, 5.0, 3.5, 6.0]` returns `valid: True`, `scene_count == 4`, `total_duration == 18.5`, and 3 transition values.
  - `test_validate_visual_continuity_zero_or_negative_duration`: Sequence containing duration `0.0` or `-2.5` returns `valid: False` with reason `"zero_or_negative_duration"`.
  - `test_validate_visual_continuity_empty`: Empty sequence `[]` returns `valid: False` with reason `"empty_scenes"`.
  - `test_harmonize_scene_transitions_tension_differential`: Adjacent scenes with $\Delta T = 3$ return short crossfade ($0.20 - 0.35$s); steady tension $\Delta T = 0$ returns gradual dissolve ($0.35 - 0.75$s); shorter scene capped at $30\%$; single scene returns `[]`.
  - Concrete edit target: `tests/unit/test_visual_coherence.py` (new test file).
  - Concrete inspection target: `src/media/visual_coherence.py` (read-only).

- [x] 2.2 **[GREEN]** Harden Visual Coherence SSOT in `src/media/visual_coherence.py`:
  - Harden `timing_scales_to_audio(raw_durations, target_duration)`: Guard against non-positive raw durations, ensure float conversion, calculate exact fractional diff, and adjust `scaled[-1]` so that `sum(scaled) == round(target_duration, 2)`.
  - Harden `build_coherent_color_grade(accent_hex, primary_hex, channel)`: Enforce exact filmic Rec.709 curves for `horror`, `drama`, and `scifi`, with robust fallback to `horror` on unknown channel keys.
  - Harden `enforce_shorts_safe_zone(width, height)`: Enforce canonical safe-zone geometry ($MarginV \ge 460\text{px}$ bottom, $\ge 180\text{px}$ top, $\ge 130\text{px}$ right, $\ge 64\text{px}$ left for vertical 9:16; $\ge 120\text{px}$ bottom, $\ge 80\text{px}$ top/lateral for horizontal 16:9; dynamic scaling for non-standard resolutions).
  - Export `validate_visual_continuity()` and `harmonize_scene_transitions()` in `__all__` with typed return signatures.
  - Concrete edit target: `src/media/visual_coherence.py`.

- [x] 2.3 **[RED]** Extend motion design tests in `tests/unit/test_ken_burns_canonical.py`:
  - `test_ken_burns_zoompan_smoothstep_expression`: Asserts generated `zoompan` contains smoothstep expression `(on/{denom})*(on/{denom})*(3-2*(on/{denom}))` and valid coordinate formulas.
  - `test_ken_burns_zoompan_pan_cycle_directions`: Asserts correct `x` and `y` formulas for all directions in `KEN_BURNS_PAN_CYCLE` (`center_to_top`, `left_to_right`, `center_to_bottom`, `right_to_left`).
  - `test_ken_burns_zoompan_degenerate_frames`: Asserts `total_frames <= 1` clamps denominator to 1 to prevent division by zero.
  - `test_ken_burns_still_segments_split_threshold`: Asserts still image of exactly 20.0s (the split threshold) splits into 2 segments of 10.0s each; still image $> 15.0$s splits into sub-segments between 10.0s and 15.0s with alternating pan directions; still image of 9.0s remains 1 unsplit segment.
  - Concrete edit target: `tests/unit/test_ken_burns_canonical.py`.
  - Concrete inspection target: `src/media/ken_burns.py` (read-only).

- [x] 2.4 **[GREEN]** Harden Ken Burns Camera Motion Planner in `src/media/ken_burns.py`:
  - Ensure `build_ken_burns_zoompan_filter()` builds smoothstep easing `(on/denom)*(on/denom)*(3-2*(on/denom))` for zoom and pan interpolation, clamping denominator to `max(1, total_frames - 1)`.
  - Update `plan_ken_burns_still_segments()`: Ensure still scenes exceeding `KEN_BURNS_SEGMENT_MAX_SEC = 15.0` (or reaching `KEN_BURNS_SPLIT_THRESHOLD_SEC = 20.0`) are partitioned into sub-segments within $[10.0, 15.0]$ seconds, assigning alternating pan directions from `KEN_BURNS_PAN_CYCLE`.
  - Handle degenerate boundary cases (`duration_sec <= 0.5`, `total_frames <= 1`) safely.
  - Concrete edit target: `src/media/ken_burns.py`.

- [x] 2.5 **[RED]** Extend SVG overlay tests in `tests/unit/test_svg_overlay.py`:
  - `test_svg_overlay_buffer_shape_mismatch`: Asserts `render_overlay()` with buffer having incorrect shape (e.g. `(1280, 720, 4)` vs requested 1080x1920) or incorrect dtype raises `ValueError`.
  - `test_svg_overlay_mustache_and_single_brace_interpolation`: Asserts `interpolate_template()` replaces both `{{key}}` and `{key}` without residual placeholders.
  - `test_svg_overlay_raster_lru_cache_bounds`: Asserts raster cache is bounded at 128 entries to prevent unbounded resident memory growth.
  - Concrete edit target: `tests/unit/test_svg_overlay.py`.
  - Concrete inspection target: `src/media/svg_overlay.py` (read-only).

- [x] 2.6 **[GREEN]** Harden `SVGOverlayEngine` in `src/media/svg_overlay.py`:
  - Ensure `render_overlay()` validates `out_buffer` shape (`shape == (height, width, 4)`) and `dtype == np.uint8`, raising `ValueError` on mismatch to prevent memory corruption or buffer overrun.
  - Ensure template parameter interpolation supports both `{{param}}` and `{param}` syntax tokens.
  - Cap `_raster_cache` at 128 entries using LRU/FIFO eviction to preserve the $\le 2.0\text{ GiB}$ RAM ceiling.
  - Ensure transparent zero-fill for `"none"` or empty presets.
  - Concrete edit target: `src/media/svg_overlay.py`.

- [x] 2.7 **[VERIFY]** Run Phase 2 core media engine test suite:
  - Command: `.venv/bin/pytest tests/unit/test_visual_coherence.py tests/unit/test_ken_burns_canonical.py tests/unit/test_svg_overlay.py -v`.
  - Assert 100% pass across all visual coherence and motion engine test cases.

---

## Phase 3: Pipeline Integration & Lane Segregation

- [x] 3.1 **[RED]** Add pipeline integration tests in `tests/unit/test_parallel_lanes.py`:
  - `test_stage_08_loop_scene_video_loop_lane`: Asserts that when `ctx.lane.visual_pipeline == "video_loop"`, `stage_08_loop_scene` resolves catalog loop, sets `ctx.stream_copy_mode = True`, and sets `ctx.mux_subtitles = True` without invoking still image planner.
  - `test_stage_08_loop_scene_image_animation_lane`: Asserts that when `ctx.lane.visual_pipeline == "image_animation"`, `stage_08_loop_scene` sets `ctx.stream_copy_mode = False`, resolves still assets, scales scene durations via `timing_scales_to_audio()`, and plans Ken Burns camera motion.
  - `test_stage_09_render_video_loop_stream_copy`: Asserts that when `visual_pipeline == "video_loop"`, `stage_09_video_rendering` delegates to `ctx.loop_engine.render()` with `stream_copy=True`, executing with stream-copy `-c:v copy` and soft `mov_text` muxing without burning subtitles (`REG-13`).
  - `test_stage_09_render_image_animation_unified_encoder`: Asserts that when `visual_pipeline == "image_animation"`, `stage_09_video_rendering` delegates to `UnifiedEncoder` or `MultiSceneCompositor` for single-pass atomic transcode with `libass` subtitle burn and `-threads 2`.
  - `test_stage_09_render_fallback_to_video_loop_on_failure`: Asserts that if image animation transcode raises an exception, stage 09 catches the error, logs an observability event, and falls back to catalog loop composition to produce a valid MP4 artifact.
  - `test_semaphore_concurrency_isolation`: Asserts short renders acquire `_SHORT_RENDER_SEMAPHORE = 2` and long renders acquire `_LONG_RENDER_SEMAPHORE = 1`.
  - Concrete edit target: `tests/unit/test_parallel_lanes.py`.
  - Concrete inspection targets: `src/pipeline/stages/stage_08_loop.py` (read-only), `src/pipeline/stages/stage_09_render.py` (read-only).

- [x] 3.2 **[GREEN]** Refactor Stage 08 Scene Manifest Builder in `src/pipeline/stages/stage_08_loop.py`:
  - Inspect `ctx.lane.visual_pipeline`:
    - For `"video_loop"`: Force `ctx.stream_copy_mode = True`, `ctx.mux_subtitles = bool(ctx.subtitles_active and ctx.ass_path.is_file())`, resolve continuous catalog loop, build loop manifest.
    - For `"image_animation"`: Force `ctx.stream_copy_mode = False`, `ctx.mux_subtitles = False` (subtitles burned via libass in unified encoder), resolve still assets, scale scene durations via `timing_scales_to_audio()`, validate continuity via `validate_visual_continuity()`, and compile Ken Burns motion metadata.
    - For `"beats"` / `"director"`: Retain existing multi-scene / catalog loop planning.
  - Invoke `memory_checkpoint("8_loop_scene")` at phase entry and exit to release unreferenced buffers.
  - Maintain function logic within the ~100-line budget by delegating discrete helpers.
  - Concrete edit target: `src/pipeline/stages/stage_08_loop.py`.

- [x] 3.3 **[GREEN]** Refactor Stage 09 Video Rendering in `src/pipeline/stages/stage_09_render.py`:
  - Route execution cleanly based on `ctx.lane.visual_pipeline`:
    - For `"video_loop"`: Invoke `ctx.loop_engine.render()` with `stream_copy=True`, utilizing `-c:v copy` and soft `mov_text` muxing (`REG-13`).
    - For `"image_animation"`: Invoke `UnifiedEncoder` or `MultiSceneCompositor` for single-pass atomic transcode, enforcing thread bounding (`-threads 2`), background `_drain_stderr` reader, and disk streaming without in-memory frame buffer loops (`REG-04`, `REG-06`, `REG-08`, `REG-14`).
    - Implement runtime graceful degradation: upon caught exception in image animation transcode, log structured observability event and fall back to catalog loop stream-copy composition.
  - Ensure all renders execute inside `render_sem` (`_SHORT_RENDER_SEMAPHORE = 2` for shorts, `_LONG_RENDER_SEMAPHORE = 1` for longform) and `active_heartbeat_scope(ctx)`.
  - Concrete edit target: `src/pipeline/stages/stage_09_render.py`.
  - Concrete inspection targets: `src/media/unified_encoder.py` (read-only), `src/media/interface.py` (read-only).

- [x] 3.4 **[GREEN]** Verify CLI `--visual-pipeline` override integration:
  - Verify that `main.py run --lane <lane_id> --visual-pipeline <pipeline>` allows operator override of lane visual pipeline for rapid operational switching and troubleshooting.
  - Concrete inspection target: `main.py` (read-only).

- [x] 3.5 **[VERIFY]** Run Phase 3 pipeline integration test suite:
  - Command: `.venv/bin/pytest tests/unit/test_parallel_lanes.py -v`.
  - Assert 100% pass across all pipeline routing, semaphore bounding, and fallback scenarios.

---

## Phase 4: Verification & Smoke Testing

- [x] 4.1 **[RED]** Verify anti-regression guardrail coverage in `tests/unit/test_anti_regression_guardrails.py`:
  - Verify `REG-01`: Zero Playwright imports in media pipeline.
  - Verify `REG-03`: Zero Pillow frame-by-frame subtitle rasterization loops.
  - Verify `REG-04`: Single-pass atomic FFmpeg filtergraphs without intermediate disk chunks.
  - Verify `REG-05`: Subtitle safe-area margins ($MarginV \ge 240\text{px}$).
  - Verify `REG-06`: Asynchronous stderr reader thread prevents pipe deadlocks.
  - Verify `REG-08`: In-memory compositor buffer reuse (`shape=(1920, 1080, 4)` uint8).
  - Verify `REG-13`: Stream-copy hot path preserves `-c:v copy` and soft `mov_text` muxing without subtitle burn.
  - Verify `REG-14`: Inviolable resource target ceiling ($\le 2$ Cores CPU, $\le 2.0$ GiB RAM).
  - Concrete inspection target: `tests/unit/test_anti_regression_guardrails.py` (read-only).

- [x] 4.2 **[GREEN]** Execute full anti-regression guardrail suite:
  - Command: `.venv/bin/pytest tests/unit/test_anti_regression_guardrails.py -v`.
  - Assert all 28 invariant checks pass cleanly (100% green).

- [x] 4.3 **[GREEN]** Execute offline generate-only smoke test across all six canonical lanes:
  - Run `main.py run --lane horror-scp-shorts --generate-only` (validating `image_animation`).
  - Run `main.py run --lane drama-drama-shorts --generate-only` (validating `video_loop`).
  - Run `main.py run --lane scifi-singularity-shorts --generate-only` (validating `image_animation`).
  - Run `main.py run --lane horror-horror-long --generate-only` (validating longform `director`).
  - Run `main.py run --lane drama-aita-long --generate-only` (validating longform `director`).
  - Run `main.py run --lane scifi-singularity-long --generate-only` (validating longform `director`).
  - Assert zero external network requests, zero browser subprocesses, valid MP4 video artifacts, and execution within the resource budget.
  - Concrete inspection target: `main.py` (read-only).

- [x] 4.4 **[GREEN]** Execute MCP synchronization check:
  - Command: `.venv/bin/python3 scripts/verify_mcp_sync.py`.
  - Assert 100% bidirectional parity across tools, resources, prompts, configs, and docs.

- [x] 4.5 **[GREEN]** Execute mandatory integrity SLA audit:
  - Command: `./scripts/verify_integrity.sh`.
  - Assert exit code 0 and all integrity SLA checks pass.
