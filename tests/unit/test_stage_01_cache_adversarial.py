"""
Adversarial test harness and stress suite for Requirement R6:
Stage 1 Claim Lease Local SQLite Cache (external_post_cache).

Validates:
1. Cache Expiration & Invalidation:
   - Exact boundary precision (t < 300s hit, t >= 300s miss).
   - Dynamic TTL parameters and instant expiration on t >= ttl.
   - Invalidation and automatic refetching with cache replacement.
   - Cache key and feed isolation under asymmetric expiry.
2. Database Corruption & Concurrency:
   - Malformed JSON syntax (truncated, binary garbage, syntax errors).
   - Semantically corrupt JSON payloads (integers, strings, dicts, lists of non-dicts).
   - Schema tampering (missing columns, altered table structures).
   - DB concurrency locks (exclusive write locks, busy timeouts).
   - Read-only database filesystem states.
   - Multithreaded hammering (concurrent reads, writes, and invalidations).
3. Queue Lease Invariant Integrity:
   - Cached candidates never bypass or corrupt story claiming.
   - Deduplication (is_story_duplicate) suppression guarantees across repeated cached runs.
   - Multi-worker lease acquisition and owner isolation.
   - Lease expiry reaper (recover_expired_leases) interaction with cached candidates.
   - Completed/published story protection against re-enqueuing.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.core.contracts.story import StoryRecord
from src.core.domain import CanonicalChannel, JobStatus
from src.core.profiling import PipelineProfiler
from src.core.repository import QueueRepository, connect
import src.pipeline.stages.stage_01_lease as stage_01_module
from src.pipeline.stages.stage_01_lease import (
    FEED_CACHE_TTL_SECONDS,
    _claim_or_enqueue_story,
    _get_cached_external_stories,
    _set_cached_external_stories,
    stage_01_claim_lease,
)


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def test_db_path(tmp_path: Path) -> str:
    """Create and initialize a temporary SQLite database for testing."""
    db_file = tmp_path / "adversarial_queue.db"
    repo = QueueRepository(str(db_file))
    repo.initialize()
    return str(db_file)


@pytest.fixture
def mock_channel_settings() -> SimpleNamespace:
    return SimpleNamespace(
        source_feed="nosleep",
        channel_name="moku",
    )


# ==============================================================================
# 1. Cache Expiration & Invalidation Stress Tests
# ==============================================================================

class TestCacheExpirationAndInvalidation:
    """Adversarial stress-testing of TTL expiration and cache invalidation mechanics."""

    def test_exact_ttl_boundary_precision(self, test_db_path: str):
        """Verify exact microsecond-level TTL boundary behavior (hit at t < 300, miss at t >= 300)."""
        stories = [{"id": "post_ttl_1", "title": "Boundary Test", "content": "Content"}]
        t_base = 1000.0
        ttl = 300.0  # expires at exactly 1300.0

        with patch("time.time", return_value=t_base):
            _set_cached_external_stories(test_db_path, "nosleep", 25, stories, ttl_seconds=ttl)

        # Probe points before boundary: ALL MUST HIT
        for t_offset in [0.0, 1.0, 150.0, 250.0, 299.0, 299.9, 299.999]:
            with patch("time.time", return_value=t_base + t_offset):
                cached = _get_cached_external_stories(test_db_path, "nosleep", 25, ttl_seconds=ttl)
                assert cached is not None, f"Expected cache HIT at t={t_base + t_offset} (offset {t_offset}s < {ttl}s)"
                assert cached[0]["id"] == "post_ttl_1"

        # Probe points at and after boundary: ALL MUST MISS (t >= 300.0)
        for t_offset in [300.0, 300.001, 300.1, 301.0, 500.0, 1000.0]:
            with patch("time.time", return_value=t_base + t_offset):
                cached = _get_cached_external_stories(test_db_path, "nosleep", 25, ttl_seconds=ttl)
                assert cached is None, f"Expected cache MISS at t={t_base + t_offset} (offset {t_offset}s >= {ttl}s)"

    def test_custom_ttl_parameter_honored(self, test_db_path: str):
        """Verify that custom ttl_seconds (e.g. 10s, 60s) is strictly honored."""
        stories = [{"id": "custom_ttl", "title": "Short TTL", "content": "Short"}]
        t_base = 2000.0
        custom_ttl = 45.0

        with patch("time.time", return_value=t_base):
            _set_cached_external_stories(test_db_path, "nosleep", 25, stories, ttl_seconds=custom_ttl)

        # Hit at 44.9s
        with patch("time.time", return_value=t_base + 44.9):
            assert _get_cached_external_stories(test_db_path, "nosleep", 25) is not None

        # Miss at 45.0s
        with patch("time.time", return_value=t_base + 45.0):
            assert _get_cached_external_stories(test_db_path, "nosleep", 25) is None

    def test_pipeline_refetch_and_cache_renewal_on_expiration(
        self, test_db_path: str, mock_channel_settings: SimpleNamespace
    ):
        """Verify that stage 1 automatically refetches and overwrites stale cache upon expiration."""
        repo = QueueRepository(test_db_path)
        initial_stories = [{"id": "init_1", "title": "Initial", "content": "Old", "url": "https://init/1"}]
        refetched_stories = [{"id": "renewed_1", "title": "Renewed", "content": "Fresh", "url": "https://renew/1"}]

        t_base = 5000.0
        with patch("time.time", return_value=t_base):
            _set_cached_external_stories(test_db_path, "nosleep", 25, initial_stories, ttl_seconds=300.0)

        mock_scoring = SimpleNamespace(passed=True, db_rank_score=90, hybrid_score=0.9, rejection_summary=None)

        # At t_base + 100s: cache HIT, no refetch
        with patch("time.time", return_value=t_base + 100.0), \
             patch("src.pipeline.stages.stage_01_lease.is_test_environment", return_value=False), \
             patch("src.scraper.fetch_reddit_stories") as mock_fetch, \
             patch("src.core.scoring.filter_and_score_story", return_value=mock_scoring), \
             patch("src.db.is_story_duplicate", return_value=False):

            claimed = _claim_or_enqueue_story(
                repository=repo,
                channel_key=CanonicalChannel.MOKU,
                channel_name="moku",
                settings=mock_channel_settings,
                database=test_db_path,
                lane_id="moku-scp-shorts",
                requested_story_id="",
                story=None,
                directed=False,
                generate_only=False,
                owner="worker_1",
                lease_seconds=300,
            )
            mock_fetch.assert_not_called()
            assert claimed is not None and claimed.id == "init_1"

        # Release lease so channel is free for the next claim
        with connect(test_db_path) as conn:
            conn.execute("DELETE FROM leases WHERE job_id = 'init_1'")
            conn.commit()

        # At t_base + 300.0s: EXPIRED -> triggers refetch and rewrites cache
        with patch("time.time", return_value=t_base + 300.0), \
             patch("src.pipeline.stages.stage_01_lease.is_test_environment", return_value=False), \
             patch("src.scraper.fetch_reddit_stories", return_value=refetched_stories) as mock_fetch, \
             patch("src.core.scoring.filter_and_score_story", return_value=mock_scoring), \
             patch("src.db.is_story_duplicate", return_value=False):

            claimed = _claim_or_enqueue_story(
                repository=repo,
                channel_key=CanonicalChannel.MOKU,
                channel_name="moku",
                settings=mock_channel_settings,
                database=test_db_path,
                lane_id="moku-scp-shorts",
                requested_story_id="",
                story=None,
                directed=False,
                generate_only=False,
                owner="worker_2",
                lease_seconds=300,
            )
            assert mock_fetch.call_count == 1
            assert claimed is not None and claimed.id == "renewed_1"

        # Verify DB contains updated payload and refreshed expires_at (300.0 + 300.0 = 600.0 relative to t_base)
        with connect(test_db_path, read_only=True) as conn:
            row = conn.execute("SELECT payload_json, expires_at FROM external_post_cache WHERE cache_key = 'nosleep:25'").fetchone()
            assert row is not None
            assert "renewed_1" in row["payload_json"]
            assert float(row["expires_at"]) == t_base + 600.0

    def test_asymmetric_feed_and_limit_expiration(self, test_db_path: str):
        """Verify independent expiration lifecycles across distinct feed/limit keys."""
        t_base = 10000.0
        # feed A expires at 10300.0
        with patch("time.time", return_value=t_base):
            _set_cached_external_stories(test_db_path, "nosleep", 25, [{"id": "ns25"}], ttl_seconds=300.0)
        # feed B expires at 10600.0
        with patch("time.time", return_value=t_base):
            _set_cached_external_stories(test_db_path, "aita", 25, [{"id": "aita25"}], ttl_seconds=600.0)

        # At t_base + 400.0s: nosleep:25 is expired, but aita:25 is still active
        with patch("time.time", return_value=t_base + 400.0):
            assert _get_cached_external_stories(test_db_path, "nosleep", 25) is None
            hit_aita = _get_cached_external_stories(test_db_path, "aita", 25)
            assert hit_aita is not None and hit_aita[0]["id"] == "aita25"


# ==============================================================================
# 2. Database Corruption & Concurrency Stress Tests
# ==============================================================================

class TestDatabaseCorruptionAndConcurrency:
    """Stress-testing DB anomalies: malformed payloads, non-list types, locked DB, and concurrency."""

    @pytest.mark.parametrize(
        "malformed_syntax",
        [
            "",
            "NOT_JSON_AT_ALL",
            '{"unclosed": "brace',
            "[1, 2, 3",
            "\x00\x01\x02binary_garbage",
            "None",
            "undefined",
        ],
    )
    def test_malformed_json_syntax_returns_none(self, test_db_path: str, malformed_syntax: str):
        """Verify that any unparseable JSON syntax returns None without raising an exception."""
        with connect(test_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS external_post_cache (
                    cache_key TEXT PRIMARY KEY, feed TEXT, payload_json TEXT, fetched_at REAL, expires_at REAL
                )
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO external_post_cache VALUES ('nosleep:25', 'nosleep', ?, 100, 9999999999.0)",
                (malformed_syntax,),
            )
            conn.commit()

        result = _get_cached_external_stories(test_db_path, "nosleep", 25)
        assert result is None

    @pytest.mark.parametrize(
        "semantically_corrupt_payload",
        [
            "12345",
            '"raw_string"',
            '{"error": "rate_limited", "code": 429}',
            "true",
            "null",
            "[1, 2, 3]",
            '["string_item_1", "string_item_2"]',
            '[{"missing_id": "value"}]',
        ],
    )
    def test_semantically_corrupt_json_handled_without_pipeline_crash(
        self, test_db_path: str, mock_channel_settings: SimpleNamespace, semantically_corrupt_payload: str
    ):
        """
        ADVERSARIAL STRESS TEST:
        Valid JSON primitives (int, str, dict, list of non-dicts) stored in SQLite cache.
        Stage 1 MUST recover gracefully by falling back to fetch_reddit_stories instead of crashing with TypeError/KeyError.
        """
        repo = QueueRepository(test_db_path)
        with connect(test_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS external_post_cache (
                    cache_key TEXT PRIMARY KEY, feed TEXT, payload_json TEXT, fetched_at REAL, expires_at REAL
                )
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO external_post_cache VALUES ('nosleep:25', 'nosleep', ?, 100, 9999999999.0)",
                (semantically_corrupt_payload,),
            )
            conn.commit()

        fallback_stories = [
            {
                "id": "recovered_001",
                "title": "Historia de Recuperación",
                "content": "Historia tras recuperación de payload corrupto en caché.",
                "url": "https://reddit.com/r/nosleep/comments/rec_001",
                "upvote_ratio": 0.95,
                "num_comments": 40,
            }
        ]

        mock_scoring = SimpleNamespace(passed=True, db_rank_score=90, hybrid_score=0.9, rejection_summary=None)

        with patch("src.pipeline.stages.stage_01_lease.is_test_environment", return_value=False), \
             patch("src.scraper.fetch_reddit_stories", return_value=fallback_stories) as mock_fetch, \
             patch("src.core.scoring.filter_and_score_story", return_value=mock_scoring), \
             patch("src.db.is_story_duplicate", return_value=False):

            try:
                claimed = _claim_or_enqueue_story(
                    repository=repo,
                    channel_key=CanonicalChannel.MOKU,
                    channel_name="moku",
                    settings=mock_channel_settings,
                    database=test_db_path,
                    lane_id="moku-scp-shorts",
                    requested_story_id="",
                    story=None,
                    directed=False,
                    generate_only=False,
                    owner="test_worker_corrupt",
                    lease_seconds=300,
                )
                # If it recovered, verify it claimed the fallback story
                assert claimed is not None, "Pipeline failed to claim story after corrupt cache recovery"
                assert claimed.id == "recovered_001"
            except (TypeError, KeyError, AttributeError) as exc:
                pytest.fail(
                    f"CRITICAL BUG: Stage 1 crashed with unhandled {type(exc).__name__}: {exc} "
                    f"when cache contained semantically corrupt payload: {semantically_corrupt_payload!r}. "
                    "Cache reading must validate that returned object is list[dict] with 'id' keys."
                )

    def test_schema_corruption_tolerance(self, test_db_path: str, mock_channel_settings: SimpleNamespace):
        """Verify that missing columns or altered table structure in external_post_cache does not crash stage 1."""
        repo = QueueRepository(test_db_path)
        with connect(test_db_path) as conn:
            # Create corrupted table schema without payload_json or expires_at
            conn.execute("DROP TABLE IF EXISTS external_post_cache")
            conn.execute("CREATE TABLE external_post_cache (dummy_col TEXT PRIMARY KEY, feed TEXT)")
            conn.commit()

        # Cache get must return None gracefully
        assert _get_cached_external_stories(test_db_path, "nosleep", 25) is None

        # Cache set must not raise exception
        _set_cached_external_stories(test_db_path, "nosleep", 25, [{"id": "s1"}])

        fallback_stories = [{"id": "schema_fallback_1", "title": "Schema OK", "content": "Content", "url": "https://..."}]
        mock_scoring = SimpleNamespace(passed=True, db_rank_score=90, hybrid_score=0.9, rejection_summary=None)

        with patch("src.pipeline.stages.stage_01_lease.is_test_environment", return_value=False), \
             patch("src.scraper.fetch_reddit_stories", return_value=fallback_stories), \
             patch("src.core.scoring.filter_and_score_story", return_value=mock_scoring), \
             patch("src.db.is_story_duplicate", return_value=False):

            claimed = _claim_or_enqueue_story(
                repository=repo,
                channel_key=CanonicalChannel.MOKU,
                channel_name="moku",
                settings=mock_channel_settings,
                database=test_db_path,
                lane_id="moku-scp-shorts",
                requested_story_id="",
                story=None,
                directed=False,
                generate_only=False,
                owner="test_worker_schema",
                lease_seconds=300,
            )
            assert claimed is not None and claimed.id == "schema_fallback_1"

    def test_locked_database_resilience(self, test_db_path: str):
        """Verify that a locked database (sqlite3.OperationalError: database is locked) does not crash cache operations."""
        lock_conn = sqlite3.connect(test_db_path, timeout=0.01)
        lock_conn.execute("BEGIN EXCLUSIVE")

        try:
            # Patch BUSY_TIMEOUT_MS to 10ms for fast deterministic test execution
            with patch("src.core.repository.migrations.BUSY_TIMEOUT_MS", 10):
                # Reading must catch error and return None
                result = _get_cached_external_stories(test_db_path, "nosleep", 25)
                assert result is None

                # Writing must catch error and return without raising
                _set_cached_external_stories(test_db_path, "nosleep", 25, [{"id": "locked_1"}])
        finally:
            lock_conn.rollback()
            lock_conn.close()

    def test_read_only_database_filesystem(self, test_db_path: str):
        """Verify cache operations when the SQLite database file permissions are read-only (0o444)."""
        # Ensure table exists first
        _set_cached_external_stories(test_db_path, "nosleep", 25, [{"id": "ro_story"}])

        os.chmod(test_db_path, 0o444)
        try:
            # Reading unexpired cache should succeed
            res = _get_cached_external_stories(test_db_path, "nosleep", 25)
            assert res is not None
            assert res[0]["id"] == "ro_story"

            # Writing to read-only DB should be caught gracefully without crashing
            _set_cached_external_stories(test_db_path, "nosleep", 25, [{"id": "ro_fail"}])
        finally:
            os.chmod(test_db_path, 0o644)

    def test_multithreaded_concurrency_hammer(self, test_db_path: str):
        """Concurrent workers simultaneously reading, writing, and invalidating external_post_cache."""
        num_threads = 8
        operations_per_thread = 25
        errors: list[Exception] = []

        def worker_task(thread_id: int):
            for i in range(operations_per_thread):
                feed = f"feed_{thread_id % 3}"
                limit = 25
                stories = [{"id": f"story_{thread_id}_{i}", "title": f"Story {i}"}]
                try:
                    if i % 2 == 0:
                        _set_cached_external_stories(test_db_path, feed, limit, stories, ttl_seconds=300.0)
                    else:
                        _get_cached_external_stories(test_db_path, feed, limit)
                except Exception as exc:
                    errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker_task, tid) for tid in range(num_threads)]
            concurrent.futures.wait(futures)

        assert len(errors) == 0, f"Concurrent cache operations produced errors: {errors}"


# ==============================================================================
# 3. Queue Lease Invariant Integrity Tests
# ==============================================================================

class TestQueueLeaseInvariantIntegrity:
    """Stress-testing queue invariants: claim integrity, duplicate suppression, worker isolation, and reaper."""

    def test_cache_does_not_corrupt_story_claiming_or_duplicate_suppression(
        self, test_db_path: str, mock_channel_settings: SimpleNamespace
    ):
        """
        Verify that returning cached candidate stories NEVER bypasses is_story_duplicate,
        never duplicates stories in the DB, and properly advances queue claims.
        """
        repo = QueueRepository(test_db_path)
        candidates = [
            {
                "id": "batch_001",
                "title": "El Monstruo del Lago Rojo",
                "content": "Un monstruo gigantesco emergió de las profundidades del lago rojo durante la tormenta eléctrica.",
                "url": "https://post/1",
            },
            {
                "id": "batch_002",
                "title": "El Manuscrito de la Biblioteca",
                "content": "En la vieja biblioteca abandonada encontramos un manuscrito antiguo encuadernado en piel humana.",
                "url": "https://post/2",
            },
            {
                "id": "batch_003",
                "title": "La Señal de la Luna Helada",
                "content": "Los astronautas descubrieron que la señal de radio provenía del interior de la luna helada.",
                "url": "https://post/3",
            },
        ]
        # Seed cache with candidates
        _set_cached_external_stories(test_db_path, "nosleep", 25, candidates, ttl_seconds=300.0)

        mock_scoring = SimpleNamespace(passed=True, db_rank_score=90, hybrid_score=0.9, rejection_summary=None)

        claimed_ids = []
        # Simulate 3 consecutive runs within TTL window
        for run_idx in range(3):
            with patch("src.pipeline.stages.stage_01_lease.is_test_environment", return_value=False), \
                 patch("src.scraper.fetch_reddit_stories") as mock_fetch, \
                 patch("src.core.scoring.filter_and_score_story", return_value=mock_scoring):

                claimed = _claim_or_enqueue_story(
                    repository=repo,
                    channel_key=CanonicalChannel.MOKU,
                    channel_name="moku",
                    settings=mock_channel_settings,
                    database=test_db_path,
                    lane_id="moku-scp-shorts",
                    requested_story_id="",
                    story=None,
                    directed=False,
                    generate_only=False,
                    owner=f"worker_{run_idx}",
                    lease_seconds=300,
                )
                # Network fetch must NEVER be invoked (cache hit)
                mock_fetch.assert_not_called()
                assert claimed is not None
                claimed_ids.append(claimed.id)

                # Complete and release lease so next story can be claimed on channel
                with connect(test_db_path) as conn:
                    conn.execute("DELETE FROM leases WHERE job_id = ?", (claimed.id,))
                    conn.commit()

        # All 3 claimed IDs must be unique
        assert len(claimed_ids) == 3
        assert len(set(claimed_ids)) == 3, f"Duplicate story claimed across runs: {claimed_ids}"

        # Verify DB contains exactly 1 record per enqueued story
        with connect(test_db_path, read_only=True) as conn:
            for s_id in claimed_ids:
                count = conn.execute("SELECT COUNT(*) FROM stories WHERE story_id = ?", (s_id,)).fetchone()[0]
                assert count == 1, f"Story {s_id} was enqueued {count} times!"

    def test_completed_stories_never_re_enqueued_from_cache(
        self, test_db_path: str, mock_channel_settings: SimpleNamespace
    ):
        """Verify that completed/published stories in DB are strictly skipped when cache returns them."""
        repo = QueueRepository(test_db_path)
        # Pre-enqueue story_001 and mark as PUBLISHED
        repo.enqueue("story_001", "Completed Story", "Full Content", "https://url/1", CanonicalChannel.MOKU)
        with connect(test_db_path) as conn:
            conn.execute("UPDATE stories SET status = ? WHERE story_id = 'story_001'", (JobStatus.PUBLISHED.value,))
            conn.commit()

        # Cache still lists story_001 and fresh story_002
        cached_batch = [
            {"id": "story_001", "title": "Completed Story", "content": "Full Content", "url": "https://url/1"},
            {"id": "story_002", "title": "Fresh Story", "content": "New Content", "url": "https://url/2"},
        ]
        _set_cached_external_stories(test_db_path, "nosleep", 25, cached_batch, ttl_seconds=300.0)

        mock_scoring = SimpleNamespace(passed=True, db_rank_score=80, hybrid_score=0.8, rejection_summary=None)

        with patch("src.pipeline.stages.stage_01_lease.is_test_environment", return_value=False), \
             patch("src.scraper.fetch_reddit_stories") as mock_fetch, \
             patch("src.core.scoring.filter_and_score_story", return_value=mock_scoring):

            claimed = _claim_or_enqueue_story(
                repository=repo,
                channel_key=CanonicalChannel.MOKU,
                channel_name="moku",
                settings=mock_channel_settings,
                database=test_db_path,
                lane_id="moku-scp-shorts",
                requested_story_id="",
                story=None,
                directed=False,
                generate_only=False,
                owner="worker_completed_test",
                lease_seconds=300,
            )
            # Story 1 was already completed, so story 2 MUST be claimed
            assert claimed is not None
            assert claimed.id == "story_002"

    def test_worker_lease_acquisition_and_owner_isolation(
        self, test_db_path: str, mock_channel_settings: SimpleNamespace
    ):
        """Verify that concurrent workers on different channels acquire distinct leases with proper ownership isolation."""
        repo = QueueRepository(test_db_path)
        candidates_moku = [
            {"id": "iso_moku_1", "title": "Story Moku", "content": "Content Moku", "url": "https://moku/1"},
        ]
        candidates_aelithia = [
            {"id": "iso_ael_1", "title": "Story Aelithia", "content": "Content Aelithia", "url": "https://ael/1"},
        ]
        _set_cached_external_stories(test_db_path, "nosleep", 25, candidates_moku, ttl_seconds=300.0)
        _set_cached_external_stories(test_db_path, "aita", 25, candidates_aelithia, ttl_seconds=300.0)
        mock_scoring = SimpleNamespace(passed=True, db_rank_score=90, hybrid_score=0.9, rejection_summary=None)

        # Worker A claims on Moku
        with patch("src.pipeline.stages.stage_01_lease.is_test_environment", return_value=False), \
             patch("src.core.scoring.filter_and_score_story", return_value=mock_scoring):

            claimed_a = _claim_or_enqueue_story(
                repository=repo,
                channel_key=CanonicalChannel.MOKU,
                channel_name="moku",
                settings=mock_channel_settings,
                database=test_db_path,
                lane_id="moku-scp-shorts",
                requested_story_id="",
                story=None,
                directed=False,
                generate_only=False,
                owner="owner_alpha",
                lease_seconds=600,
            )

        # Worker B claims on Aelithia
        settings_aelithia = SimpleNamespace(source_feed="aita", channel_name="aelithia")
        with patch("src.pipeline.stages.stage_01_lease.is_test_environment", return_value=False), \
             patch("src.core.scoring.filter_and_score_story", return_value=mock_scoring):

            claimed_b = _claim_or_enqueue_story(
                repository=repo,
                channel_key=CanonicalChannel.AELITHIA,
                channel_name="aelithia",
                settings=settings_aelithia,
                database=test_db_path,
                lane_id="aelithia-drama-shorts",
                requested_story_id="",
                story=None,
                directed=False,
                generate_only=False,
                owner="owner_beta",
                lease_seconds=600,
            )

        # Claims must be distinct
        assert claimed_a is not None and claimed_b is not None
        assert claimed_a.id == "iso_moku_1"
        assert claimed_b.id == "iso_ael_1"

        # Verify lease table owners
        with connect(test_db_path, read_only=True) as conn:
            lease_a = conn.execute("SELECT owner FROM leases WHERE job_id = ?", (claimed_a.id,)).fetchone()
            assert lease_a is not None and lease_a["owner"] == "owner_alpha"

            lease_b = conn.execute("SELECT owner FROM leases WHERE job_id = ?", (claimed_b.id,)).fetchone()
            assert lease_b is not None and lease_b["owner"] == "owner_beta"

    def test_lease_expiry_reaper_interaction_with_cached_stories(
        self, test_db_path: str, mock_channel_settings: SimpleNamespace
    ):
        """
        Verify interaction between lease expiration reaper and candidate cache:
        Worker A claims story S1. Worker A dies and lease expires.
        Worker B runs Stage 1 with cached candidates: reaper reclaims S1 to RETRYABLE_FAILED,
        and Worker B safely acquires S1 without duplicate enqueuing.
        """
        repo = QueueRepository(test_db_path)
        candidates = [{"id": "reap_001", "title": "Reaper Target", "content": "Will expire", "url": "https://reap/1"}]
        _set_cached_external_stories(test_db_path, "nosleep", 25, candidates, ttl_seconds=300.0)

        mock_scoring = SimpleNamespace(passed=True, db_rank_score=95, hybrid_score=0.95, rejection_summary=None)

        t_start = 20000.0
        # Worker A claims story with 60s lease
        with patch("time.time", return_value=t_start), \
             patch("src.pipeline.stages.stage_01_lease.is_test_environment", return_value=False), \
             patch("src.core.scoring.filter_and_score_story", return_value=mock_scoring):

            claimed_a = _claim_or_enqueue_story(
                repository=repo,
                channel_key=CanonicalChannel.MOKU,
                channel_name="moku",
                settings=mock_channel_settings,
                database=test_db_path,
                lane_id="moku-scp-shorts",
                requested_story_id="",
                story=None,
                directed=False,
                generate_only=False,
                owner="dead_worker_a",
                lease_seconds=60,
            )
            assert claimed_a is not None and claimed_a.id == "reap_001"

        # Advance time by 70s (lease is now expired)
        t_reap = t_start + 70.0

        # Worker B runs full stage_01_claim_lease
        profiler = PipelineProfiler()
        with patch("time.time", return_value=t_reap), \
             patch("src.pipeline.stages.stage_01_lease.is_test_environment", return_value=False), \
             patch("src.pipeline.stages.stage_01_lease.get_channel_settings", return_value=mock_channel_settings), \
             patch("src.core.scoring.filter_and_score_story", return_value=mock_scoring):

            claimed_ctx, err = stage_01_claim_lease(
                channel_key=CanonicalChannel.MOKU,
                channel_name="moku",
                db_path=test_db_path,
                story_id=None,
                story=None,
                directed=False,
                generate_only=False,
                owner="live_worker_b",
                lane_id="moku-scp-shorts",
                profiler=profiler,
            )

            assert err is None, f"stage_01_claim_lease returned error: {err}"
            assert claimed_ctx is not None
            assert claimed_ctx.story_id == "reap_001"
            assert claimed_ctx.owner == "live_worker_b"

        # Verify DB has exactly ONE record for reap_001 (no duplicate enqueuing)
        with connect(test_db_path, read_only=True) as conn:
            count = conn.execute("SELECT COUNT(*) FROM stories WHERE story_id = 'reap_001'").fetchone()[0]
            assert count == 1, f"Story reap_001 was duplicated in database! Count={count}"
            lease_row = conn.execute("SELECT owner FROM leases WHERE job_id = 'reap_001'").fetchone()
            assert lease_row is not None and lease_row["owner"] == "live_worker_b"
