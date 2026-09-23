# Proposal: Replace Nonsensical Channel and Lane Names ("Moku", "Aelithia") with Thematic Identifiers

## Intent

The project historically relied on arbitrary, fantasy channel names (`"moku"` for the horror/SCP channel and `"aelithia"` for the drama/moral dilemmas channel). These names were hardcoded across core domain models (`CanonicalChannel`), production lane IDs (`moku-scp-shorts`, `aelithia-aita-long`), voice profiles (`moku_terror`, `aelithia_reddit`), generator functions, default parameter arguments, and database constraints.

This proposal refactors the architecture so that standard thematic channel identifiers (`"horror"` and `"drama"`, alongside existing `"scifi"`) serve as the single source of truth (SSOT). All legacy fantasy names are relegated to a transparent backwards-compatibility alias layer, eliminating confusion, anti-patterns, and brand hardcoding while ensuring zero regressions across databases, tokens, and active daemons.

## Scope

### In Scope
- **Canonical Domain Model Inversion**: Redefine `CanonicalChannel` in `src/core/domain.py` with `HORROR = "horror"`, `DRAMA = "drama"`, and `SCIFI = "scifi"` as canonical enum members, keeping `MOKU` and `AELITHIA` as backward-compatible enum/alias references.
- **Production Lane Renaming**: Update canonical lane IDs in `config/lanes.json` and `src/core/lanes.py` to `horror-scp-shorts`, `horror-horror-long` (or `horror-long`), `drama-aita-long`, and `drama-drama-shorts` (or `drama-shorts`), mapping previous IDs in `LANE_ALIASES`.
- **Voice Profile Standardization**: Define canonical voice profiles `horror_terror` and `drama_reddit` in `config/voice_profiles.json` and `src/core/lanes.py`, retaining aliases for `moku_terror` and `aelithia_reddit`.
- **Default Parameter Sanitization**: Replace hardcoded `channel: str = "moku"` and `stamp_text="[MOKU]"` across `src/daemon.py`, `src/scene_manifest.py`, `src/db.py`, `src/api_health.py`, `src/agents/story_director.py`, and `src/audio/tts_router.py` with `"horror"` or dynamic channel resolution.
- **Narrative and Curator Aliasing**: Promote `build_horror_short_narrative`, `build_drama_short_narrative`, `HORROR_STORIES`, and `DRAMA_STORIES` as primary interfaces in `src/templates/` and `src/curators/`, keeping existing names as aliases.
- **Database Schema Accommodation**: Ensure SQLite constraints in `src/core/repository/migrations.py` allow `'horror'`, `'drama'`, and `'scifi'` without integrity failures.
- **MCP Server Parity**: Update MCP tool parameter descriptions in `src/mcp/tools/` and `docs/MCP.md` to reference `('horror', 'drama', 'scifi')`.

### Out of Scope
- Modifying OS-level usernames, system paths (e.g. `/home/moku`), or systemd user service configs that reference the host user.
- Breaking or purging existing SQLite database rows that already contain `'moku'` or `'aelithia'`.
- Deleting physical video loop assets on disk; filenames like `moku_*` and `aelithia_*` will remain indexed through thematic tags (`horror`, `drama`).

## Capabilities

### New Capabilities
None

### Modified Capabilities
- `multi-channel-lanes-and-smoke-test`: Update canonical channel and lane specifications from legacy names (`moku`, `aelithia`) to standard thematic identifiers (`horror`, `drama`, `scifi`), maintaining backward-compatible alias resolution.

## Approach

1. **Invert Enum & Channel Resolution (`src/core/domain.py`)**:
   `CanonicalChannel.HORROR = "horror"` and `CanonicalChannel.DRAMA = "drama"` become the canonical members. `CanonicalChannel.MOKU` is aliased to `CanonicalChannel.HORROR`, and `CanonicalChannel.AELITHIA` is aliased to `CanonicalChannel.DRAMA`. `CHANNEL_ALIASES` will map `"moku"` $\rightarrow$ `HORROR` and `"aelithia"` $\rightarrow$ `DRAMA`.
2. **Normalize Lane Catalog (`config/lanes.json` & `src/core/lanes.py`)**:
   The primary production lanes become `horror-scp-shorts`, `horror-horror-long`, `drama-aita-long`, and `drama-drama-shorts`. `LANE_ALIASES` maps all legacy combinations (`moku-scp-shorts` $\rightarrow$ `horror-scp-shorts`, `aelithia-aita-long` $\rightarrow$ `drama-aita-long`).
3. **Harmonize Templates & Curators (`src/templates/` & `src/curators/`)**:
   Expose canonical narrative generator functions (`build_horror_short_narrative`, `build_drama_short_narrative`, `get_horror_longform_story`, `get_drama_longform_story`) as the primary implementation, delegating legacy `build_moku_*` and `build_aelithia_*` calls directly to them.
4. **Decouple Function Defaults & Manifests (`src/`)**:
   Replace magic strings `"moku"` and `"[MOKU]"` in function signatures with `"horror"` or dynamic resolution from `ChannelProfileRegistry.get_default_channel_id()`.
5. **Update Tests & MCP Documentation**:
   Update unit tests and `docs/MCP.md` to guarantee 100% bidirectional parity via `scripts/verify_mcp_sync.py` and `./scripts/verify_integrity.sh`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/core/domain.py` | Modified | `CanonicalChannel` enum inversion; canonical `horror`, `drama`, `scifi` |
| `config/lanes.json` | Modified | Canonical lane IDs updated to thematic conventions |
| `src/core/lanes.py` | Modified | Canonical lane documents, `LANE_ALIASES`, and voice profile fallbacks |
| `config/voice_profiles.json` | Modified | Canonical `horror_terror` and `drama_reddit` voice profiles |
| `src/daemon.py` | Modified | Channel defaults and friendly names updated |
| `src/scene_manifest.py` | Modified | Default stamp text and lane ID sanitized |
| `src/templates/narratives.py` | Modified | Canonical narrative builder functions and template aliases |
| `src/templates/longform_stories.py` | Modified | Canonical story lists and getters |
| `src/curators/text_splitter.py` | Modified | Curation configs keyed by canonical lane IDs |
| `src/core/repository/migrations.py` | Modified | Relax or extend table check constraints to include thematic channels |
| `src/mcp/tools/*.py` | Modified | Tool parameter descriptions updated to thematic channels |
| `docs/MCP.md` | Modified | Synchronize tool descriptions with code for MCP sync validation |
| `tests/` | Modified | Update tests to assert canonical channels while validating legacy aliases |

## Media Processing Performance Impact

- **Zero Encoding Overhead**: Renaming channels and lanes modifies metadata routing and string keys only; stream-copy video composition (`-c:v copy`) and EBU R128 audio mastering remain completely unaffected.
- **Resource Target Adherence**: Pipeline operations strictly adhere to $\le 2$ CPU Cores and $\le 2.0$ GiB RAM budget (REG-14).

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Database CHECK constraint failure on `'horror'`/`'drama'` analytics records | Medium | Update migration schema definition / constraint check in `src/core/repository/migrations.py`. |
| MCP drift failure during `./scripts/verify_integrity.sh` | Medium | Synchronize `docs/MCP.md` simultaneously with `src/mcp/tools/*.py`. |
| Breaking existing test suites expecting `CanonicalChannel.MOKU.value == "moku"` | Medium | Retain `MOKU = HORROR` and test both canonical `horror` and legacy alias `moku`. |
| Session token lookup failure (`tokens/moku.json`) | Low | `src/youtube/uploader.py` and `src/core/google_auth.py` resolve tokens via `CHANNEL_ALIASES`, searching `tokens/horror.json` or fallback `tokens/moku.json`. |

## Rollback Plan

If regressions occur, revert the commits cleanly on the branch `replace_nonsensical_names`. Because `moku` and `aelithia` aliases remain intact in all lookup dictionaries throughout this change, rolling back introduces zero schema corruption.

## Dependencies

- None. Uses existing Python 3.12/3.13 standard library and existing dependencies.

## Success Criteria

- [ ] `CanonicalChannel.HORROR.value == "horror"` and `CanonicalChannel.DRAMA.value == "drama"`.
- [ ] `canonical_channel("moku")` resolves to `CanonicalChannel.HORROR` and `canonical_channel("aelithia")` resolves to `CanonicalChannel.DRAMA`.
- [ ] `config/lanes.json` registers canonical thematic lanes (`horror-scp-shorts`, `horror-horror-long`, `drama-aita-long`, `drama-drama-shorts`).
- [ ] `resolve_lane_for_run` resolves both thematic lane IDs and legacy `moku-*` / `aelithia-*` IDs.
- [ ] Zero hardcoded `stamp_text="[MOKU]"` in `src/scene_manifest.py`.
- [ ] `python3 scripts/verify_mcp_sync.py` passes 100% with zero drift.
- [ ] `./scripts/verify_integrity.sh` exits 0 with all checks green.
