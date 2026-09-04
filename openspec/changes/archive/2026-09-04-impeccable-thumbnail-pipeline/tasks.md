# Tasks: Impeccable High-CTR Thumbnail Pipeline

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 350-420 lines |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | Single atomic change |
| Delivery strategy | exception-ok |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Niche Layouts & 3D Typography | PR 1 | `pytest tests/unit/test_channel_profile_and_thumbnails.py -k "test_niche"` | `python scripts/design_impeccable_thumbnails.py` | `src/media/thumbnails/layouts/` |
| 2 | Asset Resolver & QA Gate | PR 1 | `pytest tests/unit/test_channel_profile_and_thumbnails.py` | `./scripts/verify_integrity.sh` | `src/media/thumbnails/asset_resolver.py` |

## Phase 1: RED Tests & Foundation

- [x] 1.1 Add failing RED tests in `tests/unit/test_channel_profile_and_thumbnails.py` covering SCP 9:16 HUD, Reddit 16:9 Card, Horror 16:9 VHS, 3D text effects, safe-zone bounds, and asset resolution.
- [x] 1.2 Create `src/media/thumbnails/layouts/base.py` defining `BaseThumbnailLayout` abstract contract and layout registry.
- [x] 1.3 Seed local master reference backdrops in `assets/thumbnails/templates/` (`scp`, `aita`, `horror`) from session artifacts `assets/` (read-only).

## Phase 2: Core Niche Layouts & Typography (GREEN)

- [x] 2.1 Implement `ScpFoundFootageLayout` in `src/media/thumbnails/layouts/scp_hud.py` with security cam HUD, classification bar, chevrons, and alert badge.
- [x] 2.2 Implement `RedditDramaCardLayout` in `src/media/thumbnails/layouts/reddit_card.py` with glassmorphic card, upvote badge, and dramatic quote bubble.
- [x] 2.3 Implement `AnalogHorrorVhsLayout` in `src/media/thumbnails/layouts/analog_horror.py` with VHS REC indicator, audio frequency tuner, CRT scanlines, and classified tape badge.
- [x] 2.4 Implement `GeneralCinematicLayout` in `src/media/thumbnails/layouts/cinematic.py` as high-craft editorial fallback.
- [x] 2.5 Upgrade `DynamicTypographyEngine` in `src/media/thumbnails/typography.py` with `draw_text_with_effects` (glow, 3D shadow, stroke, fill) and safe-line splitting.

## Phase 3: Asset Resolver & Pipeline Wiring

- [x] 3.1 Implement `ThematicAssetResolver` in `src/media/thumbnails/asset_resolver.py` implementing 3-tier local resolution.
- [x] 3.2 Purge primitive geometric stick-figure polygons (`draw.polygon`, `draw.ellipse`) from `AdaptiveSubjectCompositor` in `src/media/thumbnails/subject_extractor.py`.
- [x] 3.3 Wire layout dispatcher and asset resolver into `ThumbnailEngine.generate` in `src/media/thumbnails/engine.py`.
- [x] 3.4 Forward enriched story metadata from `create_video_thumbnail` in `lib/video.py` to `ThumbnailConfig`.

## Phase 4: QA Gatekeeper & Verification

- [x] 4.1 Update `audit_thumbnail` in `src/agents/qa_auditor.py` for aspect-ratio resolution (16:9 & 9:16), size $\ge 40\text{ KB}$, and safe-zone clearance.
- [x] 4.2 Wire thumbnail quality validation into `lib/qa_gatekeeper.py`.
- [x] 4.3 Run full test suite `pytest tests/unit/test_channel_profile_and_thumbnails.py -v` and `./scripts/verify_integrity.sh`.
