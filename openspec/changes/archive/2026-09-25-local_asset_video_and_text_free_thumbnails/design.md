# Design

## Runtime flow

1. Stage 4 resolves one or more local video files from the loop catalog.
2. Stage 8 writes an asset-only manifest with `engine_type: catalog_loop`.
3. Stage 9 always invokes `LoopVideoEngine`; no renderer can synthesize frames or inject graphics.
4. Stage 11 asks SEO for a `thumbnail_asset_request`, resolves a local AI-bank image, and exports only resize/color grading.

## Boundaries

- Accepted lane pipelines: `director`, `video_loop`.
- Accepted scene engine: `catalog_loop`.
- Retired modules: image animation/Ken Burns, hybrid renderer, SVG/in-memory overlays, HUD multi-act renderer, and director graphic filter helpers.
- Thumbnail bank rejects corrupt assets and names/sidecars that declare text; fallback stays local and deterministic.
- Agent recovery is provider-agnostic and applies equally to SDK and CLI execution.

## Compatibility

Legacy compositor aliases that do not request a retired engine resolve to `LoopVideoEngine`. Retired engine names fail closed. The old graphical modules and their dedicated tests are removed rather than shimmed.
