# Tasks: Local Video Graphics Bank, Visual Coherence & High-Impact Graphic Designs

## Review Workload Forecast

| Field | Value |
| :--- | :--- |
| Estimated changed lines | ~1,850 - 2,250 lines (~750 lines Python source, ~250 lines JSON manifest, ~300 lines SVG XML, ~750 lines test suites, plus 8 procedural PNG assets < 200 KB each) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Chain strategy | feature-branch-chain |
| Delivery strategy | auto-chain |
| Decision needed before apply | No |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Test Harness & RED Test Suites | PR 1 | `.venv/bin/pytest tests/unit/test_graphics_bank.py tests/unit/test_graphic_designs.py -v` | Pytest harness capturing RED failure states for manifest schema, query filtering, asset existence, and vector safe zones | Revert `tests/unit/test_graphics_bank.py`, `tests/unit/test_graphic_designs.py` |
| 2 | Core Graphics Bank Registry & Declarative Manifest | PR 2 | `.venv/bin/pytest tests/unit/test_graphics_bank.py -v` | In-memory `GraphicsBank` registry with filesystem path verification, category/affinity filtering, and preflight integrity probe | Revert `src/media/graphics_bank.py`, `assets/graphics_manifest.json` |
| 3 | Procedural Asset Generator & Graphic Asset Suites | PR 3 | `.venv/bin/pytest tests/unit/test_graphic_designs.py -v && python3 scripts/generate_graphic_assets.py --verify` | Headless Pillow/NumPy procedural image synthesis CLI, 8 static atmospheric RGBA PNGs, and 5 new SVG templates + 3 modernized | Revert `scripts/generate_graphic_assets.py`, `assets/overlays/static/`, `assets/svg_overlays/` |
| 4 | Engine Integration, Bounded LRU Cache & Visual Coherence | PR 4 | `.venv/bin/pytest tests/unit/test_svg_overlay.py tests/unit/test_visual_coherence.py -v` | `SVGOverlayEngine` with bounded LRU cache (maxsize=128), zero-allocation buffers, Pillow fallback, `overlays.py` resolver, and opacity clamping [0.15, 0.35] | Revert `src/media/svg_overlay.py`, `src/media/overlays.py`, `src/media/visual_coherence.py`, `src/media/__init__.py` |
| 5 | Full Pipeline Verification, Resource Benchmark & Governance Gate | PR 5 | `./scripts/verify_integrity.sh && .venv/bin/pytest tests/unit/test_anti_regression_guardrails.py -v` | Complete repository integrity verification script, anti-regression suite (`REG-01` to `REG-14`), and memory/CPU resource profiling (<= 2 cores, <= 2.0 GiB RAM) | Revert verification scripts/benchmarks |

---

## Implementation Tasks

### Phase 1: Test Infrastructure & RED Test Cases

- [x] 1.1 **[RED]** Create new test suite `tests/unit/test_graphics_bank.py` defining core registry, query, and validation assertions:
  - `test_manifest_loading_happy_path`: Validates that `GraphicsBank.load_manifest()` parses `assets/graphics_manifest.json` into immutable `GraphicAsset` records, verifies count, field types, and heap memory footprint ($< 2.0\text{ MiB}$).
  - `test_manifest_missing_required_field_rejection`: Asserts that an entry lacking mandatory fields (`category` or `relative_path`) raises a descriptive `ValueError`.
  - `test_manifest_duplicate_id_rejection`: Asserts that duplicate asset identifiers in the manifest raise `ValueError`.
  - `test_manifest_invalid_enum_rejection`: Asserts that unsupported categories (e.g. `"unsupported_3d"`) or channel affinities (e.g. `"vlog"`) raise `ValueError`.
  - `test_manifest_path_traversal_rejection`: Asserts that relative paths attempting directory traversal (e.g. `../../etc/passwd`) or absolute paths are rejected with `ValueError` (TM-01).
  - `test_query_by_category_and_channel`: Validates conjunction filtering across categories and channel niches (`horror`, `drama`, `scifi`).
  - `test_query_channel_wildcard`: Verifies assets with `channel_affinity == "all"` (such as `dark_vignette`) match queries for any specific channel.
  - `test_query_aspect_ratio_filtering`: Verifies filtering for `"9:16"` vs `"16:9"`.
  - `test_query_tag_filtering`: Verifies case-insensitive keyword tag filtering (`"vhs"`, `"camcorder"`).
  - `test_get_asset_lookup`: Tests `bank.get_asset("rec_analog_hud")` returns `GraphicAsset` and `bank.get_asset("unknown_id")` returns `None`.
  - `test_resolve_atmospheric_path`: Verifies resolution of physical file paths for `vignette`, `film_grain`, `particles` (with `particle_type="embers"`), `tv_static`, and `god_rays`.
  - `test_clamp_asset_opacity`: Verifies opacity bounds $[0.15, 0.35]$ on atmospheric assets and passthrough for non-atmospheric assets.
  - `test_validate_bank_integrity_all_pass`: Verifies `BankValidationReport.valid == True` when all registered files exist on disk with valid headers.
  - `test_validate_bank_missing_file_detection`: Verifies missing on-disk files are flagged in `missing_assets` with `valid == False`.
  - `test_validate_bank_oversized_file_detection`: Verifies assets exceeding $200\text{ KB}$ (PNG) or $500\text{ KB}$ (SVG) are captured in `oversized_assets`.
  - Concrete edit target: `tests/unit/test_graphics_bank.py` (new test file).

- [x] 1.2 **[RED]** Create new test suite `tests/unit/test_graphic_designs.py` defining assertions for physical overlay assets and procedural generation CLI:
  - `test_all_static_atmospheric_overlays_exist`: Confirms all 8 expected files exist in `assets/overlays/static/` (`dark_vignette.png`, `soft_vignette.png`, `film_grain.png`, `tv_static.png`, `particles.png`, `particles_dust.png`, `particles_embers.png`, `god_rays.png`).
  - `test_static_atmospheric_overlays_mirrored_in_root`: Confirms all 8 atmospheric files are mirrored in `assets/overlays/` for backward compatibility.
  - `test_static_atmospheric_overlays_rgba_mode`: Validates mode is `"RGBA"`, dimensions $\ge 1080\times 1920$ (or $1920\times 1080$), and non-zero alpha variance across pixels.
  - `test_static_atmospheric_overlays_file_size_budget`: Validates every static PNG is strictly $< 200\text{ KB}$ (204,800 bytes) and total size $< 1.5\text{ MB}$.
  - `test_all_svg_templates_exist_and_parse_xml`: Confirms all 8 SVG templates exist in `assets/svg_overlays/` (`rec_analog_hud.svg`, `cinematic_scope_bars.svg`, `classified_warning_banner.svg`, `drama_quote_card.svg`, `cyber_data_stream.svg`, `hud_tactical_telemetry.svg`, `scp_classification_stamp.svg`, `biometric_wave.svg`) and parse cleanly with standard `xml.etree.ElementTree`.
  - `test_svg_templates_safe_zone_conformance`: Evaluates coordinate anchors of all 8 templates against `enforce_shorts_safe_zone(1080, 1920)`:
    - Top elements reside at $y \ge 180\text{px}$.
    - Bottom elements reside at $y \le 1460\text{px}$.
    - Lateral elements reside within $x \in [64\text{px}, 950\text{px}]$.
  - `test_generate_graphic_assets_cli_verify`: Invokes `python3 scripts/generate_graphic_assets.py --verify` as a subprocess and asserts exit code 0.
  - `test_generate_graphic_assets_cli_idempotent`: Invokes `python3 scripts/generate_graphic_assets.py` without `--force` when assets exist, asserting zero re-writes and runtime $< 1.0\text{ s}$.
  - Concrete edit target: `tests/unit/test_graphic_designs.py` (new test file).

- [x] 1.3 **[RED]** Extend `tests/unit/test_svg_overlay.py` with failing assertions for new templates, bounded LRU cache, and graceful fallback:
  - `test_render_overlay_all_8_presets`: Parametrized test asserting that all 8 catalog presets render valid RGBA frames of shape `(1920, 1080, 4)` and `(960, 540, 4)`.
  - `test_render_overlay_graceful_fallback_without_resvg`: Mocks `resvg_py = None` and verifies `SVGOverlayEngine.render_overlay()` falls back to Pillow rasterization, returning valid uint8 NumPy array without raising `RuntimeError`.
  - `test_render_overlay_lru_cache_eviction_at_128`: Renders 130 unique parameter combinations, asserts `len(engine._raster_cache) <= 128`, and verifies the least-recently used entry is evicted (`popitem(last=False)`).
  - `test_render_overlay_cache_info_and_clear`: Asserts `engine.cache_info()` returns hit/miss counters and current size, and `engine.clear_cache()` flushes cached frames cleanly.
  - `test_render_overlay_missing_parameters_clean_fallback`: Asserts that invoking `interpolate_template()` with `{}` retains default text embedded in the SVG XML and leaves no residual unreplaced `{{param}}` or `{param}` tokens.
  - Concrete edit target: `tests/unit/test_svg_overlay.py` (extended test file).

- [x] 1.4 **[RED]** Extend `tests/unit/test_visual_coherence.py` with tests for opacity clamping and safe-zone checking helpers:
  - `test_clamp_atmospheric_overlay_opacity_boundaries`: Validates clamping behavior for values below min ($0.05 \to 0.15$), above max ($0.65 \to 0.35$), within band ($0.28 \to 0.28$), default fallback (`None \to 0.25`), and zero disabling ($0.0 \to 0.0$).
  - `test_validate_graphic_element_safe_zone_vertical`: Tests bounding box validation function against vertical 9:16 safe zone, confirming rejection of elements with $y > 1460\text{px}$ or $y < 180\text{px}$ or $x > 950\text{px}$ or $x < 64\text{px}$.
  - `test_validate_graphic_element_safe_zone_horizontal`: Tests bounding box validation against horizontal 16:9 safe zone ($MarginV_{bottom} \ge 120\text{px}$, $MarginV_{top} \ge 80\text{px}$, lateral $MarginH \ge 80\text{px}$).
  - Concrete edit target: `tests/unit/test_visual_coherence.py` (extended test file).

- [x] 1.5 **[VERIFY]** Run Phase 1 RED test verification:
  - Execute `.venv/bin/pytest tests/unit/test_graphics_bank.py tests/unit/test_graphic_designs.py -v`.
  - Confirm tests fail cleanly with expected missing module and missing asset errors (RED state confirmed).

---

### Phase 2: Core Graphics Bank & Manifest SSOT

- [x] 2.1 **[GREEN]** Implement typed enums and dataclasses in `src/media/graphics_bank.py`:
  - Implement `GraphicCategory(str, Enum)`: `ATMOSPHERIC = "atmospheric"`, `VECTOR_HUD = "vector_hud"`, `FRAMING = "framing"`, `TYPOGRAPHY = "typography"`.
  - Implement `GraphicChannelAffinity(str, Enum)`: `HORROR = "horror"`, `DRAMA = "drama"`, `SCIFI = "scifi"`, `ALL = "all"`.
  - Implement `@dataclass(frozen=True)` `GraphicAsset`:
    - Fields: `id: str`, `name: str`, `category: GraphicCategory`, `channel_affinity: GraphicChannelAffinity`, `aspect_ratios: Tuple[str, ...]`, `relative_path: str`, `safe_zone_compliant: bool`, `default_opacity: float`, `dynamic_params: Dict[str, str] = field(default_factory=dict)`, `tags: Tuple[str, ...] = field(default_factory=tuple)`.
    - Method: `resolve_path(self, base_dir: Path) -> Path` returning `(base_dir / self.relative_path).resolve()`.
  - Implement `@dataclass(frozen=True)` `BankValidationReport`:
    - Fields: `valid: bool`, `total_assets: int`, `verified_assets: int`, `missing_assets: Tuple[str, ...]`, `corrupted_assets: Tuple[str, ...]`, `oversized_assets: Tuple[str, ...]`, `errors: Tuple[str, ...]`.
  - Concrete edit target: `src/media/graphics_bank.py` (new file).

- [x] 2.2 **[GREEN]** Create declarative single source of truth manifest `assets/graphics_manifest.json`:
  - Define schema version `"1.0.0"`.
  - Register all 8 static atmospheric overlays:
    - `dark_vignette` (`atmospheric`, `all`, `["9:16", "16:9"]`, `assets/overlays/static/dark_vignette.png`, default opacity 0.25).
    - `soft_vignette` (`atmospheric`, `all`, `["9:16", "16:9"]`, `assets/overlays/static/soft_vignette.png`, default opacity 0.25).
    - `film_grain` (`atmospheric`, `all`, `["9:16", "16:9"]`, `assets/overlays/static/film_grain.png`, default opacity 0.20).
    - `tv_static` (`atmospheric`, `horror`, `["9:16", "16:9"]`, `assets/overlays/static/tv_static.png`, default opacity 0.20).
    - `particles` (`atmospheric`, `all`, `["9:16", "16:9"]`, `assets/overlays/static/particles.png`, default opacity 0.25).
    - `particles_dust` (`atmospheric`, `drama`, `["9:16", "16:9"]`, `assets/overlays/static/particles_dust.png`, default opacity 0.20).
    - `particles_embers` (`atmospheric`, `horror`, `["9:16", "16:9"]`, `assets/overlays/static/particles_embers.png`, default opacity 0.30).
    - `god_rays` (`atmospheric`, `all`, `["9:16", "16:9"]`, `assets/overlays/static/god_rays.png`, default opacity 0.25).
  - Register all 8 dynamic vector HUD overlays:
    - `rec_analog_hud` (`vector_hud`, `horror`, `["9:16", "16:9"]`, `assets/svg_overlays/rec_analog_hud.svg`, default opacity 0.90, dynamic params: `rec_time`, `rec_date`, `battery_pct`, `tape_mode`).
    - `cinematic_scope_bars` (`framing`, `all`, `["9:16", "16:9"]`, `assets/svg_overlays/cinematic_scope_bars.svg`, default opacity 1.00, dynamic params: `aspect_ratio_label`).
    - `classified_warning_banner` (`vector_hud`, `horror`, `["9:16", "16:9"]`, `assets/svg_overlays/classified_warning_banner.svg`, default opacity 0.95, dynamic params: `classification_tier`, `warning_message`).
    - `drama_quote_card` (`typography`, `drama`, `["9:16", "16:9"]`, `assets/svg_overlays/drama_quote_card.svg`, default opacity 0.90, dynamic params: `quote_text`, `author_name`, `source_context`).
    - `cyber_data_stream` (`vector_hud`, `scifi`, `["9:16", "16:9"]`, `assets/svg_overlays/cyber_data_stream.svg`, default opacity 0.85, dynamic params: `node_id`, `frequency_ghz`, `encryption_cipher`, `coordinates`).
    - `hud_tactical_telemetry` (`vector_hud`, `scifi`, `["9:16", "16:9"]`, `assets/svg_overlays/hud_tactical_telemetry.svg`, default opacity 0.85, dynamic params: `telemetry_text`, `bpm`).
    - `scp_classification_stamp` (`vector_hud`, `horror`, `["9:16", "16:9"]`, `assets/svg_overlays/scp_classification_stamp.svg`, default opacity 0.90, dynamic params: `item_number`, `classification`).
    - `biometric_wave` (`vector_hud`, `scifi`, `["9:16", "16:9"]`, `assets/svg_overlays/biometric_wave.svg`, default opacity 0.85, dynamic params: `bpm`, `spo2`).
  - Concrete edit target: `assets/graphics_manifest.json` (new file).

- [x] 2.3 **[GREEN]** Implement `GraphicsBank.load_manifest()` in `src/media/graphics_bank.py`:
  - Resolve default manifest path (`BASE_DIR / "assets" / "graphics_manifest.json"`).
  - Parse JSON and validate mandatory root keys (`version`, `assets`).
  - Enforce defensive security validation:
    - Validate asset ID matches `^[a-z0-9_]+$` (TM-01).
    - Validate `relative_path` is relative and resolves strictly within `base_dir` (`path.resolve().is_relative_to(base_dir)`).
  - Validate enumerations against `GraphicCategory` and `GraphicChannelAffinity`.
  - Detect and reject duplicate asset IDs.
  - Store parsed records in immutable `_assets: Dict[str, GraphicAsset]`.
  - Concrete edit target: `src/media/graphics_bank.py`.

- [x] 2.4 **[GREEN]** Implement query, lookup, and resolution helpers in `src/media/graphics_bank.py`:
  - `get_asset(self, asset_id: str) -> Optional[GraphicAsset]`.
  - `query(self, category=None, channel=None, aspect_ratio=None, tag=None) -> List[GraphicAsset]`:
    - Conjunction filtering across all non-None criteria.
    - Channel matching: if `channel` specified, matches assets with `channel_affinity == channel` or `channel_affinity == GraphicChannelAffinity.ALL`.
    - Aspect ratio matching: checks if `aspect_ratio` is contained within `asset.aspect_ratios`.
    - Tag matching: case-insensitive containment check in `asset.tags`.
  - `resolve_atmospheric_path(self, kind: str, particle_type: Optional[str] = None) -> Optional[Path]`:
    - Normalizes kind string (`"particles"`, `"vignette"`, `"dark_vignette"`, `"soft_vignette"`, `"film_grain"`, `"tv_static"`, `"god_rays"`).
    - If `kind == "particles"` and `particle_type` is specified (e.g. `"embers"`, `"dust"`), checks `particles_<type>`.
    - Resolves absolute path via `asset.resolve_path(self.base_dir)`.
    - Verifies file existence on disk before returning path.
  - `clamp_asset_opacity(self, asset_id: str, requested: Optional[float] = None) -> float`:
    - If asset category is `ATMOSPHERIC`, clamps to $[0.15, 0.35]$ (using `clamp_atmospheric_overlay_opacity`).
    - If asset is non-atmospheric, returns requested opacity bounded in $[0.0, 1.0]$ (fallback to `asset.default_opacity`).
  - Implement singleton helper `get_graphics_bank() -> GraphicsBank`.
  - Concrete edit target: `src/media/graphics_bank.py`.

- [x] 2.5 **[GREEN]** Implement `GraphicsBank.validate_bank()` preflight integrity probe in `src/media/graphics_bank.py`:
  - Iterate all registered assets in `self._assets.values()`.
  - Validate physical file exists at `asset.resolve_path(self.base_dir)`.
  - Validate non-zero file size (`st_size > 0`).
  - Validate file size upper bounds: PNG $\le 204,800\text{ bytes}$ ($200\text{ KB}$), SVG $\le 512,000\text{ bytes}$ ($500\text{ KB}$).
  - For PNG assets: open via Pillow, verify mode == `"RGBA"`, dimensions $\ge 1080\times 1920$ or $1920\times 1080$.
  - For SVG assets: scan XML text for disallowed `<!DOCTYPE` or `<!ENTITY` (TM-02), parse with `xml.etree.ElementTree`, and verify root tag is SVG.
  - Return `BankValidationReport(valid=..., total_assets=..., verified_assets=..., missing_assets=..., corrupted_assets=..., oversized_assets=..., errors=...)`.
  - Concrete edit target: `src/media/graphics_bank.py`.

- [x] 2.6 **[VERIFY]** Run `pytest tests/unit/test_graphics_bank.py -v` to confirm GREEN state for graphics bank tests.

---

### Phase 3: High-Impact Graphic Designs & Procedural Generation CLI

- [x] 3.1 **[GREEN]** Implement procedural generator CLI `scripts/generate_graphic_assets.py`:
  - Headless image synthesis using Pillow and NumPy with deterministic random seeds (`seed=42`).
  - Implement generators for all 8 static atmospheric overlays ($1080\times 1920$, RGBA):
    - `generate_dark_vignette()`: High-order radial falloff ($r^2$ to $r^4$) mapping corner alpha $0.75 \to 0.00$ at center.
    - `generate_soft_vignette()`: Feathered gaussian radial falloff mapping corner alpha $0.40 \to 0.00$ at center.
    - `generate_film_grain()`: Gaussian random noise ($\mu=128, \sigma=18$) with subtle monochromatic texture and alpha $0.20 - 0.30$.
    - `generate_tv_static()`: CRT phosphor noise modulated by periodic horizontal scanlines ($y \pmod 3 == 0$).
    - `generate_particles()`: Multi-scale floating dust motes with soft gaussian edge falloff.
    - `generate_particles_dust()`: Low-velocity directional drifting indoor motes.
    - `generate_particles_embers()`: Warm glowing ember specks ($3200\text{K}$, `#FF6600` / `#FFCC33`).
    - `generate_god_rays()`: Diagonal volumetric light shafts projecting from top corner with linear gradient attenuation.
  - Save all images as optimized 8-bit RGBA PNGs (`optimize=True`), asserting file size $< 200\text{ KB}$ each.
  - Synchronize output to `assets/overlays/static/` and mirror in `assets/overlays/`.
  - CLI argument parser: `--force` (overwrite existing), `--verify` (integrity verification mode only), `--resolution WIDTH HEIGHT`.
  - Concrete edit target: `scripts/generate_graphic_assets.py` (new file).

- [x] 3.2 **[GREEN]** Generate all 8 static atmospheric PNG overlays:
  - Run `python3 scripts/generate_graphic_assets.py --force`.
  - Verify all 8 files exist in `assets/overlays/static/` and `assets/overlays/`.
  - Verify each file is $< 200\text{ KB}$ and valid RGBA PNG.
  - Concrete output targets:
    - `assets/overlays/static/dark_vignette.png`
    - `assets/overlays/static/soft_vignette.png`
    - `assets/overlays/static/film_grain.png`
    - `assets/overlays/static/tv_static.png`
    - `assets/overlays/static/particles.png`
    - `assets/overlays/static/particles_dust.png`
    - `assets/overlays/static/particles_embers.png`
    - `assets/overlays/static/god_rays.png`
    - (and mirrors in `assets/overlays/`)

- [x] 3.3 **[GREEN]** Implement 5 new high-impact SVG vector templates in `assets/svg_overlays/`:
  - `rec_analog_hud.svg`:
    - Analog horror VHS camcorder OSD.
    - Elements: Red blinking recording dot `#FF0033` with `● REC`, battery icon with `{{battery_pct}}`, SP/LP tape mode, audio VU meter bars, `{{rec_time}}`, `{{rec_date}}`.
    - Coordinates: Top elements $y = 210\text{px}$ ($\ge 180\text{px}$), bottom elements $y = 1420\text{px}$ ($\le 1460\text{px}$).
  - `cinematic_scope_bars.svg`:
    - Anamorphic 2.39:1 scope matte letterbox bars with precision framing tick marks, optical crosshair reticle, and customizable camera gauge `{{aspect_ratio_label}}`.
    - Preserves central viewing corridor.
  - `classified_warning_banner.svg`:
    - Containment breach / top-secret redacted warning banner.
    - Elements: Diagonal yellow/black hazard chevrons (`#FFCC00`/`#000000`), triangular caution emblem, clearance classification badge `{{classification_tier}}`, redacted blackout bars, and warning text `{{warning_message}}`.
    - Coordinates: Centered in upper safe quadrant ($y \in [200\text{px}, 450\text{px}]$).
  - `drama_quote_card.svg`:
    - Minimalist warm typography card for poignant dialogue, narrative reflections, or quotes.
    - Elements: Frosted glass translucent card backdrop (`rgba(20, 20, 20, 0.75)`), thin golden border (`#D4AF37`), stylized quote mark glyph, dynamic `{{quote_text}}`, `{{author_name}}`, `{{source_context}}`.
    - Coordinates: Centered inside safe window ($x \in [100\text{px}, 980\text{px}]$, $y \in [600\text{px}, 1300\text{px}]$).
  - `cyber_data_stream.svg`:
    - Sci-Fi tactical terminal HUD with telemetry and data streams.
    - Elements: Electric cyan `#00FFCC` / green `#00FF88` accents, hexagonal framing brackets, waveform monitor, dynamic telemetry `{{node_id}}`, `{{frequency_ghz}}`, `{{encryption_cipher}}`, `{{coordinates}}`, system status `ONLINE // ENCRYPTED`.
    - Coordinates: Lateral $x \in [64\text{px}, 950\text{px}]$, vertical $y \in [220\text{px}, 1400\text{px}]$.
  - Concrete edit targets: 5 new SVG files in `assets/svg_overlays/`.

- [x] 3.4 **[REFACTOR]** Modernize existing SVG templates in `assets/svg_overlays/` for safe-zone compliance:
  - `hud_tactical_telemetry.svg`: Shift top indicators from $y = 80\text{px}$ down to $y = 200\text{px}$ ($\ge 180\text{px}$); shift bottom indicators from $y = 1800\text{px}$ up to $y = 1440\text{px}$ ($\le 1460\text{px}$); confine lateral elements within $x \in [64\text{px}, 950\text{px}]$.
  - `scp_classification_stamp.svg`: Shift top hazard chevrons down to $y = 190..330\text{px}$ ($\ge 180\text{px}$); shift bottom clearance bar up to $y = 1420\text{px}$ ($\le 1460\text{px}$).
  - `biometric_wave.svg`: Verify pulse waveform and vitals telemetry remain strictly within $[180\text{px}, 1460\text{px}]$ window.
  - Concrete edit targets: `assets/svg_overlays/hud_tactical_telemetry.svg`, `assets/svg_overlays/scp_classification_stamp.svg`, `assets/svg_overlays/biometric_wave.svg`.

- [x] 3.5 **[VERIFY]** Run `pytest tests/unit/test_graphic_designs.py -v` to confirm GREEN state across all asset design and procedural generator tests.

---

### Phase 4: Engine Integration & Visual Coherence Governance

- [x] 4.1 **[GREEN]** Refactor `SVGOverlayEngine` in `src/media/svg_overlay.py` with bounded LRU raster cache:
  - Replace dict `_raster_cache` with `collections.OrderedDict`.
  - Enforce `maxsize = 128`: upon inserting a 129th entry, evict the least recently used entry via `self._raster_cache.popitem(last=False)` (TM-04).
  - Implement `cache_info() -> SimpleNamespace` returning `hits`, `misses`, `currsize`, `maxsize`.
  - Implement `clear_cache() -> None` resetting cache and metrics.
  - Preserve zero-allocation NumPy buffer blitting: validate `out_buffer` shape `(height, width, 4)` and dtype `uint8`, writing in-place via `np.copyto(out_buffer, raster)`.
  - Concrete edit target: `src/media/svg_overlay.py`.

- [x] 4.2 **[GREEN]** Implement graceful rasterization fallback and parameter cleanup in `src/media/svg_overlay.py`:
  - When `resvg_py` is unavailable or raises an exception during `svg_to_bytes`, catch the error, log a structured warning (`logger.warning("resvg-py unavailable; falling back to Pillow rasterization")`), and render the SVG via Pillow fallback.
  - Enhance `interpolate_template()`:
    - Substitute both double-brace `{{param}}` and single-brace `{param}` tokens.
    - If dynamic parameters are omitted or missing, retain embedded default fallback strings or clean defaults without corrupting XML syntax.
  - Concrete edit target: `src/media/svg_overlay.py`.

- [x] 4.3 **[GREEN]** Integrate `src/media/overlays.py` with `GraphicsBank` and purge obsolete paths:
  - In `resolve_hybrid_overlay_asset()`, delegate resolution first to `get_graphics_bank().resolve_atmospheric_path(kind, particle_type)`.
  - If a valid path is returned from `GraphicsBank`, return it immediately.
  - Purge dead references to `assets/visual_bank` in `_hybrid_overlay_search_roots()` (the directory was purged and is forbidden by tests).
  - Update `_hybrid_overlay_search_roots()` to scan `assets/overlays/static` and `assets/overlays/motion` instead of dead paths.
  - Retain `clamp_atmospheric_overlay_opacity()` enforcing the $[0.15, 0.35]$ band with default $0.25$, returning $0.0$ when $0.0$ is requested.
  - Concrete edit target: `src/media/overlays.py`.

- [x] 4.3b **[REFACTOR]** Purge dead references to `assets/visual_bank` across media and thumbnails subsystems:
  - In `src/media/assets.py`: remove obsolete `assets/visual_bank` search roots (`visual_bank_dir / f / "scenery"` etc.), consolidating scene asset resolution to canonical template/loop locations.
  - In `src/media/thumbnails/asset_resolver.py`: clean up obsolete references to `assets/visual_bank` while preserving `assets/thumbnails/templates/`.
  - In `src/media/loop/rotation.py`: remove dead fallback checking `assets/visual_bank/<channel>/scenery`.
  - In `src/asset_manager.py`: eliminate dead `visual_bank/` directory scan loop.
  - Concrete edit targets: `src/media/assets.py`, `src/media/thumbnails/asset_resolver.py`, `src/media/loop/rotation.py`, `src/asset_manager.py`.

- [x] 4.3c **[REFACTOR]** Modernize legacy channel defaults across media interfaces:
  - Replace default parameters `channel: str = "moku"` with `channel: str = "horror"` in `src/media/visual_coherence.py`, `src/media/manifest_compiler.py`, and `src/media/thumbnail_engine.py`.
  - Retain `"moku"` and `"aelithia"` as transparent backward-compatibility aliases mapping to `"horror"` and `"drama"`.
  - Concrete edit targets: `src/media/visual_coherence.py`, `src/media/manifest_compiler.py`, `src/media/thumbnail_engine.py`.

- [x] 4.4 **[GREEN]** Integrate `src/media/visual_coherence.py` safe-zone and opacity helpers:
  - Import and re-export `clamp_atmospheric_overlay_opacity` from `src/media/overlays.py`.
  - Implement `validate_graphic_safe_zone(bbox: Dict[str, int], width: int, height: int) -> bool` coordinating with `enforce_shorts_safe_zone(width, height)`.
  - Confirm `build_coherent_color_grade()` supports channel visual identities (`horror`, `drama`, `scifi`).
  - Concrete edit target: `src/media/visual_coherence.py`.

- [x] 4.5 **[REFACTOR]** Export new subsystem symbols in `src/media/__init__.py`:
  - Export `GraphicsBank`, `GraphicAsset`, `GraphicCategory`, `GraphicChannelAffinity`, `BankValidationReport`, `get_graphics_bank`, `clamp_atmospheric_overlay_opacity`, `enforce_shorts_safe_zone`, `validate_visual_continuity`.
  - Concrete edit target: `src/media/__init__.py`.

- [x] 4.6 **[VERIFY]** Run `pytest tests/unit/test_svg_overlay.py tests/unit/test_visual_coherence.py -v` to confirm GREEN state across both engine test suites.

---

### Phase 5: Verification, Benchmarking & Governance Validation

- [x] 5.1 **[VERIFY]** Execute end-to-end asset verification via procedural CLI:
  - Run `python3 scripts/generate_graphic_assets.py --verify`.
  - Assert 100% of static PNGs and SVG templates are verified with 0 errors.

- [x] 5.2 **[VERIFY]** Execute anti-regression guardrail suite:
  - Run `.venv/bin/pytest tests/unit/test_anti_regression_guardrails.py -v`.
  - Confirm strict compliance with:
    - `REG-01`: Zero Playwright/Chromium imports in `src/media/`.
    - `REG-02`: Zero legacy web renderers or templates.
    - `REG-04`: Single-pass atomic FFmpeg encoding without intermediate disk chunks.
    - `REG-08`: Contiguous NumPy buffers without accumulating frame arrays in Python RAM.
    - `REG-14`: Subprocess thread bounding (`-threads 2`).

- [x] 5.3 **[VERIFY]** Execute full unit test suite:
  - Run `.venv/bin/pytest tests/unit/test_graphics_bank.py tests/unit/test_graphic_designs.py tests/unit/test_svg_overlay.py tests/unit/test_visual_coherence.py -v`.
  - Assert 100% pass across all graphics bank, designs, engine, and coherence tests.

- [x] 5.4 **[VERIFY]** Performance & Resource Target Benchmark (AGENTS.md Section 5):
  - Verify `GraphicsBank` manifest load time $< 10\text{ ms}$ and memory $< 2.0\text{ MiB}$ heap.
  - Verify `SVGOverlayEngine` LRU cache steady-state memory $< 180\text{ MiB}$ and peak memory under 128 entries $\le 1.06\text{ GiB}$ (well within $\le 2.0\text{ GiB}$ system limit).
  - Verify CPU utilization stays bounded within $\le 2.0\text{ Cores}$.

- [x] 5.5 **[VERIFY]** Repository-wide integrity gate check:
  - Execute `./scripts/verify_integrity.sh`.
  - Assert exit code 0 with zero guardrail violations, zero uncommitted secrets, and zero bloat files.
