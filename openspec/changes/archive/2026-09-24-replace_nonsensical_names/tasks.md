# Tasks: Replace Nonsensical Channel and Lane Names

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~350-390 lines |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | Single PR (atomic channel & alias inversion) |
| Delivery strategy | single-pr |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No  
Chained PRs recommended: No  
Chain strategy: feature-branch-chain  
400-line budget risk: Medium  

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Core domain enum inversion and alias resolution | PR 1 | `.venv/bin/pytest tests/unit/test_channel_domain_dynamic.py -v` | Unit tests | `src/core/domain.py` |
| 2 | Lane configuration and voice profile standardization | PR 1 | `.venv/bin/pytest tests/unit/test_channels_lanes.py -v` | Unit tests | `config/lanes.json`, `src/core/lanes.py` |
| 3 | Templates, curators, and manifest default sanitization | PR 1 | `.venv/bin/pytest tests/unit/test_narrative_refinement.py tests/unit/test_scene_manifest_clean_schema.py -v` | Unit tests | `src/templates/`, `src/curators/`, `src/scene_manifest.py` |
| 4 | Database schema check relaxation and MCP sync verification | PR 1 | `.venv/bin/python3 scripts/verify_mcp_sync.py && ./scripts/verify_integrity.sh` | CLI / scripts | `src/core/repository/migrations.py`, `docs/MCP.md` |

---

## Phase 1: Core Domain Enum Inversion (TDD)

- [ ] 1.1 (RED Test TM-1): Add test in `tests/unit/test_channel_domain_dynamic.py` asserting `CanonicalChannel.HORROR.value == "horror"`, `CanonicalChannel.DRAMA.value == "drama"`, and that `canonical_channel("moku") == CanonicalChannel.HORROR` and `canonical_channel("aelithia") == CanonicalChannel.DRAMA`.
- [ ] 1.2 (GREEN): Invert `CanonicalChannel` in `src/core/domain.py` so `HORROR = "horror"` and `DRAMA = "drama"` are the canonical enum values. Alias `MOKU` to `HORROR` and `AELITHIA` to `DRAMA`, and update `CHANNEL_ALIASES`.
- [ ] 1.3: Verify `test_channel_domain_dynamic.py` passes 100%.

## Phase 2: Lane Catalog and Voice Profile Standardization (TDD)

- [ ] 2.1 (RED Test TM-2 & TM-3): Add tests in `tests/unit/test_channels_lanes.py` validating that querying lanes and voice profiles for `"horror"` resolves canonical lane `horror-scp-shorts` / `horror-horror-long` and voice profile `horror_terror`, while querying legacy lane `"moku-horror-long"` resolves correctly through `LANE_ALIASES`.
- [ ] 2.2 (GREEN): Update `config/lanes.json` with canonical lane IDs `horror-scp-shorts`, `horror-horror-long`, `drama-aita-long`, and `drama-drama-shorts`.
- [ ] 2.3 (GREEN): Update `src/core/lanes.py` with `LANE_ALIASES` mapping all legacy fantasy names to the canonical thematic lanes, and update `FALLBACK_LANE_DOCUMENTS` and voice profile fallbacks.
- [ ] 2.4 (GREEN): Add canonical `horror_terror` and `drama_reddit` entries in `config/voice_profiles.json` while maintaining existing keys as aliases.

## Phase 3: Templates, Curators, and Defaults Sanitization

- [ ] 3.1: Expose canonical narrative builders (`build_horror_short_narrative`, `build_drama_short_narrative`, `build_horror_longform_narrative`, `build_drama_longform_narrative`) as primary in `src/templates/narratives.py`, aliasing legacy `build_moku_*` and `build_aelithia_*` to them.
- [ ] 3.2: Expose `HORROR_STORIES` and `DRAMA_STORIES` in `src/templates/longform_stories.py`.
- [ ] 3.3: Update `LANE_CURATION_CONFIGS` in `src/curators/text_splitter.py` to key primarily by canonical thematic lane IDs.
- [ ] 3.4: Sanitize default parameter values in `src/daemon.py` (`channel: str = "horror"`), `src/scene_manifest.py` (`stamp_text="[CLASSIFIED]"`, `channel_name="horror"`), `src/db.py`, `src/api_health.py`, and `src/audio/tts_router.py`.

## Phase 4: Database Schema Check and MCP Synchronization (TDD)

- [ ] 4.1 (RED Test TM-4): Add test in `tests/unit/test_repository_migration_003.py` or `tests/unit/test_multichannel_db.py` verifying analytics snapshot insertion with channel `"horror"` and `"drama"`.
- [ ] 4.2 (GREEN): In `src/core/repository/migrations.py`, update `video_analytics_snapshots` table constraint to `CHECK(channel IN ('horror', 'drama', 'scifi', 'moku', 'aelithia'))`.
- [ ] 4.3 (RED Test TM-5): Verify `scripts/verify_mcp_sync.py` flags any drift if descriptions in `src/mcp/tools/*.py` are updated.
- [ ] 4.4 (GREEN): Update tool parameter descriptions in `src/mcp/tools/list_lanes.py`, `system_preflight.py`, `query_loop_catalog.py`, and `manage_queue.py` to `('horror', 'drama', 'scifi')`, and synchronize `docs/MCP.md` simultaneously.

## Phase 5: Anti-Regression Verification and Integrity Gate

- [ ] 5.1: Run targeted unit tests: `.venv/bin/pytest tests/unit/test_channel_domain_dynamic.py tests/unit/test_channels_lanes.py tests/unit/test_scene_manifest_clean_schema.py -v`.
- [ ] 5.2: Run MCP parity check: `.venv/bin/python3 scripts/verify_mcp_sync.py`.
- [ ] 5.3: Run full anti-regression suite: `.venv/bin/pytest tests/unit/test_anti_regression_guardrails.py -v`.
- [ ] 5.4: Execute full repository integrity gate: `./scripts/verify_integrity.sh`.
