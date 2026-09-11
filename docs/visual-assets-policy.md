# Visual assets policy (backgrounds vs thumbnails)

> **Estado:** OFICIAL / REPOSITORIO  
> **Alcance:** `assets/videos/`, `assets/loops/`, thumbnails, title cards  
> **Última actualización:** 2026-09

Single source of truth for classifying visual media. Keep this short; other docs link here instead of restating rules.

## Rules

1. **Video backgrounds** = clean motion loops (`assets/videos/shorts/`, `assets/videos/longs/`, `assets/loops/`) or certified scenery stills. **No** baked title text, warning badges, CRT/HUD chrome, Reddit UI, or finished covers. Continuous single-loops are resolved via `LoopVideoEngine.resolve_continuous_loop`. Filenames containing BITÁCORA/ADVERTENCIA are never indexed as backgrounds. Still backgrounds use canonical Ken Burns (zoom 1.00→1.10, ≥12 s @ 30 fps defaults).
2. **Title text / warning badges / HUD chrome** = thumbnail composition path only (`src/thumbnail.py`, layouts under `src/media/thumbnails/`, clean bases in `assets/thumbnails/templates/`). Compose text dynamically — never use pre-baked title cards as video frames or as thumbnail bases.
3. **Misclassified title cards** = Quarantined and excluded from backgrounds. **Never** re-index them as scenery backgrounds. Do not use files until baked text/UI is removed.

## CTR composition

Production video renderer is FFmpeg. Do not treat WebGL/Canvas as the production stack.

- **Thumbnails = 3 layers:** clean backdrop (`assets/thumbnails/templates/{aita,horror,scp}/master_backdrop.jpg`, no baked OSD) → dynamic title (≤2 lines, word wrap, cream/white + black outline, no neon glow) → optional badge (omit NONE/empty; AITA `YTA`/`NTA`/`ESH`/`INFO`; SCP `SAFE`/`EUCLID`/`KETER`; horror `ADVERTENCIA · TAPE` only if `tape_id`). Camcorder OSD default off.
- **Video stills:** Ken Burns via FFmpeg `zoompan` 1.00→1.10; never a single zoompan >20s; split to 12–15s hard cuts (≥2–3 planes if duration >20s). Motion loops preferred; not Ken-Burned. Overlays (`film_grain` / `vignette` / `tv_static`) alpha 15–35%, never as background. No grey procedural loop as plane 0.
- **Audio (P1):** AAC 44100 + loudnorm `I=-16`.
- Continuous loops reside in `assets/videos/shorts/` and `assets/videos/longs/`; master catalog metadata in `assets/loops/bank_manifest.json`.

## Code guards (do not bypass)

| Guard | Where |
|---|---|
| `is_eligible_background_asset` | `src/asset_manager.py` — excludes `_quarantine_title_cards`, `overlays`, `ambient_gifs`, GIFs, etc. from the background pool |
| Quarantine path skip | `src/media/thumbnails/asset_resolver.py`, `src/media/assets.py` |
| Regression tests | `tests/unit/test_title_card_background_quarantine.py`, `tests/unit/test_template_and_asset_manager.py`, `tests/unit/test_thumbnail_ctr_anti_cases.py`, `tests/unit/test_thumbnail_ctr_fatal_fixtures.py`, `tests/unit/test_ctr_clean_backdrops.py`, `tests/unit/test_ken_burns_canonical.py` |

## Related (do not duplicate)

- Catalog integrity (CI seed vs prod, no ghost scenery): [POLITICA_CATALOGO_CI.md](POLITICA_CATALOGO_CI.md)
