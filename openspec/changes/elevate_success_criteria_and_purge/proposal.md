# Proposal: Elevate Video Success Criteria, Eliminate Viral Tier, and Implement Diagnostic Pre-Purge Marking

## Intent

The channel analytics and publishing systems currently suffer from three architectural and operational misalignments:
1. **Redundant Comment Classification**: The `classify_comment_level` engine includes a `"viral"` tier alongside `"moderate"` and `"low"`. In production, any video reaching high engagement is already untouchable (`high`/`alto`), rendering a separate `"viral"` classification superfluous and misleading for decision gates.
2. **Permissive Underperformance Thresholds**: The survival floor for video performance is currently set at `25.0/100`, tolerating hundreds of videos with zero likes, minimal views (< 50), and stale presence that damage channel algorithmic trust. The survival threshold must be elevated to `40.0/100`, establishing a clear three-tier taxonomy: Underperforming/Purge Candidate (< 40.0), Monitoring/Stable (40.0 - 74.9), and High/Untouchable (>= 75.0).
3. **Blind Deletion vs. Diagnostic Pre-Purge Marking**: The previous pruning logic deleted candidates blindly without persisting why a video failed or enabling manual audit before deletion. Deletion must follow a two-phase protocol: diagnose root cause, mark in database (`MARKED_FOR_PURGE` with explicit failure codes), and execute paced batch deletion via YouTube Data API (`videos.delete`).
4. **Inviolable Upload Channel Segregation**: Production video uploads MUST strictly and exclusively use session cookies (via Playwright / InnerTube in `src/youtube/`). YouTube Data API v3 MUST NEVER be used for uploading videos, reserving API quota solely for metrics observation and atomic video deletion.

## Scope

### In Scope
- **Scoring & Classification Refinement (`src/analytics/scoring.py`, `src/analytics/link_collector.py`)**:
  - Remove `"viral"` from comment level classification.
  - Establish discrete levels: `"none"`, `"low"`, and `"high"`.
  - Elevate empirical score thresholds: Underperforming (< 40.0), Stable (40.0 - 74.9), High (>= 75.0).
- **Diagnostic Failure Classifier & Pre-Purge Marker (`src/analytics/pruner.py`)**:
  - Implement deterministic failure root cause diagnostics: `ZERO_ENGAGEMENT_STALE`, `CROSS_CONTAMINATED_TITLE`, `EMPTY_TITLE_ARTIFACT`, `UNDERPERFORMING_SCORE`.
  - Implement pre-purge database marking (`stories.status = 'MARKED_FOR_PURGE'`, `stories.failure_code = <reason>`).
  - Update default pruning score floor from 25.0 to 40.0.
  - Implement batch execution of marked candidates via YouTube Data API `videos().delete()`, followed by transition to `stories.status = 'PURGED'`.
- **Upload Segregation Hardening (`src/youtube/uploader/`)**:
  - Enforce session cookies as the sole production upload pathway.
  - Prohibit YouTube Data API video uploads to preserve quota for analytics and purging.
- **Database Schema & Status Alignment (`src/core/domain.py`, `src/core/repository/`)**:
  - Recognize `JobStatus.MARKED_FOR_PURGE` or `StoryStatus.MARKED_FOR_PURGE` and `PURGED`.
  - Add or verify `failure_code` on `stories` for recording diagnostic reasons.

### Out of Scope
- Modifying YouTube Data API read endpoints (`videos.list`, `channels.list`).
- Rewriting the media rendering or composition pipelines.
- Deleting physical background loop assets from disk.

## Capabilities

### Modified Capabilities
- `video-performance-scoring`: Eradicate `"viral"` comment classification tier, reclassify to `"none"`, `"low"`, `"high"`, and elevate underperformance threshold to 40.0 and high performance to >= 75.0.
- `channel-purge-control`: Add diagnostic root-cause classification, two-phase pre-purge marking (`MARKED_FOR_PURGE`), and elevate evaluation floor to 40.0.
- `youtube-publishing`: Enforce zero-API upload policy; restrict YouTube Data API v3 strictly to telemetry and atomic deletion while uploads remain 100% cookie-driven.

## Approach

1. **Scoring Engine Update**:
   - Refactor `classify_comment_level` in `src/analytics/scoring.py` to return `"none"`, `"low"`, or `"high"`.
   - Update tests in `tests/unit/test_analytics_scoring.py` and `tests/unit/test_analytics_link_collector.py`.
2. **Diagnostic Classifier and Marking in Pruner**:
   - Add `classify_video_failure(video_data)` in `src/analytics/pruner.py`.
   - Add `mark_underperforming_videos(channel, db_path, min_score=40.0, grace_hours=24.0)` to set `stories.status = 'MARKED_FOR_PURGE'` with diagnostic failure codes.
   - Add `purge_marked_videos(channel, db_path, youtube_service)` to delete marked videos via YouTube API and transition to `stories.status = 'PURGED'`.
3. **Upload Policy Guardrail**:
   - Ensure `src/youtube/uploader/` routes all video uploads through cookie session mechanisms, preventing any accidental consumption of API upload quota.
4. **Live Execution & Integrity Gate**:
   - Run audit and diagnostic marking on live database `data/shorts_queue.db`.
   - Purge the marked batch using YouTube Data API.
   - Run `./scripts/verify_integrity.sh`.
