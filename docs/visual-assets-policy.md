# Visual assets policy (backgrounds vs thumbnails)

> **Estado:** OFICIAL / REPOSITORIO  
> **Alcance:** `assets/visual_bank/`, scenery, loops, thumbnails, title cards  
> **Última actualización:** 2026-09

Single source of truth for classifying visual media. Keep this short; other docs link here instead of restating rules.

## Rules

1. **Video backgrounds** = clean scenery stills or motion loops (`assets/visual_bank/{channel}/scenery/`, `assets/loops/`, catalog procedural). **No** baked title text, warning badges, CRT/HUD chrome, Reddit UI, or finished covers. Prefer motion loops over scenery stills for video scenes; empty scenery falls through to catalog/procedural loops (never a baked title card). Filenames containing BITÁCORA/ADVERTENCIA are never indexed as backgrounds. Still backgrounds use canonical Ken Burns (zoom 1.00→1.10, ≥12 s @ 30 fps defaults).
2. **Title text / warning badges / HUD chrome** = thumbnail composition path only (`src/thumbnail.py`, layouts under `src/media/thumbnails/`, clean bases in `assets/thumbnails/templates/`). Compose text dynamically — never use pre-baked title cards as video frames or as thumbnail bases.
3. **Misclassified title cards** go to `assets/visual_bank/_quarantine_title_cards/`. **Never** re-index them as scenery backgrounds. Do not move files back into `scenery/` until baked text/UI is removed.

## Code guards (do not bypass)

| Guard | Where |
|---|---|
| `is_eligible_background_asset` | `src/asset_manager.py` — excludes `_quarantine_title_cards`, `overlays`, `ambient_gifs`, GIFs, etc. from the background pool |
| Quarantine path skip | `src/media/thumbnails/asset_resolver.py`, `src/media/assets.py` |
| Regression tests | `tests/unit/test_title_card_background_quarantine.py`, `tests/unit/test_template_and_asset_manager.py` |

## Related (do not duplicate)

- Catalog integrity (CI seed vs prod, no ghost scenery): [POLITICA_CATALOGO_CI.md](POLITICA_CATALOGO_CI.md)
- Quarantine folder note: [`assets/visual_bank/_quarantine_title_cards/README.md`](../assets/visual_bank/_quarantine_title_cards/README.md)
