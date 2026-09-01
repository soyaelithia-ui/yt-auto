# Proposal: Dynamic Channel Registry Unification & Path Sanitization

## Intent
Resolve architectural coupling where channel definitions are split between a static 2-channel enum (`CanonicalChannel.MOKU`, `CanonicalChannel.AELITHIA` in `src/core/domain.py` and `src/config.py`) and a dynamic declarative registry (`ChannelProfileRegistry` loading from `config/channels/*.json`). In addition, purge residual hardcoded foreign paths (`/home/...`) across test suites and Docker configurations.

## Scope

### In Scope
- Unify channel resolution so that `src/core/domain.py` and `src/config.py` dynamically integrate with `ChannelProfileRegistry` and support any channel configured in `config/channels/` (including `scifi.json` and future additions) while preserving full backward compatibility for `moku` and `aelithia`.
- Sanitize residual hardcoded foreign filesystem paths in `tests/unit/test_audio_quality.py`, `tests/unit/test_media_integrity.py`, and `docker-compose.yml`.
- Validate that all credential/cookie paths adhere to `.env` and `secrets/` isolation with zero repo-level secret retention.

### Out of Scope
- Media DSP audio mastering, video encoding codecs, or FFmpeg pipelines.
- Adding actual production secret/cookie payloads to the repository (strictly forbidden by security architecture).

## Capabilities

### Modified Capabilities
- `channel-management`: Extended to dynamically resolve channel profiles from `config/channels/` without requiring code-level enum modifications.
- `test-infrastructure`: Sanitized to use workspace-relative dynamic fixtures instead of absolute foreign paths.

## Approach
1. **Dynamic Channel Domain Model**:
   - Refactor `canonical_channel()` and `ChannelSettings` resolution in `src/core/domain.py` and `src/config.py` to query `ChannelProfileRegistry.list_active_channel_ids()` and fallback aliases dynamically.
   - Retain `CanonicalChannel` string compatibility constants to prevent breaking legacy imports and typing contracts.
2. **Path Sanitization in Test & Docker Suites**:
   - Replace `/home/Moku/...` and `/home/mvfhymyhqw/...` strings in `test_audio_quality.py`, `test_media_integrity.py`, and `docker-compose.yml` with dynamic `tmp_path`, `REPO_ROOT`, or environment-driven variables.
3. **Verification**:
   - Run the full test suite (`pytest`) ensuring 100% pass rate across unit, integration, and E2E suites.

## Affected Areas
| Area | Impact | Description |
|------|--------|-------------|
| `src/core/domain.py` | MEDIUM | Make channel validation accept any registered channel ID while retaining canonical aliases |
| `src/config.py` | MEDIUM | Dynamic `ChannelSettings` lookup via `ChannelProfileRegistry` |
| `tests/unit/test_audio_quality.py` | LOW | Clean legacy foreign path strings |
| `tests/unit/test_media_integrity.py` | LOW | Clean legacy foreign path strings |
| `docker-compose.yml` | LOW | Clean hardcoded binary fallback path |

## Risks
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Breaking legacy imports expecting `CanonicalChannel.MOKU` | Low | Maintain `CanonicalChannel` as a dynamic-friendly str-compatible class |
| Test failures due to path alterations | Low | Use pytest `tmp_path` fixtures and `REPO_ROOT` anchors |

## Performance Impact
Zero performance impact on video generation or audio mastering. Channel registry loading is cached in memory with file mtime validation.

## Rollback Plan
1. Revert changes to `src/core/domain.py`, `src/config.py`, `tests/unit/`, and `docker-compose.yml` via Git.
2. No DB migrations or external dependency changes are introduced.

## Success Criteria
- [ ] Any channel defined in `config/channels/*.json` (e.g. `scifi`) is accepted by CLI and channel resolution without errors.
- [ ] Legacy aliases (`moku`, `aelithia`, `terror`, `aita`, etc.) resolve seamlessly.
- [ ] No hardcoded `/home/Moku` or foreign absolute paths remain in test files or configs.
- [ ] Entire test suite (`pytest`) passes with 0 regressions.
