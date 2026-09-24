# Proposal: Native Automated Link Collection, Comment Level Tracking, Empirical Scoring, and Intelligent AI Story Packaging

## Intent

The system currently relies on manual triggers to discover and sync published YouTube video links, does not persist granular comment metrics or comment failure statuses across publications, and generates video titles, descriptions, and tags through deterministic string concatenation and rigid branding templates rather than semantic AI intelligence.

This change natively integrates:
1. **Automated Link Collection**: An autonomous link collection engine that crawls 100% of channel uploads via YouTube Data API v3, extracts canonical watch URLs, short URLs (`youtu.be`), and Shorts URLs (`/shorts/`), and records them atomically into the local SQLite inventory.
2. **Comment Level Tracking**: Persistence and classification of real-world video comment metrics (`comment_count`, comment velocity, and discrete comment levels: `none`, `low`, `moderate`, `viral`) alongside view and like counts in `publications`.
3. **View & Engagement Success Scoring**: Automated empirical scoring directly weighted by views, like-to-view ratio, comment volume/velocity, and retention, updating `actual_success_score` in real time during link sweeps.
4. **Pinned Comment Execution & Failure Marking**: Native execution of AI-generated pinned comments (`commentThreads.insert`) with fail-safe error handling that flags failed attempts (`comment_status = 'failed'`, `comment_error`) without interrupting the publishing pipeline.
5. **100% Intelligent AI-Driven Packaging**: Complete eradication of rigid template-based string concatenation from title through description (`ctx.branding.generate_description`, `_deterministic_seo`), delegating the entire title, description, tags, hashtags, and discussion-sparking pinned comment generation to the AI optimizer using the complete narrative script context.

## Scope

### In Scope
- **Automated Native Link Collector (`src/analytics/link_collector.py` & `src/core/inventory.py`)**:
  - Automatically crawls 100% of uploaded video links per channel without pagination truncation.
  - Generates canonical watch URLs, short URLs (`https://youtu.be/<id>`), and Shorts URLs (`https://www.youtube.com/shorts/<id>`).
  - Idempotent upsert into `publications` and `stories` tables.
- **Comment Metrics & Classification (`src/analytics/scoring.py`)**:
  - Classifies comment levels into discrete tiers (`none`, `low`, `moderate`, `viral`) based on velocity and ratio relative to views.
  - Updates `publications.comment_count`, `publications.view_count`, `publications.like_count`, and `publications.actual_success_score`.
- **Pinned Comment Dispatch & Failure Marking (`src/youtube/comments.py` & `src/pipeline/stages/stage_13_publish.py`)**:
  - Dispatches AI-generated pinned comments to YouTube via OAuth / API.
  - Catches API errors (e.g. comments disabled on video, quota, permission errors) gracefully and marks `comment_status = 'failed'` and `comment_error = <reason>`.
- **Database Schema Migration 008 (`src/core/repository/migrations.py`)**:
  - Adds `comment_count`, `view_count`, `like_count`, `comment_status`, `comment_error`, and `pinned_comment` to `publications`.
  - B-tree indexing on `publications(comment_status)` and `publications(comment_count)`.
- **Intelligent AI Packaging Elimination of Boilerplate (`src/agents/seo_optimizer.py` & `src/pipeline/stages/stage_11_metadata.py`)**:
  - Purges rigid robotic description templates (`generate_description`, `generate_shorts_metadata`).
  - SEO Optimizer Agent receives the full story narrative, synopsis, and lane tone.
  - AI generates bespoke Spanish titles, engaging narrative descriptions with natural CTAs, tailored tags, and dilemma-driven pinned comments.
- **Daemon & CLI Integration (`src/daemon.py` & `src/cli/handlers/analytics.py`)**:
  - Adds `main.py analytics collect-links` CLI command.
  - Integrates automated link collection and comment scoring into the daemon 24h maintenance sweep.

### Out of Scope
- Interactive terminal prompts (strictly prohibited by AGENTS.md).
- Third-party browser scraping or Playwright for comments (Zero-Browser Policy).
- Deleting videos with failed comments (failed comments are marked for observability and retry).

## Capabilities

### New Capabilities
- `automatic-link-collection`: Native multi-channel link discovery, URL normalization, and inventory cataloging.
- `pinned-comment-lifecycle`: Autonomous pinned comment dispatch, pin enforcement, and failed comment state tracking.

### Modified Capabilities
- `video-performance-scoring`: Extends scoring formulas with discrete comment levels and direct view-based weightings.
- `ai-native-story-packaging`: Replaces deterministic branding templates with full AI story-informed metadata generation.

## Approach

1. **Link Collector Engine**:
   - `src/analytics/link_collector.py` defines `collect_channel_links(channel, max_items=0)` paging through YouTube Data API `playlistItems.list` for the channel's uploads playlist.
   - For every video, extracts video ID, builds URLs, fetches statistics (`viewCount`, `likeCount`, `commentCount`), and upserts into `publications`.
2. **Comment Status & Failure Marking**:
   - In `src/youtube/comments.py`, implement `post_pinned_comment(youtube_service, video_id, text)`.
   - In `stage_13_publish.py`, attempt comment posting. If comments are disabled on the video or quota limits trigger, store `comment_status="failed"` and record `comment_error`. If successful, store `comment_status="posted"`.
3. **AI Metadata Packaging**:
   - Update `SeoOptimizerAgent.optimize()` to accept `script_text`, `synopsis`, and `channel_tone`.
   - Update `stage_11_metadata.py` to supply full story context to `seo_opt.optimize()` and use the AI's generated description and title directly, bypassing template string concatenation.
4. **Database Migration**:
   - Define `MIGRATION_008` in `src/core/repository/migrations.py` adding columns to `publications`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/analytics/link_collector.py` | New | Autonomous YouTube uploads link harvester and inventory synchronizer. |
| `src/youtube/comments.py` | New | YouTube comment posting and error classification service. |
| `src/analytics/scoring.py` | Modified | Comment level calculation and view-based scoring refinements. |
| `src/core/repository/migrations.py` | Modified | Migration 008: comment columns and indices on `publications`. |
| `src/core/inventory.py` | Modified | `PublishedVideoRecord` updated with comment metrics and failure states. |
| `src/pipeline/stages/stage_11_metadata.py` | Modified | Eradicate template generation; 100% AI story metadata synthesis. |
| `src/pipeline/stages/stage_13_publish.py` | Modified | Autonomous pinned comment post and failure marking. |
| `src/agents/seo_optimizer.py` | Modified | Rich narrative context ingestion and AI metadata generation. |
| `src/cli/handlers/analytics.py` | Modified | Add `collect-links` subcommand. |
| `src/daemon.py` | Modified | Wire link collection into the periodic maintenance cycle. |
