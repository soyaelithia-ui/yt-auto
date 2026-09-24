# Specification: Video Performance Scoring & Song Attribution

## Purpose
The `video-performance-scoring` capability computes normalized empirical success scores ($0-100$) for published YouTube Shorts based on real-world audience metrics (views, like ratio, comment velocity, and estimated retention) and discrete comment level classification (`none`, `low`, `moderate`, `viral`). It automatically attributes empirical performance to the underlying background music tracks and physical assets, providing sub-millisecond query capabilities for AI agents and the autonomous pipeline.

## Requirements

### Requirement: Normalized Empirical Success Score Calculation Across Modular Architecture
(Previously: Executed within monolithic `src/core/scoring.py` coupling regex heuristics, LLM prompts, and SQLite persistence)

The scoring subsystem MUST modularize its implementation across decoupled, single-responsibility modules:
- `src/core/scoring/models.py`: Strongly-typed dataclasses (`HeuristicScoreReport`, `SemanticScoreReport`, `StoryScoringVerdict`).
- `src/core/scoring/heuristics.py`: Fast deterministic heuristics, opening hook strength detection, and spoken duration estimations.
- `src/core/scoring/semantic.py`: LLM semantic viral evaluation, JSON validation, and deterministic fallback evaluation.
- `src/core/scoring.py` (or package facade): High-level scoring coordinator orchestrating hybrid score computation and story filtering.

Across this modular architecture, the scoring engine MUST calculate composite empirical success scores strictly bounded between $0.0$ and $100.0$ for any published video with available YouTube Data API statistics. The composite formula MUST weigh time-decayed view velocity, engagement rate ($(\text{likes} \cdot 10 + \text{comments} \cdot 25) / \max(\text{views}, 1)$), and audience retention rate without raising exceptions on zero-view, missing metrics, or baseline conditions.

#### Scenario: High engagement short calculates high success score across modular pipeline (Happy Path)
- **Given** a published video with 5,000 views, 300 likes, 40 comments, and an estimated retention rate of 85.0% after 48 hours
- **When** the modular scoring coordinator computes the empirical score
- **Then** the resulting success score MUST be $\ge 70.0$ and $\le 100.0$
- **And** the score MUST be persisted in `publications.actual_success_score` and the latest `video_analytics_snapshots` record.

#### Scenario: Zero-view fresh video computes baseline score without division by zero (Edge Case)
- **Given** a recently published video with 0 views, 0 likes, and 0 comments
- **When** the modular heuristics and empirical engine process the metrics
- **Then** the engine MUST NOT raise a `ZeroDivisionError`
- **And** the calculated success score MUST be $0.0$.

#### Scenario: Fallback to deterministic heuristics on semantic LLM timeout (Edge Case)
- **Given** a story evaluation where the LLM provider times out or returns malformed JSON
- **When** `semantic.py` processes the response
- **Then** it MUST fall back deterministically to rule-based heuristics
- **And** the returned `StoryScoringVerdict` MUST contain a valid score in $[0.0, 100.0]$ with `semantic_evaluated=False`.

### Requirement: Background Music and Asset Attribution
The scoring subsystem MUST extract the background audio track identifier (`used_resources.music`) from the publication record and attribute the computed video success score to that track. The subsystem MUST provide aggregated performance statistics (total uses, average score, top-performing video ID) for each music track across the channel catalog.

#### Scenario: Song attribution tracks performance across multiple videos (Happy Path)
- **Given** a music track `"assets/audio/music/dark_ambient_01.mp3"` used in 3 published videos with scores 60.0, 80.0, and 70.0
- **When** the music attribution aggregator is queried for the channel
- **Then** the average success score for `"dark_ambient_01.mp3"` MUST be $70.0$
- **And** the usage count MUST be reported as 3.

#### Scenario: Video record without music track metadata is handled gracefully (Edge Case)
- **Given** an older publication record where `used_resources` is null or does not contain a `"music"` key
- **When** attribution aggregation runs
- **Then** the aggregator MUST classify the track as `"unknown"` or skip track attribution without throwing errors.

### Requirement: Microsecond Performance Indexing and Sub-Millisecond Lookups
(Previously: Maintained SQLite indices on `publications` with $< 5\text{ ms}$ query latency)

The decomposition of `src/core/scoring.py` and separation of catalog asset sync from core repository operations MUST NOT degrade SQLite database access performance or alter B-tree schema indices. The system MUST maintain SQLite B-tree indices on `publications(actual_success_score)` and `publications(video_sha256)` to support sub-millisecond retrieval of top-performing videos, bottom-performing pruning candidates, and video hash verification.

#### Scenario: Sub-millisecond lookup of bottom-performing candidates for pruning (Happy Path)
- **Given** an indexed database containing published video records
- **When** the pruner queries for videos with `actual_success_score < 25.0` ordered by score ascending with a limit of 10
- **Then** the query MUST execute in $< 5\text{ ms}$ using SQLite index scans
- **And** the returned records MUST be sorted in strictly ascending score order.

#### Scenario: Sub-millisecond lookup by video SHA256 digest (Happy Path)
- **Given** a 64-character SHA256 hash of a rendered video file
- **When** `get_video_by_sha256()` is invoked
- **Then** the system MUST retrieve the corresponding `PublishedVideoRecord` in $< 2\text{ ms}$.

### Requirement: Modular Scoring Data Contract and Granularity Enforcement
All inter-module communication between `models.py`, `heuristics.py`, `semantic.py`, and `scoring.py` MUST use strongly-typed contracts (`@dataclass(slots=True)` or Pydantic models). Each individual function across these modules MUST adhere to the ~100 executable line budget mandated by AGENTS.md Rule 8.1. Untyped dictionaries (`dict[str, Any]`) are strictly prohibited across modular scoring interfaces.

#### Scenario: Strongly-typed contract verification between scoring modules (Happy Path)
- **Given** an input text and lane configuration passed to `score_story()`
- **When** data flows between `heuristics.py`, `semantic.py`, and `scoring.py`
- **Then** all inputs and outputs MUST conform to explicit types (`StoryScoringVerdict`, `HeuristicScoreReport`, `SemanticScoreReport`)
- **And** static type checking with `mypy` or `py_compile` SHALL pass with zero violations.

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

### Requirement: Empirical Scoring with View Weighting
The success score formula MUST compute a normalized score ($0.0 - 100.0$) strongly factoring in views:
- $40\%$ Views / Velocity (log-scale normalized to 10,000 views)
- $35\%$ Engagement Rate ($(\text{likes} \cdot 10 + \text{comments} \cdot 25) / \max(1, \text{views})$)
- $25\%$ Audience Retention Rate ($0.0 - 100.0\%$)

#### Scenario: High views with active comments produces top score
- **Given** a video with 12,000 views, 800 likes, and 90 comments
- **When** `calculate_empirical_score` is invoked
- **Then** the returned score MUST be $\ge 80.0$ and $\le 100.0$.

