# Design: Elevate Success Criteria, Eliminate Viral Tier, and Implement Diagnostic Pre-Purge Marking

## Architectural Overview

This design addresses three core subsystems:
1. **Comment Classification & Empirical Scoring** (`src/analytics/scoring.py`):
   - Simplifies comment categorization into a 3-tier model: `none`, `low`, and `high`.
   - Realigns operational performance score bands:
     - Underperforming: $[0.0, 40.0)$
     - Stable: $[40.0, 75.0)$
     - High / Untouchable: $[75.0, 100.0]$
2. **Diagnostic Classifier and Pre-Purge State Machine** (`src/analytics/pruner.py`):
   - Evaluates videos that meet age grace periods ($\ge 24\text{h}$) and fall below the elevated floor ($< 40.0$).
   - Determines deterministic failure codes:
     - `ZERO_ENGAGEMENT_STALE`: $\ge 48\text{h}$, $< 50$ views, $0$ likes.
     - `CROSS_CONTAMINATED_TITLE`: Title carries cross-channel keywords (e.g. "Soy el malo" on horror channel).
     - `EMPTY_TITLE_ARTIFACT`: Generic title ("test", "video", or empty).
     - `UNDERPERFORMING_SCORE`: Score $< 40.0$ after $\ge 24\text{h}$.
   - Two-phase execution:
     - Phase A: Audit & Mark (`stories.status = 'MARKED_FOR_PURGE'`, `stories.failure_code = <code_str>`).
     - Phase B: Batch Deletion via YouTube Data API (`videos.delete`), transitioning to `stories.status = 'PURGED'`.
3. **Inviolable Upload Channel Restriction** (`src/youtube/uploader/`):
   - Restricts `upload_video()` so that production uploads always execute via session cookies (InnerTube/Playwright).
   - Completely removes any default fallback to YouTube API upload (`videos.insert`), preserving API quota solely for reading analytics and atomic deletions.

## Detailed Component Design

### 1. Comment Classification Refinement

```python
def classify_comment_level(comments: int, views: int = 0) -> str:
    """
    Classifies audience comment engagement:
    - 'none': 0 comments
    - 'low': 1-5 comments or engagement ratio < 0.5%
    - 'high': >= 6 comments and (views == 0 or ratio >= 0.5%)
    """
    c = max(0, int(comments))
    v = max(0, int(views))
    if c == 0:
        return "none"
    ratio = (c / max(1.0, float(v))) * 100.0 if v > 0 else 0.0
    if c >= 6 and (v == 0 or ratio >= 0.5):
        return "high"
    return "low"
```

### 2. Diagnostic Root Cause Classifier

```python
def classify_video_failure(
    title: str,
    channel: str,
    views: int,
    likes: int,
    age_hours: float,
    score: float,
) -> str:
    """Determines the specific failure code for an underperforming video."""
    t_lower = title.lower().strip()
    if not t_lower or t_lower in ("test", "video", "untitled", "video sin título"):
        return "EMPTY_TITLE_ARTIFACT"
    if channel == "horror" and ("soy el malo" in t_lower or "aita" in t_lower):
        return "CROSS_CONTAMINATED_TITLE"
    if channel == "drama" and ("relato de terror" in t_lower or "scp" in t_lower):
        return "CROSS_CONTAMINATED_TITLE"
    if age_hours >= 48.0 and views < 50 and likes == 0:
        return "ZERO_ENGAGEMENT_STALE"
    if score < 40.0:
        return "UNDERPERFORMING_SCORE"
    return "UNKNOWN_FAILURE"
```

### 3. Pre-Purge Marking and Batch Deletion

The state transitions in SQLite:
```
PUBLISHED -> MARKED_FOR_PURGE (with failure_code) -> PURGED (post-YouTube API delete)
```

In `src/core/domain.py`:
`JobStatus.MARKED_FOR_PURGE = "MARKED_FOR_PURGE"`
`JobStatus.PURGED = "PURGED"`

### 4. Zero-API Upload Enforcement

In `src/youtube/uploader/__init__.py`:
- Video binary uploads MUST only execute through session cookies (`_perform_playwright_fallback_flow` or InnerTube).
- Disallow fallback to `upload_video_via_api()`. If cookies fail or are missing, report `WAITING_YOUTUBE_LIMIT` or `AUTHENTICATION_ERROR` rather than attempting `videos().insert()`.
