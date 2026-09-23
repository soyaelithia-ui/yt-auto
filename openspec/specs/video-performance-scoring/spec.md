# Specification: Video Performance Scoring & Song Attribution

## Purpose
The `video-performance-scoring` capability computes normalized empirical success scores ($0-100$) for published YouTube Shorts based on real-world audience metrics (views, like ratio, comment velocity, and estimated retention). It automatically attributes empirical performance to the underlying background music tracks and physical assets, providing sub-millisecond query capabilities for AI agents and the autonomous pipeline.

## Requirements

### Requirement 1: Normalized Empirical Success Score Calculation
The scoring engine MUST calculate a composite empirical success score bounded between $0.0$ and $100.0$ for any published video with available YouTube Data API statistics. The formula MUST weigh time-decayed view velocity, engagement rate ($(\text{likes} \cdot 10 + \text{comments} \cdot 25) / \max(\text{views}, 1)$), and audience retention rate without raising exceptions on zero-view or baseline conditions.

#### Scenario: High engagement short calculates high success score (Happy Path)
- **Given** a published video with 5,000 views, 300 likes, 40 comments, and an estimated retention rate of 85.0% after 48 hours
- **When** the empirical scoring engine computes the score
- **Then** the resulting success score MUST be $\ge 70.0$ and $\le 100.0$
- **And** the score MUST be persisted in `publications.actual_success_score` and the latest `video_analytics_snapshots` record.

#### Scenario: Zero-view fresh video computes baseline score without division by zero (Edge Case)
- **Given** a recently published video with 0 views, 0 likes, and 0 comments
- **When** the empirical scoring engine processes the metrics
- **Then** the engine MUST NOT raise a `ZeroDivisionError`
- **And** the calculated success score MUST be $0.0$.

### Requirement 2: Background Music and Asset Attribution
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

### Requirement 3: Microsecond Performance Indexing and Sub-Millisecond Lookups
The system MUST maintain SQLite B-tree indices on `publications(actual_success_score)` and `publications(video_sha256)` to support sub-millisecond retrieval of top-performing videos, bottom-performing candidates, and video hash verification.

#### Scenario: Sub-millisecond lookup of bottom-performing candidates for pruning (Happy Path)
- **Given** an indexed database containing 200 published video records
- **When** the pruner queries for videos with `actual_success_score < 25.0` ordered by score ascending with a limit of 10
- **Then** the query MUST execute in $< 5\text{ ms}$ using SQLite index scans
- **And** the returned records MUST be sorted in strictly ascending score order.

#### Scenario: Lookup by video SHA256 digest (Happy Path)
- **Given** a 64-character SHA256 hash of a rendered video file
- **When** `get_video_by_sha256()` is invoked
- **Then** the system MUST retrieve the corresponding `PublishedVideoRecord` in $< 2\text{ ms}$.
