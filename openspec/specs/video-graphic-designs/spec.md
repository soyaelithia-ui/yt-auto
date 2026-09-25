# Standardized High-Impact Video Graphic Designs Specification

## Purpose
Defines the graphic designs subsystem providing standardized, production-grade static atmospheric overlay textures and high-fidelity SVG vector HUD templates aligned with Horror, Drama, and Sci-Fi channel genres, backed by an offline procedural asset generation toolchain.

## Requirements

### Requirement: Static Atmospheric Overlay Suite (`static_atmospheric_overlay_suite`)
The system MUST provide 8 production-grade static atmospheric overlay assets in `assets/overlays/static/` (and mirrored in `assets/overlays/` for legacy compatibility) to supply visual depth and textural atmosphere without requiring CPU-intensive video decoding during composition.

The 8 required static assets SHALL be:
1. `dark_vignette.png`: Deep radial shadow falloff focusing audience attention toward center-frame for horror and psychological suspense. Corner alpha $0.75 \to 0.00$ at frame center.
2. `soft_vignette.png`: Gentle, feathered radial vignette for cinematic drama and character-driven narratives. Corner alpha $0.40 \to 0.00$ at frame center.
3. `film_grain.png`: Fine 35mm optical grain texture breaking digital color banding and unifying heterogeneous assets.
4. `tv_static.png`: Analog cathode-ray phosphor noise and scanline texture for analog horror, surveillance feeds, and glitch transitions.
5. `particles.png`: Neutral ambient floating micro-dust particles with soft alpha falloff.
6. `particles_dust.png`: Low-velocity directional drift motes for atmospheric liminal, archive, and indoor scenes.
7. `particles_embers.png`: High-contrast glowing warm ember sparks ($3200\text{K}$) for climactic catastrophe, fire, and conflict scenes.
8. `god_rays.png`: Soft volumetric light beam shafts projecting diagonally from high angles with linear gradient attenuation.

Each asset MUST satisfy the following physical constraints:
- Stored as an 8-bit per channel `RGBA` PNG with a functional alpha transparency channel.
- Native resolution of at least $1080\times 1920$ pixels (compatible with both 9:16 vertical crop and 16:9 horizontal scaling).
- File size strictly bounded below $200\text{ KB}$ (204,800 bytes) per asset to maintain repository compactness and near-instantaneous I/O reads.
- 100% offline generation with zero external network or third-party web service downloads.

#### Scenario: Verification of all 8 static atmospheric overlays (Happy Path)
- **Given** the media pipeline initializes for production rendering
- **When** the filesystem is inspected at `assets/overlays/static/`
- **Then** all 8 files (`dark_vignette.png`, `soft_vignette.png`, `film_grain.png`, `tv_static.png`, `particles.png`, `particles_dust.png`, `particles_embers.png`, `god_rays.png`) MUST exist
- **And** each file MUST be an uncorrupted PNG decodable by Pillow.

#### Scenario: RGBA alpha channel transparency validation (Happy Path)
- **Given** static overlay asset `assets/overlays/static/dark_vignette.png`
- **When** the image is loaded into memory
- **Then** the image mode MUST be `"RGBA"`
- **And** the alpha channel MUST exhibit variable transparency across pixels (min alpha < 0.10, max alpha > 0.60)
- **And** center pixels MUST have alpha near 0.00 to prevent obscuring central subjects.

#### Scenario: File size upper bound constraint enforcement (Guardrail)
- **Given** any generated or refreshed static atmospheric overlay asset
- **When** the file's disk size is probed
- **Then** the file size MUST be strictly less than $200\text{ KB}$
- **And** the combined disk footprint of all 8 static overlays MUST be less than $1.5\text{ MB}$.

---

### Requirement: Dynamic SVG Vector HUD Suite (`dynamic_svg_vector_hud_suite`)
The system MUST provide a standardized suite of 5 high-impact, channel-aligned SVG vector templates in `assets/svg_overlays/`, complementing existing tactical and biometric overlays, while enforcing YouTube Shorts mobile UI safe-zone margins.

The 5 SVG templates SHALL adhere to the following specifications:
1. `rec_analog_hud.svg` (Analog Horror / Found Footage):
   - Visual elements: Vintage camcorder on-screen display, blinking recording indicator (`#FF0033` red dot and `● REC`), battery icon with segmented charge and `{{battery_pct}}` readout, tape mode (`SP` / `LP`), audio VU bar indicator, monospace timestamp (`{{rec_time}}`), and date (`{{rec_date}}`).
   - Placement: Top indicators placed at $y = 210\text{px}$ (strictly below $MarginV_{top} \ge 180\text{px}$); bottom readouts placed at $y = 1420\text{px}$ (strictly above $MarginV_{bottom} \ge 460\text{px}$ threshold of $1460\text{px}$).
2. `cinematic_scope_bars.svg` (Anamorphic Cinema Framing):
   - Visual elements: Ultra-wide 2.39:1 scope letterbox matte bars, thin precision tick marks, optical center crosshair reticle, and customizable camera gauge indicators (`{{aspect_ratio_label}}` / `2.39:1 SCOPE`).
   - Placement: Preserves central safe viewing corridor, ensuring subtitle readability within safe zones.
3. `classified_warning_banner.svg` (SCP / Containment Warning):
   - Visual elements: Industrial containment warning banner, yellow/black diagonal hazard stripe borders (`#FFCC00`/`#000000`), caution triangular emblem, clearance classification badge (`{{classification_tier}}`), redacted blackout bars, and dynamic warning text (`{{warning_message}}`).
   - Placement: Centered in upper safe quadrant ($y = 200\text{px}$ to $450\text{px}$), strictly above mobile center and clear of seekbars.
4. `drama_quote_card.svg` (Minimalist Drama & Dialogue):
   - Visual elements: Warm editorial typography card, frosted glass translucent backdrop (`rgba(20, 20, 20, 0.75)`), thin golden border (`#D4AF37`), quotation mark icon, dynamic quote body (`{{quote_text}}`), author attribution (`{{author_name}}`), and citation context (`{{source_context}}`).
   - Placement: Centered in safe window ($x = 100\text{px}$ to $980\text{px}$, $y = 600\text{px}$ to $1300\text{px}$).
5. `cyber_data_stream.svg` (Sci-Fi Tactical Terminal):
   - Visual elements: High-tech cyber telemetry HUD, neon cyan/green accents (`#00FFCC` / `#00FF88`), telemetry data readouts (`{{node_id}}`, `{{frequency_ghz}}`, `{{encryption_cipher}}`, `{{coordinates}}`), frequency waveform, and status badge (`ONLINE // ENCRYPTED`).
   - Placement: Lateral readouts kept inside $x \ge 64\text{px}$ and $x \le 950\text{px}$, vertical elements between $y = 220\text{px}$ and $1400\text{px}$.

All SVG templates MUST support token parameter interpolation using both double-brace `{{param}}` and single-brace `{param}` syntax. When dynamic parameters are omitted, templates MUST gracefully display sensible fallback defaults embedded directly within the SVG XML.

#### Scenario: Analog horror REC HUD template dynamic parameter interpolation (Happy Path)
- **Given** template `rec_analog_hud.svg`
- **And** parameters `{"rec_time": "00:14:28:09", "rec_date": "OCT. 24 1994", "battery_pct": "78%"}`
- **When** `SVGOverlayEngine.interpolate_template()` processes the template
- **Then** the resulting SVG MUST contain `"00:14:28:09"`, `"OCT. 24 1994"`, and `"78%"`
- **And** MUST NOT contain unreplaced `{{rec_time}}`, `{{rec_date}}`, or `{{battery_pct}}` tokens.

#### Scenario: Drama quote card text substitution and visual framing (Happy Path)
- **Given** template `drama_quote_card.svg`
- **And** parameters `{"quote_text": "We were together. I forget the rest.", "author_name": "Walt Whitman", "source_context": "Leaves of Grass"}`
- **When** `SVGOverlayEngine.interpolate_template()` processes the template
- **Then** the quote text, author, and source context MUST be substituted into the typography elements
- **And** the layout MUST remain centered within safe margins.

#### Scenario: Sci-Fi cyber data stream parameter substitution (Happy Path)
- **Given** template `cyber_data_stream.svg`
- **And** parameters `{"node_id": "ORBITAL-7", "frequency_ghz": "142.084", "encryption_cipher": "AES-GCM-256", "coordinates": "34.0522 N, 118.2437 W"}`
- **When** `SVGOverlayEngine.interpolate_template()` executes
- **Then** all 4 telemetry parameters MUST be rendered into the corresponding HUD data fields.

#### Scenario: Missing parameter fallback to template defaults (Edge Case)
- **Given** template `classified_warning_banner.svg` containing dynamic token `{{classification_tier}}`
- **When** parameter interpolation is invoked with an empty dictionary `{}`
- **Then** the template MUST retain default fallback text (e.g. `"LEVEL 4 // TOP SECRET"`) or clean empty string
- **And** MUST NOT raise a `KeyError` or emit corrupted XML syntax.

#### Scenario: XML well-formedness and schema validation across all presets (Happy Path)
- **Given** all 5 new SVG templates in `assets/svg_overlays/`
- **When** parsed using Python standard library `xml.etree.ElementTree`
- **Then** every template MUST parse successfully without `ParseError`
- **And** the root element tag MUST be `{http://www.w3.org/2000/svg}svg` or `svg`.

---

### Requirement: Procedural Asset Generation CLI (`procedural_asset_generation_cli`)
The system MUST provide an autonomous, headless CLI script at `scripts/generate_graphic_assets.py` to deterministically create or regenerate all 8 static atmospheric overlay PNGs and verify vector HUD templates without external network calls or web services.

The procedural generation script MUST:
1. Use standard mathematical synthesis (NumPy noise arrays, Pillow radial gradients, gaussian blurs, particle motes, scanlines).
2. Use fixed random seeds to ensure 100% deterministic, reproducible output files.
3. Save generated assets to `assets/overlays/static/` and synchronize them with `assets/overlays/`.
4. Ensure all generated PNG files are optimized 8-bit RGBA files strictly $< 200\text{ KB}$ each.
5. Provide a `--force` command-line flag to overwrite existing assets; without `--force`, existing valid assets SHALL NOT be unnecessarily regenerated.
6. Provide a `--verify` flag to validate that all required assets exist, are valid RGBA images, and adhere to size limits.
7. Return exit code 0 on success and non-zero on error.

#### Scenario: Procedural generation of all 8 static atmospheric overlays (Happy Path)
- **Given** an empty or missing `assets/overlays/static/` directory
- **When** `python3 scripts/generate_graphic_assets.py --force` is executed
- **Then** all 8 atmospheric PNG assets MUST be created on disk
- **And** every asset MUST be a valid RGBA PNG of resolution $1080\times 1920$
- **And** every file size MUST be $< 200\text{ KB}$
- **And** the command MUST exit with code 0.

#### Scenario: Idempotent execution skips regeneration when assets exist (Happy Path)
- **Given** all 8 atmospheric PNG assets already exist and are valid
- **When** `python3 scripts/generate_graphic_assets.py` is executed without `--force`
- **Then** the script MUST verify existing files without rewriting them
- **And** execution MUST complete in $< 1.0\text{ second}$ with exit code 0.

#### Scenario: Headless offline execution without network or display server (Happy Path)
- **Given** an environment without an X11/Wayland display server (`DISPLAY` unset) and without internet connectivity
- **When** `scripts/generate_graphic_assets.py` is invoked
- **Then** generation MUST succeed using headless Pillow/NumPy rendering
- **And** no socket connections or browser processes SHALL be initiated.
