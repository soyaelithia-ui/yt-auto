# Proposal: VPS FFmpeg Hot-Path Smoke (copy + veryfast)

## Intent
Main already targets cheap FFmpeg (beats stream-copy; `DIRECTOR_SINGLE_PASS`; `veryfast`/CRF 21). Before HUD/thumb look PRs, prove the VPS actually emits those flags. If smoke fails, stop.

## Scope

### In Scope
- Inspect one production-like encode on the VPS (ffmpeg stderr via `YT_COMPOSE_STREAM_STDERR`).
- Assert beats / no-HUD director: `-c:v copy`.
- Assert unavoidable re-encode: `-preset veryfast` and CRF 21 (`encode_defaults`).
- Record pass/fail. Fail-closed gate for `planner-hud-layout-channel-accent` and `parametric-generic-thumbnail`.
- Optional log-grep helper under `scripts/` only. No hot-path edits.

### Out of Scope
- Planner `niche_hud.hud_layout` and channel accent
- Generic thumbnails / removing `scp_hud.py` / `reddit_card.py`
- Edits to `src/media/compositor.py`, `src/media/proc_engine.py`, `src/pipeline.py`
- Changing `RENDER_PRESET` / `RENDER_CRF`

## Capabilities

### New Capabilities
- `ffmpeg-hot-path-smoke`: Evidence gate that live FFmpeg argv matches copy vs veryfast/CRF21 contracts.

### Modified Capabilities
- None

## Approach
1. Confirm compose: `RENDER_PRESET=veryfast`, `RENDER_CRF=21`, `DIRECTOR_SINGLE_PASS=1`.
2. Smoke a beats lane (`config/lanes.json` is all `visual_pipeline: beats`) and grep `-c:v copy`.
3. If a re-encode appears in logs, grep `-preset veryfast` and CRF 21; do not invent a director job.
4. Existing unit tests stay; this is production evidence.
5. On fail: do not open look PRs.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| VPS ffmpeg stderr / compose logs | Inspected | Evidence of copy vs veryfast |
| `docker-compose.yml` | Unchanged | Already pins veryfast/CRF21 |
| `src/media/encode_defaults.py` | Unchanged | Re-encode SSOT |
| `scripts/smoke_ffmpeg_hot_path.sh` | New (optional) | Log grep helper |
| `compositor.py` / `proc_engine.py` / `pipeline.py` | None | Do not touch |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Prod lanes never hit director | High | Prove beats copy first; claim veryfast only if a re-encode is logged |
| Logs omit argv | Med | Require `YT_COMPOSE_STREAM_STDERR=1`; fail if evidence absent |
| Smoke used to retouch hot path | Med | Out of scope unless defaults ignored |

## Rollback Plan
Delete any new smoke script. No product code to revert. Follow-up changes stay unopened.

## Dependencies
- VPS or captured prod ffmpeg stderr
- Exploration `sdd/explore/config-driven-look-cheap-render`

## Success Criteria
- [ ] Beats/no-HUD evidence of `-c:v copy`
- [ ] Re-encode evidence of `veryfast` + CRF 21, or explicit "no re-encode observed"
- [ ] No compositor/proc_engine/pipeline edits
- [ ] Look PRs not opened if smoke fails
