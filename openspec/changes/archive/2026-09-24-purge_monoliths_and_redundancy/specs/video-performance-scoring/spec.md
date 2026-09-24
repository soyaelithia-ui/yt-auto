# Delta for Video Performance Scoring & Song Attribution

## RENAMED Requirements

### Requirement: Normalized Empirical Success Score Calculation -> Normalized Empirical Success Score Calculation Across Modular Architecture

(Reason: Reflect modularized scoring architecture)

## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Modular Scoring Data Contract and Granularity Enforcement
All inter-module communication between `models.py`, `heuristics.py`, `semantic.py`, and `scoring.py` MUST use strongly-typed contracts (`@dataclass(slots=True)` or Pydantic models). Each individual function across these modules MUST adhere to the ~100 executable line budget mandated by AGENTS.md Rule 8.1. Untyped dictionaries (`dict[str, Any]`) are strictly prohibited across modular scoring interfaces.

#### Scenario: Strongly-typed contract verification between scoring modules (Happy Path)
- **Given** an input text and lane configuration passed to `score_story()`
- **When** data flows between `heuristics.py`, `semantic.py`, and `scoring.py`
- **Then** all inputs and outputs MUST conform to explicit types (`StoryScoringVerdict`, `HeuristicScoreReport`, `SemanticScoreReport`)
- **And** static type checking with `mypy` or `py_compile` SHALL pass with zero violations.
