# Specification: Video Performance Scoring & Comment Level Categorization

## Purpose
Extends the `video-performance-scoring` capability with discrete comment level evaluation (`none`, `low`, `moderate`, `viral`), view-based empirical success scoring, and automated persistence into SQLite `publications`.

## Requirements

### Requirement 1: Comment Level Classification
The scoring engine MUST evaluate the raw comment count relative to video views and age, categorizing the engagement into discrete levels:
- `none`: 0 comments.
- `low`: 1 to 5 comments, or engagement ratio $< 0.5\%$.
- `moderate`: 6 to 30 comments with engagement ratio between $0.5\%$ and $3.0\%$.
- `viral`: $> 30$ comments or engagement ratio $> 3.0\%$.

#### Scenario: Video with 45 comments is classified as viral (Happy Path)
- **Given** a published video with 1,200 views and 45 comments
- **When** `classify_comment_level(comments=45, views=1200)` is evaluated
- **Then** the resulting comment level MUST be `"viral"`.

#### Scenario: Zero comment video is classified as none (Edge Case)
- **Given** a published video with 100 views and 0 comments
- **When** `classify_comment_level(comments=0, views=100)` is evaluated
- **Then** the resulting comment level MUST be `"none"`.

### Requirement 2: Empirical Scoring with View Weighting
The success score formula MUST compute a normalized score ($0.0 - 100.0$) strongly factoring in views:
- $40\%$ Views / Velocity (log-scale normalized to 10,000 views)
- $35\%$ Engagement Rate ($(\text{likes} \cdot 10 + \text{comments} \cdot 25) / \max(1, \text{views})$)
- $25\%$ Audience Retention Rate ($0.0 - 100.0\%$)

#### Scenario: High views with active comments produces top score
- **Given** a video with 12,000 views, 800 likes, and 90 comments
- **When** `calculate_empirical_score` is invoked
- **Then** the returned score MUST be $\ge 80.0$ and $\le 100.0$.
