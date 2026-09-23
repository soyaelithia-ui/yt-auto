## Exploration: Replace Nonsensical Channel and Lane Names ("Moku", "Aelithia") with Thematic Identifiers

### Current State
The project historically used arbitrary, nonsensical names for its production channels:
- `"moku"` was assigned to the **Horror / SCP / Creepypasta** channel.
- `"aelithia"` was assigned to the **Drama / Moral Dilemmas / Reddit AITA** channel.

While configuration files in `config/channels/` have already been renamed to thematic identifiers (`horror.json`, `drama.json`, `scifi.json`) and `config/channels.json` sets `default_channel: "horror"`, the Python code remains inverted and tightly coupled to the legacy names:
1. `CanonicalChannel` in `src/core/domain.py` defines `MOKU = "moku"` and `AELITHIA = "aelithia"` as canonical, aliasing `HORROR` and `DRAMA` backward to `MOKU` and `AELITHIA`.
2. Production lane identifiers in `config/lanes.json` and `src/core/lanes.py` use `moku-scp-shorts`, `moku-horror-long`, `aelithia-aita-long`, and `aelithia-drama-shorts`. Thematic aliases (`horror-long`, `drama-shorts`) are mapped backward to the nonsensical names.
3. Voice profiles in `config/voice_profiles.json` and `src/core/lanes.py` use `moku_terror` and `aelithia_reddit`.
4. Python functions across `src/daemon.py`, `src/scene_manifest.py`, `src/db.py`, `src/api_health.py`, `src/narrative/quality_gate.py`, and `src/agents/story_director.py` hardcode `channel: str = "moku"` and `stamp_text="[MOKU]"` as default arguments.
5. Story generator modules in `src/templates/narratives.py` and `src/templates/longform_stories.py` expose functions and variables prefixed with `_MOKU_*` and `_AELITHIA_*` (`build_moku_short_narrative`, `build_aelithia_short_narrative`).
6. Curation configs and classes in `src/curators/` use `AelithiaDramaCurator` and `MokuHorrorCurator`.
7. Asset resolvers in `src/media/thumbnails/asset_resolver.py` resolve channel folders using `"moku"` and `"aelithia"` prefixes.
8. Database table definitions in `src/core/repository/migrations.py` contain CHECK constraints restricting channels to `('moku', 'aelithia')`.

### Affected Areas
- `src/core/domain.py` — Invert `CanonicalChannel` enum (`HORROR = "horror"`, `DRAMA = "drama"`, `SCIFI = "scifi"`), relegate `MOKU` and `AELITHIA` to backwards-compatible aliases, and update `CHANNEL_ALIASES`.
- `config/lanes.json` & `src/core/lanes.py` — Promote thematic lane IDs (`horror-scp-shorts`, `horror-horror-long` / `horror-long`, `drama-aita-long`, `drama-drama-shorts` / `drama-shorts`) as canonical definitions, and retain `moku-*` and `aelithia-*` in `LANE_ALIASES`.
- `config/voice_profiles.json` & `src/core/lanes.py` — Introduce `horror_terror` and `drama_reddit` canonical profile keys with backwards aliases for `moku_terror` and `aelithia_reddit`.
- `src/daemon.py`, `src/scene_manifest.py`, `src/db.py`, `src/api_health.py`, `src/audio/tts_router.py` — Replace default parameter `channel: str = "moku"` with `"horror"` or dynamically resolved default channel, and sanitize default stamp text from `"[MOKU]"` to generic `"[CLASSIFIED]"` or dynamic channel branding.
- `src/templates/narratives.py` & `src/templates/longform_stories.py` — Establish `build_horror_short_narrative`, `build_drama_short_narrative`, `build_horror_longform_story`, etc. as primary functions with legacy aliases preserved.
- `src/curators/text_splitter.py`, `src/curators/drama.py`, `src/curators/horror.py` — Key `LANE_CURATION_CONFIGS` by canonical thematic lane IDs, aliasing legacy names.
- `src/media/thumbnails/asset_resolver.py` & `src/media/loop/rotation.py` — Prioritize `"horror"` and `"drama"` in visual asset and scenery lookup.
- `src/mcp/tools/list_lanes.py`, `system_preflight.py`, `query_loop_catalog.py`, `manage_queue.py` — Update tool parameter descriptions from `('moku', 'aelithia')` to `('horror', 'drama', 'scifi')`.
- `src/core/repository/migrations.py` — Ensure `video_analytics_snapshots` and queue operations accommodate `"horror"`, `"drama"`, and `"scifi"`.
- `tests/` — Update unit and integration tests to validate both thematic canonical names and legacy alias resolution.

### Approaches
1. **Full Canonical Inversion with Compatibility Aliasing (Recommended)** — Invert `CanonicalChannel` so `HORROR = "horror"`, `DRAMA = "drama"`, and `SCIFI = "scifi"` are the SSOT. Update `config/lanes.json` and `src/` to use thematic identifiers as primary keys, while keeping `moku` and `aelithia` registered as aliases in `CHANNEL_ALIASES`, `LANE_ALIASES`, and voice configs.
   - Pros: Solves the bad practice cleanly across the entire codebase; aligns runtime code with `config/channels/{horror,drama,scifi}.json`; completely backwards-compatible with existing databases, tokens, and CLI flags.
   - Cons: Touches multiple modules and requires updating corresponding unit tests.
   - Effort: Medium

2. **Facade-Only Aliasing (Shallow Alias)** — Keep internal enum values as `"moku"` and `"aelithia"`, but allow CLI and APIs to accept `"horror"` and `"drama"` as external aliases.
   - Pros: Minimal code changes.
   - Cons: Leaves the anti-pattern untouched in code; internal logic, logs, and stack traces remain polluted with nonsensical fantasy names.
   - Effort: Low

3. **Hard Breaking Purge (Zero Legacy Aliases)** — Eradicate every mention of `"moku"` and `"aelithia"` without providing fallback aliases.
   - Pros: Maximum purity with zero legacy references.
   - Cons: High regression risk: breaks existing SQLite databases (`shorts_queue.db`, `review_state.db`), OAuth session tokens (`tokens/moku.json`), systemd scripts, and in-flight queue jobs.
   - Effort: High

### Recommendation
**Approach 1 (Full Canonical Inversion with Compatibility Aliasing)** is strongly recommended. It directly fulfills the user directive to eliminate the bad practice of nonsensical names in favor of standard thematic names (`horror`, `drama`, `scifi`), while guaranteeing zero downtime or regressions for existing queue items, tokens, or running daemons through transparent alias mappings.

### Risks
- **Database Schema Constraints**: `video_analytics_snapshots` in SQLite has a `CHECK(channel IN ('moku', 'aelithia'))` in migration 003. A migration or schema patch is required to allow `'horror'` and `'drama'` without failing SQLite integrity.
- **MCP Server Drift**: Changing tool field descriptions requires updating `docs/MCP.md` simultaneously to maintain 100% parity with `scripts/verify_mcp_sync.py`.
- **Token and Session Persistence**: YouTube OAuth credentials stored in `tokens/moku.json` and `cookies.json` must continue resolving seamlessly via channel alias lookup (`horror` -> `tokens/horror.json` or fallback `tokens/moku.json`).

### Ready for Proposal
Yes — The codebase investigation is complete, the affected files are identified, and the migration strategy is clear. The user can proceed to run `/sdd-propose` to create the formal change proposal.
