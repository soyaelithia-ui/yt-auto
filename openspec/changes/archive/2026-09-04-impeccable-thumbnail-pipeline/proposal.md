# Proposal: Impeccable High-CTR Thumbnail Pipeline

## Intent
The automated thumbnail generator (`src/media/thumbnails/`) currently falls back to primitive PIL vector polygons (`draw.polygon`, `draw.ellipse` stick figures) and excessive Gaussian blur over abstract procedural loops, yielding low-CTR, unpolished thumbnails. 

This change introduces a production-grade, niche-tailored thumbnail generation pipeline directly into `yt-auto`. It modularizes the proven designs from `scripts/design_impeccable_thumbnails.py`:
1. Eradication of primitive PIL stick-figure drawing in `AdaptiveSubjectCompositor`.
2. Dedicated niche compositing layouts (`ScpFoundFootageLayout`, `RedditDramaCardLayout`, `AnalogHorrorVhsLayout`).
3. 3D multi-pass typography engine (`draw_text_with_effects`) with diffuse ambient glow, deep blurred drop shadow, sharp high-contrast stroke, and vibrant foreground fills in safe zones.
4. Curated thematic asset resolver hierarchy (Explicit input -> Thematic Asset Bank -> Climax keyframe).
5. Comprehensive thumbnail quality assurance in `src/agents/qa_auditor.py` and `lib/qa_gatekeeper.py`.

## Scope
### In Scope
- Create modular layout compositors in `src/media/thumbnails/layouts/`:
  - `ScpFoundFootageLayout`: Live security camera HUD, Foundation classification header, industrial chevron hazard stripes, Euclid/Keter containment badge, and directional gradient mask.
  - `RedditDramaCardLayout`: Glassmorphic Reddit post header card (r/ icon, subreddit, OP metadata, orange upvote pill), dramatic quote callout bubble, and directional gradient mask.
  - `AnalogHorrorVhsLayout`: VHS Camcorder REC HUD, audio frequency tuner badge, CRT interlaced scanlines, classified tape callout, and atmospheric vignette.
- Upgrade `DynamicTypographyEngine` in `src/media/thumbnails/typography.py` with multi-pass 3D rendering.
- Eradicate primitive geometric silhouette generation from `AdaptiveSubjectCompositor` in `src/media/thumbnails/subject_extractor.py`.
- Implement `ThematicAssetResolver` in `src/media/thumbnails/asset_resolver.py` for local-first curated asset fallback.
- Initialize `assets/thumbnails/templates/` with the proven high-fidelity master key visuals.
- Enhance `src/agents/qa_auditor.py` and `lib/qa_gatekeeper.py` to audit thumbnail resolution (1080x1920 vertical and 1920x1080 horizontal), minimum file size (>40 KB), text luminance contrast, and safe-zone compliance.
- Unit and integration tests in `tests/unit/test_channel_profile_and_thumbnails.py`.

### Out of Scope
- Altering the video stream-copy rendering engine (`src/media/loop_worker.py`).
- Changing the audio narration mastering or subtitle timing logic.

## Approach
1. **Red Test Phase**: Author test cases in `tests/unit/test_channel_profile_and_thumbnails.py` verifying all 3 niche layouts, 3D text effects, safe-zone bounding, and absence of crude PIL stick figures.
2. **Layout & Engine Modularization**: Implement `src/media/thumbnails/layouts/` and wire them into `ThumbnailEngine.generate`.
3. **Asset Resolver & Asset Bank**: Implement `ThematicAssetResolver` and copy master reference backdrops to `assets/thumbnails/templates/`.
4. **Typography Upgrade**: Update `DynamicTypographyEngine` with multi-pass rendering.
5. **QA Fortification**: Update `qa_auditor.py` and `qa_gatekeeper.py`.
6. **Green Test & Integrity Verification**: Run pytest and `./scripts/verify_integrity.sh`.

## Capabilities
### New Capabilities
- `impeccable-thumbnail-pipeline`: Automated, niche-tailored thumbnail compositing engine with specialized layout templates (SCP HUD, Reddit Card, Analog Horror VHS), 3D multi-pass typography, and local thematic asset resolution.

### Modified Capabilities
- `visual-qa-inspection`: Added validation criteria for rendered thumbnail artifacts, checking aspect-ratio resolution, minimum file size, luminance contrast, and YouTube player safe-zone clearance.

## Impact
- **New files**: `src/media/thumbnails/layouts/base.py`, `src/media/thumbnails/layouts/scp_hud.py`, `src/media/thumbnails/layouts/reddit_card.py`, `src/media/thumbnails/layouts/analog_horror.py`, `src/media/thumbnails/asset_resolver.py`.
- **Modified files**: `src/media/thumbnails/engine.py`, `src/media/thumbnails/typography.py`, `src/media/thumbnails/subject_extractor.py`, `lib/video.py`, `src/agents/qa_auditor.py`, `lib/qa_gatekeeper.py`, `tests/unit/test_channel_profile_and_thumbnails.py`.
- **Breaking changes**: None. Deprecated PIL polygon routines in `AdaptiveSubjectCompositor` are replaced with high-craft compositing while preserving the public method signatures.

## Rollback Plan
If regressions occur, revert git commit via `git revert HEAD` and restore previous thumbnail generator.
