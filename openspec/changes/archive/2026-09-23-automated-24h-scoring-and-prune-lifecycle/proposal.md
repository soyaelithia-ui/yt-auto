# Proposal: Automated 24h Performance Scoring and Underperforming Video Pruning Lifecycle

## Intent
Automate post-publishing channel health and performance optimization. Currently, story scoring only happens pre-publishing (`src/core/scoring.py`), while YouTube Data API statistics synchronization (`src/youtube/analytics.py`) and channel purging (`src/cli/purge_channels.py`) are manual, ad-hoc, and require interactive terminal confirmation (`DELETE`).

This change introduces an automated 24-hour background lifecycle into the continuous daemon. Every 24 hours, the system:
1. Syncs YouTube Data API v3 metrics for published videos.
2. Computes a normalized Empirical Success Score ($0-100$) combining view velocity, engagement ratio ($\text{likes} + \text{comments} / \text{views}$), and audience retention.
3. Attributes performance scores to the background music tracks/songs and video hashes.
4. Identifies underperforming videos that have passed a mandatory 24h grace period and fall below a strict survival threshold ($score < 25.0$ and views $< 50$).
5. Safely purges (or unlists) underperforming videos with rate-limiting and a maximum bounded deletion cap per cycle (max 2 videos/day per channel) to preserve channel authority and API quota.

## Scope

### In Scope
- **Automated 24h Cadence Step**: Integration of a periodic 24-hour analytics evaluation sweep inside the daemon orchestrator (`src/orchestrator/` and `src/cli/main.py`).
- **Normalized Empirical Success Scoring Engine**: Dedicated scoring algorithm in `src/analytics/scoring.py` computing normalized scores ($0-100$) and attributing scores to specific music tracks/songs and video hashes.
- **Automated Criteria-Based Pruning Policy**: Automated deletion of underperforming videos with strict safeguards:
  - Mandatory evaluation grace period ($\ge 24\text{ hours}$ post-upload).
  - Configurable minimum performance threshold ($score < 25.0$ or bottom 10th percentile).
  - Hard safety cap on deletions ($\le 2$ videos deleted per channel per 24-hour cycle).
  - Quota breaker: immediate halt on HTTP 429 or quota limit.
- **SQLite Database Indexing**: Lightweight schema migration in `src/core/repository/migrations.py` adding `actual_success_score` and `music_track` indices to `publications` and `video_analytics_snapshots`.
- **Telegram Operational Logging**: Emit structured Telegram notifications detailing scores computed and any videos safely pruned.

### Out of Scope
- Pre-publishing story curation changes (retains existing `src/core/scoring.py` heuristic & LLM two-stage gate).
- Immediate/instant deletion of videos younger than 24 hours (strictly prohibited by the grace period).
- Bulk channel wipeout or wiping high-performing videos.

## Capabilities

### New Capabilities
- `video-performance-scoring`: Automated empirical scoring algorithm calculating normalized success metrics ($0-100$), time-decayed view velocity, engagement ratios, and music track attribution from YouTube Data API v3 statistics.

### Modified Capabilities
- `channel-purge-control`: Extends purge capability with automated criteria-based pruning (grace period $\ge 24\text{h}$, minimum score threshold, bounded deletion quota) without requiring interactive terminal prompts while preserving dry-run safety.
- `continuous-daemon-scheduler`: Adds an autonomous 24-hour cadence sweep cycle for analytics synchronization, success scoring, and underperforming video pruning.

## Approach

1. **Scoring Engine (`src/analytics/scoring.py`)**:
   - Calculate normalized engagement:
     $$\text{Engagement Rate} = \frac{\text{likes} \cdot 10 + \text{comments} \cdot 25}{\max(\text{views}, 1)}$$
   - Calculate time-decayed view velocity against channel median benchmarks:
     $$\text{Velocity} = \frac{\text{views}}{\max(1.0, \text{age\_hours})}$$
   - Composite Score ($0-100$):
     $$\text{Success Score} = \min\left(100.0, \left(0.4 \cdot \text{Normalized Views} + 0.35 \cdot \text{Engagement Rate} + 0.25 \cdot \text{Retention Pct}\right)\right)$$
   - Song/Audio Attribution: Extract music stem path from `publications.used_resources` JSON and map average success scores per audio track.

2. **Automated 24h Pruner (`src/analytics/pruner.py`)**:
   - Query publications where `strftime('%s', 'now') - strftime('%s', verified_at) >= 86400` (older than 24h).
   - Evaluate candidates against channel-specific thresholds (`MIN_SURVIVAL_SCORE = 20.0`, `MIN_VIEWS_24H = 50`).
   - If candidate qualifies for pruning:
     - Check daily quota: if channel already pruned $\ge 2$ videos in rolling 24h, skip remaining.
     - Call YouTube Data API `videos().delete(id=video_id)` with exponential backoff.
     - Mark status as `PURGED_UNDERPERFORMING` in SQLite `publications` and `stories` tables.
     - Emit event to Telegram notification bus.

3. **Daemon Integration (`src/orchestrator/lifecycle.py` / `src/cli/main.py`)**:
   - Check timestamp of last 24h sweep in `scheduler_state`.
   - If `now - last_sweep_at >= 86400` (or CLI `main.py sweep-24h`), execute analytics sync $\rightarrow$ score calculation $\rightarrow$ underperforming pruning.
   - Update `last_sweep_at`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/analytics/scoring.py` | New | Empirical scoring formula, song attribution, and leaderboard queries. |
| `src/analytics/pruner.py` | New | Criteria-based automated video deletion with grace period and quota caps. |
| `src/analytics/__init__.py` | Modified | Export scoring and pruning interfaces. |
| `src/core/repository/migrations.py` | Modified | Schema migration for `actual_success_score` column and index on `publications`. |
| `src/orchestrator/lifecycle.py` / `src/cli/main.py` | Modified | 24-hour cadence trigger in continuous daemon scheduler and CLI command. |
| `openspec/specs/channel-purge-control/spec.md` | Modified | Delta spec for criteria-based autonomous pruning. |
| `openspec/specs/continuous-daemon-scheduler/spec.md` | Modified | Delta spec for 24h analytics and pruning sweep. |
| `openspec/specs/video-performance-scoring/spec.md` | New | Full spec for empirical performance scoring and song attribution. |

## Media Processing Performance Impact
- **Zero Media Re-encoding**: This change involves zero FFmpeg, video rendering, or audio mixing processing.
- **Resource Footprint**: Lightweight SQLite queries and HTTPS requests to YouTube Data API v3.
- **CPU & Memory**: Steady-state CPU overhead is $< 1\%$ across all threads; peak memory allocation is $< 15\text{ MiB}$, strictly complying with the $\le 2\text{ Cores}$ and $\le 2.0\text{ GiB RAM}$ SLA.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| **Premature Deletion of Slow-Burn Videos** | Medium | Enforce mandatory 24h (or configurable 48h) grace period; conservative score threshold ($< 20$); maximum 2 videos deleted per day. |
| **YouTube Data API Quota Exhaustion** | Low | Deletions cost 50 units (low); inspect channel uploads via playlistItems (1 unit); circuit trip immediately on HTTP 429. |
| **Accidental High-Performing Video Deletion** | Low | Multiple safety assertions: video MUST have score below floor AND views below threshold; deletion order sorted ascending by score. |
| **Database Lock Contention with Ingestion/Render** | Low | All SQLite updates execute in short transactions with WAL mode and exponential retry. |

## Rollback Plan
1. Set environment variable `AUTO_PRUNE_ENABLED=false` or `--disable-prune` flag to instantaneously disable all deletion logic while keeping scoring active.
2. CLI dry-run mode (`--dry-run`) enabled by default unless `--live` or daemon configuration explicitly enables live mutations.
3. Database changes are additive (new column with default values); rolling back involves discarding new columns or ignoring `actual_success_score`.

## Dependencies
- Google API Client (`googleapiclient.discovery.build`) for YouTube Data API v3 video deletion and statistics fetching.
- SQLite WAL mode for non-blocking concurrent reads and writes.

## Success Criteria
- [ ] 24-hour periodic sweep executes autonomously in daemon mode without manual interaction.
- [ ] Empirical success scores ($0-100$) are calculated and persisted in `publications` and `video_analytics_snapshots`.
- [ ] Background music tracks/songs are correctly attributed with average performance scores.
- [ ] Videos younger than 24 hours are never marked or selected for deletion (100% grace period adherence).
- [ ] Underperforming videos meeting deletion criteria are pruned cleanly on YouTube and marked `PURGED_UNDERPERFORMING` in SQLite.
- [ ] Daily deletion ceiling ($\le 2$ videos/channel/day) is strictly enforced.
- [ ] 100% test coverage with offline synthetic mocks and `./scripts/verify_integrity.sh` passing.
