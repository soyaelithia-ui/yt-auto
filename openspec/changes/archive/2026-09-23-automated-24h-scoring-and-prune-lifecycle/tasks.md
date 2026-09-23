# Tasks: Automated 24h Performance Scoring and Underperforming Video Pruning Lifecycle

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~320 - 380 lines |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single reviewable PR / branch |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Database schema migration & indices for scoring | PR 1 | `.venv/bin/pytest tests/unit/test_analytics_migration.py -v` | SQLite migrations in memory | Revert `MIGRATION_008` in `src/core/repository/migrations.py` |
| 2 | Empirical scoring formula & song attribution | PR 1 | `.venv/bin/pytest tests/unit/test_analytics_scoring.py -v` | Pure Python unit test | Delete `src/analytics/scoring.py` |
| 3 | Criteria-based automated video pruner with safety bounds | PR 1 | `.venv/bin/pytest tests/unit/test_analytics_pruner.py -v` | In-memory DB + mock YouTube API | Delete `src/analytics/pruner.py` |
| 4 | Daemon 24h maintenance sweep & CLI subcommands | PR 1 | `.venv/bin/pytest tests/unit/test_maintenance_sweep.py -v` | `python3 main.py sweep-24h --dry-run` | Revert changes in `src/daemon.py` and CLI handlers |

---

## Phase 1: Foundation & Database Migration

- [x] 1.1 **[RED]** Create `tests/unit/test_analytics_migration.py` verifying that `migrate_database` adds `actual_success_score` and `music_track` to `publications`, adds `last_24h_sweep_at` to `scheduler_state`, and creates `idx_publications_score`.
- [x] 1.2 **[GREEN]** Update `src/core/repository/migrations.py` to add `MIGRATION_008` (or next sequential migration) defining the new columns and SQLite indices.
- [x] 1.3 Update `PublishedVideoRecord` in `src/core/inventory.py` to include `actual_success_score: float = 0.0` and `music_track: str | None = None`.

## Phase 2: Empirical Scoring & Music Attribution Engine

- [x] 2.1 **[RED]** Create `tests/unit/test_analytics_scoring.py` specifying tests for:
  - High engagement scenario computing score $\ge 70.0$ and $\le 100.0$.
  - Zero-view zero-engagement edge case returning $0.0$ without `ZeroDivisionError`.
  - Background music attribution aggregating average scores across videos.
  - Video lookup by SHA256 in $< 5\text{ ms}$.
- [x] 2.2 **[GREEN]** Create `src/analytics/scoring.py` implementing `calculate_empirical_score`, `sync_and_score_channel_publications`, and `get_top_performing_music_tracks`.
- [x] 2.3 Update `src/analytics/__init__.py` to export the public scoring interfaces.

## Phase 3: Autonomous Underperforming Video Pruner

- [x] 3.1 **[RED]** Create `tests/unit/test_analytics_pruner.py` specifying tests for:
  - Video younger than 24 hours is protected by mandatory grace period.
  - Eligible video older than 24h with low score and views is marked for pruning.
  - Daily deletion ceiling strictly caps deletions to $\le 2$ videos per channel per 24h window.
  - Kill-switch (`AUTO_PRUNE_ENABLED=false`) aborts all deletions immediately.
  - Quota exhaustion (HTTP 429) stops batch deletion gracefully without crashing.
- [x] 3.2 **[GREEN]** Create `src/analytics/pruner.py` implementing `evaluate_prune_candidates` and `execute_autonomous_prune` with safety assertions, YouTube API deletion dispatch, and SQLite state update to `PURGED_UNDERPERFORMING`.
- [x] 3.3 Add Telegram operational audit logging for pruned items in `src/analytics/pruner.py`.

## Phase 4: Daemon & CLI Integration

- [x] 4.1 **[RED]** Create `tests/unit/test_maintenance_sweep.py` verifying that `run_24h_maintenance_sweep` updates `last_24h_sweep_at` in `scheduler_state` and executes cleanly in dry-run mode.
- [x] 4.2 **[GREEN]** Implement `_run_24h_maintenance_sweep` in `src/daemon.py` inside the `start_daemon_lanes` loop, guarded by `elapsed >= 86400` check and non-blocking exception handling.
- [x] 4.3 Create `src/cli/handlers/analytics.py` and update `src/cli/subparsers.py` to register `sweep-24h` and `prune-underperforming` CLI commands with `--dry-run` and `--live` flags.

## Phase 5: Verification & Integrity Audit

- [x] 5.1 Run all new unit tests: `.venv/bin/pytest tests/unit/test_analytics_*.py tests/unit/test_maintenance_sweep.py -v`.
- [x] 5.2 Execute full anti-regression suite: `.venv/bin/pytest tests/unit/test_anti_regression_guardrails.py -v`.
- [x] 5.3 Verify MCP sync: `.venv/bin/python3 scripts/verify_mcp_sync.py`.
- [x] 5.4 Mandatory repository integrity audit: `./scripts/verify_integrity.sh`.
