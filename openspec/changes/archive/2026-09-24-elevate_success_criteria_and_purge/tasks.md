# Tasks: Elevate Success Criteria, Eliminate Viral Tier, and Implement Diagnostic Pre-Purge Marking

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~250-300 lines |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR (criteria elevation, diagnostic pre-purge, zero-API upload) |
| Delivery strategy | single-pr |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No  
Chained PRs recommended: No  
Chain strategy: feature-branch-chain  
400-line budget risk: Low  

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Scoring comment classification (`none`, `low`, `high`) & elevated thresholds | PR 1 | `.venv/bin/pytest tests/unit/test_analytics_scoring.py tests/unit/test_analytics_link_collector.py -v` | Unit tests | `src/analytics/scoring.py` |
| 2 | Diagnostic failure classifier and pre-purge marking in `pruner.py` | PR 1 | `.venv/bin/pytest tests/unit/test_pruner_diagnostics.py tests/unit/test_pruner_autonomous.py -v` | Unit tests | `src/analytics/pruner.py` |
| 3 | Zero-API upload policy enforcement in `src/youtube/uploader/` | PR 1 | `.venv/bin/pytest tests/unit/test_uploader_session.py -v` | Unit tests | `src/youtube/uploader/` |
| 4 | Audit, mark, and purge live failed videos via YouTube Data API | PR 1 | `./scripts/verify_integrity.sh` | Live / Script | `data/shorts_queue.db` |

---

## Phase 1: Comment Classification & Elevated Scoring Thresholds (TDD)

- [x] 1.1 (RED Test): Update tests in `tests/unit/test_analytics_scoring.py` asserting that `classify_comment_level(35, 2000)` returns `"high"` instead of `"viral"`, and remove `"viral"` assertions in `tests/unit/test_analytics_link_collector.py`.
- [x] 1.2 (GREEN): Update `classify_comment_level` in `src/analytics/scoring.py` to eliminate `"viral"`, categorizing engagement into `"none"`, `"low"`, and `"high"`.
- [x] 1.3: Verify unit tests pass: `.venv/bin/pytest tests/unit/test_analytics_scoring.py tests/unit/test_analytics_link_collector.py -v`.

## Phase 2: Diagnostic Classifier and Pre-Purge Marking (TDD)

- [x] 2.1 (RED Test): Create unit tests in `tests/unit/test_pruner_diagnostics.py` validating `classify_video_failure()` for `ZERO_ENGAGEMENT_STALE`, `CROSS_CONTAMINATED_TITLE`, `EMPTY_TITLE_ARTIFACT`, and `UNDERPERFORMING_SCORE`.
- [x] 2.2 (GREEN): Implement `classify_video_failure()`, update default `min_score` to 40.0, and add `mark_candidates_for_purge()` in `src/analytics/pruner.py`.
- [x] 2.3 (GREEN): Ensure `execute_autonomous_prune()` and batch purge helper can process marked candidates and transition state from `MARKED_FOR_PURGE` to `PURGED`.
- [x] 2.4: Add `MARKED_FOR_PURGE` and `PURGED` to `JobStatus` in `src/core/domain.py`.
- [x] 2.5: Verify pruner tests pass: `.venv/bin/pytest tests/unit/test_pruner_diagnostics.py tests/unit/test_pruner_autonomous.py -v`.

## Phase 3: Zero-API Upload Enforcement

- [x] 3.1: Verify and configure `src/youtube/uploader/__init__.py` to disallow YouTube API video binary upload fallback, enforcing session cookies.
- [x] 3.2: Verify with tests that mock uploads and production uploads follow the cookie/session path.

## Phase 4: Diagnostic Audit, Marking, and Purge Execution

- [x] 4.1: Run a diagnostic audit on `data/shorts_queue.db` to identify failed videos (< 40.0 score, cross-contaminated titles, zero views > 48h).
- [x] 4.2: Mark candidate batch as `MARKED_FOR_PURGE` with explicit failure codes.
- [x] 4.3: Execute batch deletion of the marked batch via YouTube Data API and record status as `PURGED`.
- [x] 4.4: Verify database consistency and inventory summary.

## Phase 5: Anti-Regression Verification and Integrity Gate

- [x] 5.1: Run `./scripts/verify_integrity.sh`.
- [x] 5.2: Update and restart Docker container with updated image/code.
