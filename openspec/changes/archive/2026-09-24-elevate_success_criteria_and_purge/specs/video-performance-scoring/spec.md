# Specification: Video Performance Scoring (Delta)

## MODIFIED Requirements

### Requirement: Comment Level Classification
The scoring engine MUST evaluate raw comment count relative to video views and age, categorizing engagement strictly into three discrete operational levels (`none`, `low`, `high`). The redundant `"viral"` tier is eliminated:
- `none`: 0 comments.
- `low`: 1 to 5 comments, or engagement ratio $< 0.5\%$.
- `high`: $\ge 6$ comments and (views == 0 or engagement ratio $\ge 0.5\%$).

#### Scenario: Video with 45 comments is classified as high (Happy Path)
- **Given** a published video with 1,200 views and 45 comments
- **When** `classify_comment_level(comments=45, views=1200)` is evaluated
- **Then** the resulting comment level MUST be `"high"`.

#### Scenario: Zero comment video is classified as none (Edge Case)
- **Given** a published video with 100 views and 0 comments
- **When** `classify_comment_level(comments=0, views=100)` is evaluated
- **Then** the resulting comment level MUST be `"none"`.

#### Scenario: Low comment video is classified as low (Edge Case)
- **Given** a published video with 2 comments and 1000 views
- **When** `classify_comment_level(comments=2, views=1000)` is evaluated
- **Then** the resulting comment level MUST be `"low"`.

### Requirement: Normalized Empirical Success Score Thresholds
The scoring engine and downstream pruning subsystems MUST apply elevated operational performance thresholds:
- Underperforming / Purge Candidate Floor: $\text{score} < 40.0$
- Monitoring / Stable Range: $40.0 \le \text{score} < 75.0$
- High / Untouchable Range: $\text{score} \ge 75.0$

#### Scenario: Underperforming video below 40.0 is flagged as purge candidate
- **Given** a published video with 15 views, 0 likes, and computed empirical score of 12.0
- **When** evaluated against the operational performance thresholds
- **Then** the video MUST be classified as an underperforming purge candidate.

#### Scenario: Video with score 75.0 or above is classified as high and untouchable
- **Given** a published video with 10,000 views, 500 likes, and empirical score of 78.5
- **When** evaluated against the operational performance thresholds
- **Then** the video MUST be classified as high performance and protected from automated deletion.
