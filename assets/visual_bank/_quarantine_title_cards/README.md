# Quarantined title-card artwork

These JPEGs are **finished title cards / pre-baked thumbnails** (baked-in titles,
warning banners, Reddit UI, CRT overlays). They must **not** live under
`*/scenery/` or any other video-background pool.

## Why
If indexed as scenery, the compositor / `ThematicAssetResolver.resolve_scene_asset_path`
treats them as full-frame video backgrounds → frozen “cover as video” look
(e.g. “BITÁCORA PERDIDA DEL”, “ADVERTENCIA // TAPE-04 // ARCHIVE”).

## Rule
- Video backgrounds: clean scenery stills or motion loops only.
- Thumbnails: compose dynamic text on **clean** template backdrops under
  `assets/thumbnails/templates/` — never reuse these pre-baked cards as bases.
- Do not move files from this folder back into `scenery/` without removing baked text.
