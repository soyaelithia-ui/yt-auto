"""
Unit tests for Stage 01 claim lease local SQLite caching (external_post_cache).

Validates Milestone 1 (F02 / R6):
- Cache miss: calls fetch_reddit_stories, stores payload in SQLite external_post_cache with TTL.
- Cache hit: within 300s TTL, returns cached stories without invoking fetch_reddit_stories.
- Cache expiration: after 300s, invalidates expired entries and refreshes cache from external source.
- DB error tolerance: gracefully catches SQLite errors/corrupt data and falls back to direct fetch.
- Cache key granularity: ensures separate feeds and limits do not collide.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.core.domain import CanonicalChannel
from src.core.repository import QueueRepository, connect
import src.pipeline.stages.stage_01_lease as stage_01_module
from src.pipeline.stages.stage_01_lease import (
    _claim_or_enqueue_story,
    stage_01_claim_lease,
)


# ==============================================================================
# Test Fixtures & Helpers
# ==============================================================================

@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    """Create and initialize a temporary SQLite queue database."""
    db_path = tmp_path / "test_queue.db"
    repo = QueueRepository(db_path)
    repo.initialize()
    return db_path


@pytest.fixture
def mock_channel_settings() -> SimpleNamespace:
    """Mock channel settings object providing source_feed."""
    return SimpleNamespace(
        source_feed="nosleep",
        channel_name="horror",
    )


def _get_helper_functions():
    """Retrieve caching helper functions from stage_01_lease or fail if missing."""
    get_cached = getattr(stage_01_module, "_get_cached_external_stories", None)
    set_cached = getattr(stage_01_module, "_set_cached_external_stories", None)
    ttl_seconds = getattr(stage_01_module, "FEED_CACHE_TTL_SECONDS", 300.0)
    return get_cached, set_cached, ttl_seconds


# ==============================================================================
# Low-Level Unit Tests: _get_cached_external_stories & _set_cached_external_stories
# ==============================================================================

class TestStage01CacheUnit:
    """Unit tests verifying SQLite external_post_cache table operations."""

    def test_cache_miss_returns_none_on_empty_db(self, test_db: Path):
        """Cache probe returns None when external_post_cache is empty or table does not exist."""
        get_cached, _, _ = _get_helper_functions()
        if get_cached is None:
            pytest.fail("_get_cached_external_stories is not implemented in stage_01_lease")

        result = get_cached(str(test_db), feed="nosleep", limit=25)
        assert result is None

    def test_cache_set_and_hit_within_ttl(self, test_db: Path):
        """Stored stories are successfully retrieved from SQLite cache within TTL."""
        get_cached, set_cached, ttl = _get_helper_functions()
        if get_cached is None or set_cached is None:
            pytest.fail("Cache helper functions are not implemented in stage_01_lease")

        sample_stories = [
            {
                "id": "post_001",
                "title": "La Sombra en el Espejo",
                "content": "Había algo detrás de mí en el reflejo...",
                "url": "https://reddit.com/r/nosleep/comments/post_001",
                "upvote_ratio": 0.95,
                "num_comments": 42,
            },
            {
                "id": "post_002",
                "title": "El Pasillo Oscuro",
                "content": "Las luces nunca volvieron a encenderse.",
                "url": "https://reddit.com/r/nosleep/comments/post_002",
                "upvote_ratio": 0.88,
                "num_comments": 15,
            },
        ]

        # Store in cache
        set_cached(str(test_db), feed="nosleep", limit=25, stories=sample_stories, ttl_seconds=300.0)

        # Direct SQL verification of schema and row contents
        with connect(str(test_db), read_only=True) as conn:
            row = conn.execute(
                "SELECT cache_key, feed, payload_json, fetched_at, expires_at FROM external_post_cache WHERE cache_key = ?",
                ("nosleep:25",),
            ).fetchone()
            assert row is not None
            assert row["cache_key"] == "nosleep:25"
            assert row["feed"] == "nosleep"
            assert json.loads(row["payload_json"]) == sample_stories
            assert float(row["expires_at"]) > float(row["fetched_at"])

        # Cache HIT verification
        cached = get_cached(str(test_db), feed="nosleep", limit=25)
        assert cached is not None
        assert len(cached) == 2
        assert cached[0]["id"] == "post_001"
        assert cached[1]["id"] == "post_002"

    def test_cache_expiration_after_ttl(self, test_db: Path):
        """Expired cache entry returns None and is treated as a cache miss."""
        get_cached, set_cached, _ = _get_helper_functions()
        if get_cached is None or set_cached is None:
            pytest.fail("Cache helper functions are not implemented in stage_01_lease")

        sample_stories = [{"id": "exp_1", "title": "Expired", "content": "Old content", "url": "https://..."}]

        # Set with 1.0s TTL
        base_time = 1000000.0
        with patch("time.time", return_value=base_time):
            set_cached(str(test_db), feed="nosleep", limit=25, stories=sample_stories, ttl_seconds=1.0)

        # Check hit at base_time + 0.5s
        with patch("time.time", return_value=base_time + 0.5):
            assert get_cached(str(test_db), feed="nosleep", limit=25) is not None

        # Check miss at base_time + 1.5s (> 1.0s TTL)
        with patch("time.time", return_value=base_time + 1.5):
            assert get_cached(str(test_db), feed="nosleep", limit=25) is None

        # Check miss after 300s standard TTL
        with patch("time.time", return_value=base_time + 301.0):
            assert get_cached(str(test_db), feed="nosleep", limit=25) is None

    def test_cache_key_isolation_different_feeds_and_limits(self, test_db: Path):
        """Different feeds or limits maintain isolated cache keys without cross-contamination."""
        get_cached, set_cached, _ = _get_helper_functions()
        if get_cached is None or set_cached is None:
            pytest.fail("Cache helper functions are not implemented in stage_01_lease")

        stories_nosleep = [{"id": "ns_1", "title": "NoSleep", "content": "Dark"}]
        stories_drama = [{"id": "dr_1", "title": "Drama", "content": "Conflict"}]

        set_cached(str(test_db), feed="nosleep", limit=25, stories=stories_nosleep)
        set_cached(str(test_db), feed="aita", limit=25, stories=stories_drama)

        hit_nosleep = get_cached(str(test_db), feed="nosleep", limit=25)
        hit_drama = get_cached(str(test_db), feed="aita", limit=25)
        miss_other_limit = get_cached(str(test_db), feed="nosleep", limit=10)

        assert hit_nosleep is not None and hit_nosleep[0]["id"] == "ns_1"
        assert hit_drama is not None and hit_drama[0]["id"] == "dr_1"
        assert miss_other_limit is None

    def test_db_error_tolerance_corrupt_payload(self, test_db: Path):
        """Corrupted JSON payload in cache returns None gracefully without unhandled exception."""
        get_cached, _, _ = _get_helper_functions()
        if get_cached is None:
            pytest.fail("Cache helper functions are not implemented in stage_01_lease")

        # Manually inject corrupted JSON
        with connect(str(test_db)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS external_post_cache (
                    cache_key TEXT PRIMARY KEY,
                    feed TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    fetched_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO external_post_cache VALUES (?, ?, ?, ?, ?)",
                ("nosleep:25", "nosleep", "INVALID_NOT_JSON{{", time.time(), time.time() + 300.0),
            )
            conn.commit()

        # Should catch JSONDecodeError and return None
        result = get_cached(str(test_db), feed="nosleep", limit=25)
        assert result is None

    def test_db_error_tolerance_on_sqlite_failure(self):
        """Inaccessible or invalid database path returns None/does not crash."""
        get_cached, set_cached, _ = _get_helper_functions()
        if get_cached is None or set_cached is None:
            pytest.fail("Cache helper functions are not implemented in stage_01_lease")

        invalid_db_path = "/dev/null/cannot_exist/test.db"

        # Reading must not crash
        assert get_cached(invalid_db_path, feed="nosleep", limit=25) is None

        # Writing must not crash
        set_cached(invalid_db_path, feed="nosleep", limit=25, stories=[{"id": "1"}])


# ==============================================================================
# Pipeline-Level Integration Tests: _claim_or_enqueue_story with Cache
# ==============================================================================

class TestStage01CachePipelineIntegration:
    """Integration tests verifying Stage 1 claim/enqueue behavior with caching."""

    def test_pipeline_cache_miss_invokes_fetch_and_stores_cache(
        self, test_db: Path, mock_channel_settings: SimpleNamespace
    ):
        """On cold start (cache miss), fetch_reddit_stories is invoked and stores entries in SQLite."""
        repo = QueueRepository(test_db)
        mock_stories = [
            {
                "id": "wan_post_001",
                "title": "Historia de Terror Real",
                "content": "Esta es una historia completa y aterradora para el pipeline.",
                "url": "https://reddit.com/r/nosleep/comments/wan_001",
                "upvote_ratio": 0.95,
                "num_comments": 50,
            }
        ]

        with patch("src.pipeline.stages.stage_01_lease.is_test_environment", return_value=False), \
             patch("src.scraper.fetch_reddit_stories", return_value=mock_stories) as mock_fetch, \
             patch("src.core.scoring.filter_and_score_story") as mock_score, \
             patch("src.db.is_story_duplicate", return_value=False):

            # Configure mock scoring verdict to pass
            mock_score.return_value = SimpleNamespace(passed=True, db_rank_score=90, hybrid_score=0.9, rejection_summary=None)

            claimed = _claim_or_enqueue_story(
                repository=repo,
                channel_key=CanonicalChannel.HORROR,
                channel_name="horror",
                settings=mock_channel_settings,
                database=str(test_db),
                lane_id="horror-scp-shorts",
                requested_story_id="",
                story=None,
                directed=False,
                generate_only=False,
                owner="test_worker",
                lease_seconds=300,
            )

            # fetch_reddit_stories MUST be called on cache miss
            assert mock_fetch.call_count == 1
            assert claimed is not None
            assert claimed.id == "wan_post_001"

            # Cache table MUST contain the stored payload in SQLite
            with connect(str(test_db)) as conn:
                tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                assert "external_post_cache" in tables, "Table external_post_cache was not created in SQLite database"
                row = conn.execute(
                    "SELECT payload_json FROM external_post_cache WHERE cache_key = ?",
                    ("nosleep:25",)
                ).fetchone()
                assert row is not None, "external_post_cache was not populated on cache miss"
                assert "wan_post_001" in row["payload_json"]

    def test_pipeline_cache_hit_bypasses_fetch_reddit_stories(
        self, test_db: Path, mock_channel_settings: SimpleNamespace
    ):
        """When cache is populated within 300s TTL, fetch_reddit_stories is NOT invoked."""
        repo = QueueRepository(test_db)
        get_cached, set_cached, _ = _get_helper_functions()
        if set_cached is None:
            pytest.fail("_set_cached_external_stories is not implemented in stage_01_lease")

        cached_stories = [
            {
                "id": "cached_post_002",
                "title": "Historia Cacheada",
                "content": "Esta historia vino de la caché local de SQLite sin WAN.",
                "url": "https://reddit.com/r/nosleep/comments/cached_002",
                "upvote_ratio": 0.92,
                "num_comments": 30,
            }
        ]

        # Pre-populate cache with TTL = 300s
        set_cached(str(test_db), feed="nosleep", limit=25, stories=cached_stories, ttl_seconds=300.0)

        with patch("src.pipeline.stages.stage_01_lease.is_test_environment", return_value=False), \
             patch("src.scraper.fetch_reddit_stories") as mock_fetch, \
             patch("src.core.scoring.filter_and_score_story") as mock_score, \
             patch("src.db.is_story_duplicate", return_value=False):

            mock_score.return_value = SimpleNamespace(passed=True, db_rank_score=85, hybrid_score=0.85, rejection_summary=None)

            claimed = _claim_or_enqueue_story(
                repository=repo,
                channel_key=CanonicalChannel.HORROR,
                channel_name="horror",
                settings=mock_channel_settings,
                database=str(test_db),
                lane_id="horror-scp-shorts",
                requested_story_id="",
                story=None,
                directed=False,
                generate_only=False,
                owner="test_worker_2",
                lease_seconds=300,
            )

            # fetch_reddit_stories must NEVER be invoked on cache hit
            mock_fetch.assert_not_called()
            assert claimed is not None
            assert claimed.id == "cached_post_002"

    def test_pipeline_cache_expiration_triggers_fresh_fetch(
        self, test_db: Path, mock_channel_settings: SimpleNamespace
    ):
        """When cache entry expires (> 300s), stage 1 executes a fresh fetch and updates cache."""
        repo = QueueRepository(test_db)
        get_cached, set_cached, _ = _get_helper_functions()
        if set_cached is None:
            pytest.fail("_set_cached_external_stories is not implemented in stage_01_lease")

        stale_stories = [{"id": "stale_001", "title": "Stale", "content": "Old content", "url": "https://..."}]
        fresh_stories = [
            {
                "id": "fresh_001",
                "title": "Historia Fresca",
                "content": "Contenido nuevo tras expiración de caché de 300s.",
                "url": "https://reddit.com/r/nosleep/comments/fresh_001",
                "upvote_ratio": 0.99,
                "num_comments": 100,
            }
        ]

        base_time = 1700000000.0
        # Seed cache at base_time with 300s TTL (expires at base_time + 300s)
        with patch("time.time", return_value=base_time):
            set_cached(str(test_db), feed="nosleep", limit=25, stories=stale_stories, ttl_seconds=300.0)

        # Advance clock to base_time + 301s (expired)
        with patch("time.time", return_value=base_time + 301.0), \
             patch("src.pipeline.stages.stage_01_lease.is_test_environment", return_value=False), \
             patch("src.scraper.fetch_reddit_stories", return_value=fresh_stories) as mock_fetch, \
             patch("src.core.scoring.filter_and_score_story") as mock_score, \
             patch("src.db.is_story_duplicate", return_value=False):

            mock_score.return_value = SimpleNamespace(passed=True, db_rank_score=95, hybrid_score=0.95, rejection_summary=None)

            claimed = _claim_or_enqueue_story(
                repository=repo,
                channel_key=CanonicalChannel.HORROR,
                channel_name="horror",
                settings=mock_channel_settings,
                database=str(test_db),
                lane_id="horror-scp-shorts",
                requested_story_id="",
                story=None,
                directed=False,
                generate_only=False,
                owner="test_worker_refresh",
                lease_seconds=300,
            )

            # Fresh fetch must be triggered
            assert mock_fetch.call_count == 1
            assert claimed is not None
            assert claimed.id == "fresh_001"

    def test_pipeline_db_cache_error_falls_back_to_direct_fetch(
        self, test_db: Path, mock_channel_settings: SimpleNamespace
    ):
        """If reading SQLite cache raises an exception, the pipeline gracefully falls back to fetch."""
        repo = QueueRepository(test_db)
        direct_stories = [
            {
                "id": "direct_001",
                "title": "Fallback Direct Fetch",
                "content": "Fallback story fetched after simulated cache failure.",
                "url": "https://reddit.com/r/nosleep/comments/direct_001",
                "upvote_ratio": 0.90,
                "num_comments": 20,
            }
        ]

        with patch("src.pipeline.stages.stage_01_lease.is_test_environment", return_value=False), \
             patch("src.pipeline.stages.stage_01_lease._get_cached_external_stories", return_value=None, create=True), \
             patch("src.scraper.fetch_reddit_stories", return_value=direct_stories) as mock_fetch, \
             patch("src.core.scoring.filter_and_score_story") as mock_score, \
             patch("src.db.is_story_duplicate", return_value=False):

            mock_score.return_value = SimpleNamespace(passed=True, db_rank_score=80, hybrid_score=0.8, rejection_summary=None)

            claimed = _claim_or_enqueue_story(
                repository=repo,
                channel_key=CanonicalChannel.HORROR,
                channel_name="horror",
                settings=mock_channel_settings,
                database=str(test_db),
                lane_id="horror-scp-shorts",
                requested_story_id="",
                story=None,
                directed=False,
                generate_only=False,
                owner="test_worker_fallback",
                lease_seconds=300,
            )

            assert mock_fetch.call_count == 1
            assert claimed is not None
            assert claimed.id == "direct_001"
