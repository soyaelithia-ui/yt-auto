# Implementation Tasks: Native Automated Link Collection, Comment Level Tracking, Empirical Scoring, and Intelligent AI Story Packaging

## Phase 1: Database Migration & Core Contracts
- [x] 1.1 Define `MIGRATION_008` in `src/core/repository/migrations.py` adding `comment_count`, `view_count`, `like_count`, `comment_status`, `comment_error`, `pinned_comment` to `publications`.
- [x] 1.2 Add schema migration indexes on `comment_status`, `comment_count`, and `view_count` in `migrations.py`.
- [x] 1.3 Update `PublishedVideoRecord` dataclass in `src/core/inventory.py` to include comment and view fields.
- [x] 1.4 Update `record_published_inventory` in `src/core/inventory.py` to persist comment metrics and failure statuses.

## Phase 2: Link Collector Subsystem
- [x] 2.1 Create `src/analytics/link_collector.py` with multi-channel link crawling and URL normalization (`watch`, `short`, `shorts`).
- [x] 2.2 Implement batch statistics retrieval (`viewCount`, `likeCount`, `commentCount`) for collected links.
- [x] 2.3 Implement atomic upsert of collected links into `publications` and `stories` tables.

## Phase 3: Pinned Comment Lifecycle & Failure Marking
- [x] 3.1 Create `src/youtube/comments.py` with `post_pinned_comment` using YouTube Data API `commentThreads.insert`.
- [x] 3.2 Implement non-crashing error interception for comments disabled, quota exhaustion, or auth errors.
- [x] 3.3 Update `src/pipeline/stages/stage_13_publish.py` to invoke comment posting post-publication and mark `comment_status` (`posted` vs `failed`).

## Phase 4: View-Based Empirical Scoring & Comment Level Categorization
- [x] 4.1 Implement `classify_comment_level(comments: int, views: int) -> str` in `src/analytics/scoring.py`.
- [x] 4.2 Refine `calculate_empirical_score` in `src/analytics/scoring.py` to evaluate comment velocity and view tiers.
- [x] 4.3 Update `sync_and_score_channel_publications` in `src/analytics/scoring.py` to persist `view_count`, `like_count`, and `comment_count`.

## Phase 5: AI-Native Story Packaging & Boilerplate Eradication
- [x] 5.1 Update `SeoOptimizerAgent.optimize()` in `src/agents/seo_optimizer.py` to accept full narrative script, synopsis, and channel voice context.
- [x] 5.2 Eradicate hardcoded string template description building (`generate_description`, `generate_shorts_metadata`) in `src/pipeline/stages/stage_11_metadata.py`.
- [x] 5.3 Bind AI-generated `selected_title`, `description`, `tags`, and `pinned_comment` directly into `PipelineContext`.

## Phase 6: CLI & Daemon 24h Sweep Integration
- [x] 6.1 Add `collect-links` action to `src/cli/handlers/analytics.py` and register in subparser.
- [x] 6.2 Integrate `collect_channel_links` into the automated 24h maintenance sweep in `src/daemon.py`.

## Phase 7: Verification & Integrity Audit
- [x] 7.1 Author unit tests for link collection in `tests/unit/test_analytics_link_collector.py`.
- [x] 7.2 Author unit tests for pinned comment lifecycle and failure marking in `tests/unit/test_pinned_comments.py`.
- [x] 7.3 Author unit tests for comment level classification and empirical scoring in `tests/unit/test_analytics_scoring.py`.
- [x] 7.4 Author unit tests for AI-native metadata packaging in `tests/unit/test_seo_optimizer.py` and `tests/unit/test_pipeline_metadata.py`.
- [x] 7.5 Run `./scripts/verify_integrity.sh` and ensure 100% test pass rate with zero regressions.
