# Local Video Graphics Bank Specification

## Purpose
Defines the local video graphics bank subsystem governing declarative asset cataloging, typed schema validation, multi-parameter querying and discovery, file integrity probing, and lifecycle management for static atmospheric textures and dynamic vector HUD templates across YouTube production lanes.

## Requirements

### Requirement: Graphics Manifest Schema and Validation (`graphics_manifest_schema_and_validation`)
The system MUST maintain a single source of truth (SSOT) JSON catalog at `assets/graphics_manifest.json` registering all static atmospheric overlays, vector HUD designs, and framing assets. The manifest MUST conform to a strongly-typed schema represented by `GraphicAsset` and `GraphicsManifest` models in `src/media/graphics_bank.py`.

The manifest schema SHALL enforce the following structure:
1. `version`: Semantic version string (e.g. `"1.0.0"`).
2. `assets`: Non-empty array of asset objects, each requiring:
   - `id`: Unique lowercase alphanumeric string identifier with underscores (e.g. `"rec_analog_hud"`, `"dark_vignette"`).
   - `name`: Human-readable title describing the graphic element.
   - `category`: String enumeration adhering strictly to `GraphicCategory`: `"atmospheric"`, `"vector_hud"`, `"framing"`, or `"typography"`.
   - `channel_affinity`: String enumeration adhering strictly to `GraphicChannelAffinity`: `"horror"`, `"drama"`, `"scifi"`, or `"all"`.
   - `aspect_ratios`: Non-empty list of supported aspect ratios (`["9:16"]`, `["16:9"]`, or `["9:16", "16:9"]`).
   - `relative_path`: Posix file path relative to repository workspace root (`assets/overlays/static/...` or `assets/svg_overlays/...`).
   - `safe_zone_compliant`: Boolean flag indicating whether interactive/textual components strictly reside within mobile UI safe boundaries.
   - `default_opacity`: Floating-point value bounded in $[0.0, 1.0]$. For assets under category `"atmospheric"`, default opacity MUST be clamped within $[0.15, 0.35]$.
   - `dynamic_params`: Dictionary of string key-value pairs representing template substitution variables and fallback defaults (empty dict `{}` for static assets).
   - `tags`: List of lowercase keyword strings for multi-facet discovery.

If the manifest JSON is malformed, missing required keys, or contains duplicate asset IDs, `GraphicsBank.load_manifest()` MUST raise a descriptive `ValueError` detailing the schema error.

#### Scenario: Valid manifest loading and model instantiation (Happy Path)
- **Given** a valid `assets/graphics_manifest.json` file conforming to the schema
- **When** `GraphicsBank.load_manifest()` is executed
- **Then** the bank MUST parse all asset entries into immutable `GraphicAsset` instances
- **And** all parsed assets MUST be accessible via `bank.get_asset(asset_id)`
- **And** memory consumption for the parsed catalog MUST NOT exceed 2.0 MiB heap memory.

#### Scenario: Missing required field rejection in manifest entry (Edge Case)
- **Given** a manifest entry lacking the mandatory `"category"` or `"relative_path"` field
- **When** `GraphicsBank.load_manifest()` attempts to parse the file
- **Then** the system MUST raise a `ValueError` identifying the invalid asset entry and missing key
- **And** the bank MUST NOT enter a partially-loaded or inconsistent state.

#### Scenario: Duplicate asset ID detection and rejection (Edge Case)
- **Given** a manifest containing two distinct asset entries sharing identical `"id": "dark_vignette"`
- **When** `GraphicsBank.load_manifest()` validates the asset collection
- **Then** the system MUST raise a `ValueError` indicating a duplicate asset identifier collision
- **And** abort manifest ingestion.

#### Scenario: Invalid category or channel affinity enumeration (Edge Case)
- **Given** an asset entry with `"category": "unsupported_3d_mesh"` or `"channel_affinity": "vlog"`
- **When** `GraphicsBank.load_manifest()` parses the entry
- **Then** the system MUST raise a `ValueError` reporting the unsupported enumeration value
- **And** provide the list of permissible enum values.

---

### Requirement: Graphics Bank Query and Filtering (`graphics_bank_query_and_filtering`)
The system MUST provide a high-level query and filtering interface via `GraphicsBank.query()` in `src/media/graphics_bank.py` to allow automated scene planning stages, visual coherence directors, and compositor engines to discover graphic assets dynamically.

The query API MUST support conjunction (AND) filtering across the following optional parameters:
1. `category`: Filters by exact `GraphicCategory` (e.g. `GraphicCategory.ATMOSPHERIC` or string `"atmospheric"`).
2. `channel`: Filters by channel niche string (`"horror"`, `"drama"`, `"scifi"`). Assets configured with `channel_affinity == "all"` MUST match any requested channel niche.
3. `aspect_ratio`: Filters assets whose `aspect_ratios` list contains the requested ratio (`"9:16"` or `"16:9"`).
4. `tag`: Filters assets whose `tags` list contains the specified tag string (case-insensitive).

The bank MUST additionally provide helper methods:
- `get_asset(asset_id: str) -> Optional[GraphicAsset]`: Returns the single matching asset or `None`.
- `resolve_atmospheric_path(kind: str, particle_type: Optional[str] = None) -> Optional[Path]`: Resolves a physical filesystem path for legacy and hybrid overlay requests (`"vignette"`, `"film_grain"`, `"tv_static"`, `"particles"`, `"god_rays"`).
- `clamp_asset_opacity(asset_id: str, requested: Optional[float] = None) -> float`: Resolves effective overlay opacity, enforcing atmospheric bounds $[0.15, 0.35]$.

#### Scenario: Querying assets by channel affinity and category (Happy Path)
- **Given** a populated graphics bank containing atmospheric assets and vector HUDs across channels
- **When** `bank.query(category="vector_hud", channel="horror")` is invoked
- **Then** the returned list MUST contain `rec_analog_hud` and `classified_warning_banner`
- **And** MUST NOT contain drama-specific quote cards or scifi data streams
- **And** MUST include any vector HUD asset with `channel_affinity == "all"`.

#### Scenario: Channel wildcard matching for universal assets (Happy Path)
- **Given** asset `dark_vignette` registered with `channel_affinity == "all"`
- **When** `bank.query(category="atmospheric", channel="scifi")` is invoked
- **Then** `dark_vignette` MUST be included in the returned assets alongside scifi-specific overlays.

#### Scenario: Query by aspect ratio constraint (Happy Path)
- **Given** assets registered for `"9:16"` only, `"16:9"` only, and dual `["9:16", "16:9"]`
- **When** `bank.query(aspect_ratio="9:16")` is invoked
- **Then** the result MUST only include assets that support `"9:16"`
- **And** MUST exclude assets restricted exclusively to horizontal formats.

#### Scenario: Query returning empty list when no assets match criteria (Edge Case)
- **Given** a query specifying `category="framing"`, `channel="drama"`, and `tag="cyber"`
- **When** no registered asset satisfies all three criteria simultaneously
- **Then** `bank.query()` MUST return an empty list `[]` without raising an exception.

#### Scenario: Single asset lookup by exact identifier (Happy Path)
- **Given** registered asset ID `"cinematic_scope_bars"`
- **When** `bank.get_asset("cinematic_scope_bars")` is invoked
- **Then** it MUST return the matching `GraphicAsset` instance with its relative path and parameters.

#### Scenario: Single asset lookup with unknown identifier (Edge Case)
- **Given** a non-existent asset ID `"missing_hologram_hud"`
- **When** `bank.get_asset("missing_hologram_hud")` is invoked
- **Then** it MUST return `None` without raising a `KeyError`.

#### Scenario: Atmospheric overlay path resolution for hybrid compositing (Happy Path)
- **Given** an overlay request with `kind="particles"` and `particle_type="embers"`
- **When** `bank.resolve_atmospheric_path(kind="particles", particle_type="embers")` is invoked
- **Then** it MUST resolve the absolute path to `assets/overlays/static/particles_embers.png`
- **And** verify that the file exists on disk.

---

### Requirement: Asset Integrity and Existence Probe (`asset_integrity_and_existence_probe`)
The system MUST provide a preflight integrity probe via `GraphicsBank.validate_bank()` to verify the physical existence, file format validity, and dimension correctness of all manifest-registered assets before rendering pipelines execute.

The probe MUST perform the following validations for every registered asset:
1. **Physical Existence**: The target file MUST exist at `base_dir / asset.relative_path`.
2. **Non-Zero Byte Length**: The file size MUST be strictly greater than 0 bytes (`st_size > 0`).
3. **Storage Budget Limit**: Static PNG textures MUST NOT exceed $200\text{ KB}$ (204,800 bytes). SVG vector files MUST NOT exceed $500\text{ KB}$ (512,000 bytes).
4. **Image Decodability & Color Format**:
   - Static atmospheric assets (`.png`) MUST be decodable as valid PNG images with `RGBA` color mode containing an active alpha channel.
   - Minimum pixel dimensions MUST be at least $1080\times 1920$ (vertical) or $1920\times 1080$ (horizontal).
5. **Vector Syntax Correctness**:
   - Vector overlays (`.svg`) MUST parse as well-formed XML with root element `<svg>`.
   - The root element MUST declare valid `viewBox`, `width`, or `height` attributes.

The method MUST return a strongly-typed `BankValidationReport` dataclass:
```python
@dataclass(frozen=True)
class BankValidationReport:
    valid: bool
    total_assets: int
    verified_assets: int
    missing_assets: List[str]
    corrupted_assets: List[str]
    oversized_assets: List[str]
    errors: List[str]
```
The probe MUST execute in $< 500\text{ ms}$ for the entire bank and MUST NOT crash if individual files are corrupt or missing.

#### Scenario: Full bank integrity probe passes when all assets are intact (Happy Path)
- **Given** all 8 static atmospheric PNGs and 8 SVG overlays exist on disk with valid headers and $< 200\text{ KB}$ file sizes
- **When** `bank.validate_bank()` is executed
- **Then** the report MUST have `valid == True`
- **And** `missing_assets` MUST be empty
- **And** `corrupted_assets` MUST be empty
- **And** `errors` MUST be empty.

#### Scenario: Probe detects missing asset file on disk (Edge Case)
- **Given** a manifest entry referencing `assets/overlays/static/missing_asset.png`
- **And** the file does not exist on disk
- **When** `bank.validate_bank()` is executed
- **Then** the report MUST have `valid == False`
- **And** `missing_assets` MUST contain `"missing_asset"`
- **And** `errors` MUST record a descriptive message identifying the missing path.

#### Scenario: Probe detects zero-byte or corrupt PNG asset (Edge Case)
- **Given** an asset file `assets/overlays/static/tv_static.png` that has been truncated to 0 bytes
- **When** `bank.validate_bank()` is executed
- **Then** the report MUST have `valid == False`
- **And** `corrupted_assets` MUST contain `"tv_static"`
- **And** `errors` MUST record the decode or empty file error.

#### Scenario: Probe detects asset exceeding maximum file size threshold (Edge Case)
- **Given** an uncompressed atmospheric PNG asset of size $850\text{ KB}$ ($> 200\text{ KB}$)
- **When** `bank.validate_bank()` is executed
- **Then** the report MUST record the asset in `oversized_assets`
- **And** `valid` MUST be set to `False` to prevent repository bloat.

---

### Requirement: Canonical Path Resolution and Legacy Fallback Purge (`canonical_path_resolution_and_legacy_purge`)
The system MUST resolve atmospheric overlays and graphic elements exclusively from verified, canonical repository directories:
- `assets/overlays/static/` for static atmospheric PNG textures.
- `assets/svg_overlays/` for declarative SVG HUD and vector elements.
- `assets/loops/` for video loops.
- `assets/thumbnails/templates/` for CTR master backdrops.

The system MUST NOT attempt to scan or fall back to purged legacy directories, specifically `assets/visual_bank/`. The overlay resolution engine in `src/media/overlays.py` and asset resolver in `src/media/assets.py` MUST eradicate references to `assets/visual_bank/`.

Legacy channel identifiers (`"moku"`, `"aelithia"`, `"moku_terror"`, `"aita_drama"`) MUST be normalized to canonical channel genres (`"horror"`, `"drama"`, `"scifi"`), and media entry points MUST use canonical channel defaults (`"horror"`) rather than obsolete names.

#### Scenario: Overlay resolution scans canonical static folder (Happy Path)
- **Given** an overlay request for `"dark_vignette"`
- **When** `resolve_hybrid_overlay_asset("vignette")` is invoked
- **Then** the resolved path MUST point to `assets/overlays/static/dark_vignette.png` or `assets/overlays/dark_vignette.png`
- **And** the resolver MUST NOT attempt to access any path under `assets/visual_bank/`.

#### Scenario: Legacy channel normalization (Happy Path)
- **Given** a query or function call specifying legacy channel `"moku"` or `"aelithia"`
- **When** channel affinity or visual coherence grading is evaluated
- **Then** `"moku"` MUST be normalized to `"horror"`
- **And** `"aelithia"` MUST be normalized to `"drama"`
- **And** the operation MUST proceed without error.
