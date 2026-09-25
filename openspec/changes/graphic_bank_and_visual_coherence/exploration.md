# Exploration: Local Bank of Video Graphic Elements, Visual Coherence, and Dynamic Designs

## Context & Objectives
- Target change: `graphic_bank_and_visual_coherence`
- Standardize and enrich the local graphic element bank (`assets/videos`, `assets/loops`, `assets/svg_overlays`, `assets/overlays`).
- Ensure channel visual coherence and distinction between Horror/SCP (`horror-horror-long`, `horror-scp-short`) and Drama/AITA (`drama-aita-long`, `drama-aita-short`).
- Enforce strict project invariants (AGENTS.md Section 5): <= 2 CPU Cores, <= 2.0 GiB RAM, stream-copy video composition priority, zero-browser.

---

## 1. Current State Assessment

### 1.1 Video Loops & Storage Disconnect
- Physical video loops reside in `assets/videos/longs/` (6 clips, 1920x1080 @ 30fps, SAR 1:1, H.264 Main/High, 30s) and `assets/videos/shorts/` (2 clips, 1080x1920 @ 30fps, 15s).
- `assets/loops/bank_manifest.json` points to legacy filenames in `assets/loops/` (`moku_containment_facility_master_60s.mp4`, etc.) which do not physically exist on disk (only `.gitkeep` files exist).
- SQLite catalog `data/loop_catalog.db` (`LoopCatalogRepository`) currently contains 0 records because `sync_catalog_from_assets` strictly scans `assets/loops/`.
- In production, `LoopRotationManager` falls back to scanning `assets/videos/` directly using round-robin and tension token scoring (`horror`, `containment`, `facility`, `drama`, `courtroom`).

### 1.2 SVG & Vector Overlays
- `assets/svg_overlays/` contains only 3 vertical (1080x1920) templates:
  - `hud_tactical_telemetry.svg`
  - `biometric_wave.svg`
  - `scp_classification_stamp.svg`
- Zero horizontal (1920x1080) SVGs exist.
- Zero SVGs exist for the Drama / Aelithia channel.
- `SVGOverlayEngine` (`src/media/svg_overlay.py`) depends on `resvg_py`, which is an optional C-extension not installed in the environment.
- System FFmpeg is compiled with `--enable-librsvg`, allowing direct SVG rasterization in the filtergraph without Python memory overhead.
- `ImageAnimationRenderer` (`src/media/image_animation.py`) accepts `svg_overlay` parameters in scene items but never wires them into the FFmpeg filter complex.

### 1.3 Raster & Atmospheric Overlays
- `assets/overlays/` contains only `.gitkeep`.
- Calls to `resolve_hybrid_overlay_asset()` (`src/media/overlays.py`) for `particles.png`, `god_rays.png`, `film_grain.png`, `vignette.png`, `tv_static.png` return `None` and fail closed.

### 1.4 Visual Coherence & Safe-Zone Rules
- `src/media/visual_coherence.py` establishes single-source-of-truth rules:
  - Color grading: horror cold-cyan vs drama warm-amber vs scifi blue lift.
  - Safe-zone enforcement: vertical mobile UI margins (top 180px, bottom 460px, right 130px).
  - Scene transition harmonization.
- `src/media/multi_act_renderer.py` draws HUD geometry (`top_bar`, `card`, `bottom_bar`) via FFmpeg `drawtext`/`drawbox` filters using channel accent palettes.
- `SceneAssetTracker` (`src/visuals/scene_asset_tracker.py`) logs asset lineage and dhashes for visual deduplication.

---

## 2. Affected Code & Asset Areas
- `assets/loops/bank_manifest.json` — Reconcile manifest with actual files in `assets/videos/` and new graphic assets.
- `assets/svg_overlays/` — Add horizontal (1920x1080) and vertical (1080x1920) templates for Horror/SCP and Drama/AITA.
- `assets/overlays/` — Supply base atmospheric textures (`film_grain.png`, `vignette_dark.png`, `vignette_warm.png`, `particles_dust.png`, `particles_embers.png`).
- `src/media/svg_overlay.py` — Add fallback to FFmpeg `--enable-librsvg` rasterization when `resvg_py` is not present; support parameter interpolation directly to temporary/piped SVG.
- `src/media/overlays.py` — Expand asset search roots and channel-aware overlay selection.
- `src/media/multi_act_renderer.py` — Wire SVG overlays and act-divider cards into the multi-act FFmpeg filter complex alongside `drawtext`/`drawbox`.
- `src/media/image_animation.py` — Connect scene SVG overlay parameters to the filtergraph.
- `src/media/loop/rotation.py` & `src/core/catalog_sync.py` — Unify physical loop search directories (`assets/videos` and `assets/loops`) so the SQLite catalog is properly synchronized.
- `src/media/visual_coherence.py` — Add geometry and brand coherence validators for new graphical assets.

---

## 3. Evaluated Approaches

### Approach 1: Unified Channel Graphic Bank with FFmpeg Native librsvg Pipeline (Selected)
- Reconcile `assets/videos/` and `assets/loops/` into a single canonical hierarchy and sync them into `LoopCatalogRepository`.
- Populate missing base raster overlays in `assets/overlays/static/` with transparent PNGs: `vignette_dark.png`, `vignette_warm.png`, `film_grain.png`, `particles_embers.png`, `particles_dust.png`.
- Expand SVG catalog with horizontal (1920x1080) and Drama-specific designs (`reddit_confession_card.svg`, `aita_verdict_stamp.svg`, `sentiment_meter.svg`, `horror_act_divider.svg`, `containment_grid.svg`).
- Use FFmpeg's built-in `--enable-librsvg` engine to directly overlay interpolated SVGs onto video scenes in `multi_act_renderer.py` and `image_animation.py`.
- Provide an automated CLI audit tool (`scripts/audit_graphic_bank.py`) to verify SAR 1:1, resolutions (1080x1920 / 1920x1080), alpha transparency, and safe-zone clearance.
- **Pros**: Zero external binary dependencies; minimal CPU and RAM usage (< 50MB RSS); preserves fast stream-copy video composition; provides rich dynamic graphics for both Horror and Drama.
- **Cons**: Requires standardizing path lookup aliases between `assets/videos/` and `assets/loops/`.
- **Effort**: Medium.

### Approach 2: Heavy In-Memory Buffer Rasterization with resvg-py & NumPy Pipeline
- Enforce `resvg-py` binary installation in the virtual environment.
- Rasterize every SVG and stamp in Python into 32-bit RGBA NumPy frame arrays and pipe uncompressed rawvideo streams into FFmpeg.
- **Pros**: Pixel-level programmatic manipulation in Python.
- **Cons**: Extreme RAM consumption (~8.3 MB per 1080p frame; a 1-second 30fps buffer is ~250MB, risking the <= 2.0 GiB ceiling under concurrent workers); heavy CPU penalty over IPC pipes; breaks stream-copy video path.
- **Effort**: High.

### Approach 3: Static Pre-Baked PNG Stacks (Pure Pre-Composited Layering)
- Pre-render all SVG variants at design time into hundreds of static transparent PNG images.
- Discard dynamic SVG parameter interpolation (`{{item_number}}`, `{{bpm}}`, `{{verdict}}`).
- **Pros**: Simple filtergraphs, near-zero runtime CPU load.
- **Cons**: Inflexible: cannot dynamically display episode titles, Reddit usernames, case file codes, or heart rates; repository bloat with large static image sets.
- **Effort**: Low.

---

## 4. Key Learnings
1. FFmpeg on this system is compiled with `--enable-librsvg`, which can natively rasterize SVGs inside FFmpeg filtergraphs; this eliminates the need for external Python C-extensions (`resvg-py`) and avoids buffering uncompressed 1080p RGBA frames in Python memory.
2. The active production loops currently reside in `assets/videos/longs/` (6 clips) and `assets/videos/shorts/` (2 clips), while `assets/loops/bank_manifest.json` points to legacy filenames that are not physically present in `assets/loops/`, leaving SQLite `video_loops` with 0 records. Reconciling this sync is essential for catalog integrity.
3. `assets/overlays/` and `assets/svg_overlays/` currently lack horizontal (16:9) assets and all Drama/Aelithia graphic assets; adding channel-specific visual packs will dramatically increase visual differentiation between the Horror and Drama channels.
