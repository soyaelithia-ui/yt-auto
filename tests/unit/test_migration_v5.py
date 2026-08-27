"""Unit tests for migration v5 (production lanes) and lane lease machinery."""

from __future__ import annotations

import sqlite3

import pytest

from src.core.domain import JobStatus
from src.core.repository import QueueRepository, connect, migrate_database


@pytest.fixture()
def db_path(tmp_path):
    target = str(tmp_path / "queue.db")
    migrate_database(target)
    return target


def _table_names(db_path: str) -> set[str]:
    with connect(db_path, read_only=True) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row["name"] for row in rows}


class TestMigrationV5:
    def test_applies_on_fresh_database(self, db_path):
        tables = _table_names(db_path)
        assert "scheduler_lane_state" in tables
        assert "lane_leases" in tables
        with connect(db_path, read_only=True) as conn:
            versions = [
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")
            ]
        assert versions == [1, 2, 3, 4, 5]

    def test_additive_columns_present(self, db_path):
        with connect(db_path, read_only=True) as conn:
            columns = lambda table: {
                row["name"] for row in conn.execute(f"PRAGMA table_info({table})")
            }
            assert "lane_id" in columns("runs")
            assert {"lane_id", "source_license"} <= columns("stories")
            assert "story_key" in columns("artifacts")
            assert "simhash" in columns("content_fingerprints")

    def test_rerun_is_noop(self, db_path):
        report = migrate_database(db_path)
        assert report.applied_versions == ()
        assert report.quick_check == "ok"

    def test_recovers_from_partial_v5_state(self, db_path):
        # Schema objects exist but the migration record was lost (interrupted run).
        with connect(db_path) as conn:
            conn.execute("DELETE FROM schema_migrations WHERE version = 5")
            conn.commit()
        report = migrate_database(db_path)
        assert report.applied_versions == (5,)
        assert report.quick_check == "ok"


class TestLaneClaims:
    def _story(self, repo: QueueRepository, story_id: str = "s1", channel: str = "moku"):
        assert repo.enqueue(story_id, f"Título {story_id}", "Contenido " * 20, f"https://example.com/{story_id}", channel)

    def test_claim_for_lane_basics(self, db_path):
        repo = QueueRepository(db_path)
        self._story(repo)
        job = repo.claim_for_lane("moku-scp-shorts", "moku", "worker-a", lease_seconds=600)
        assert job is not None
        assert job["status"] == JobStatus.PROCESSING.value
        # Lane persisted on both story and run.
        with connect(db_path, read_only=True) as conn:
            story_lane = conn.execute(
                "SELECT lane_id FROM stories WHERE story_id = 's1'"
            ).fetchone()["lane_id"]
            run_lane = conn.execute(
                "SELECT lane_id FROM runs WHERE run_id = ?", (job["run_id"],)
            ).fetchone()["lane_id"]
            lease = conn.execute("SELECT lane_id FROM lane_leases").fetchall()
        assert story_lane == "moku-scp-shorts"
        assert run_lane == "moku-scp-shorts"
        assert [row["lane_id"] for row in lease] == ["moku-scp-shorts"]

    def test_two_lanes_same_channel_hold_leases_concurrently(self, db_path):
        """The whole point of lane leases: short + long of moku in flight."""
        repo = QueueRepository(db_path)
        self._story(repo, "short-one")
        self._story(repo, "long-one")
        first = repo.claim_for_lane("moku-scp-shorts", "moku", "w1", lease_seconds=600)
        second = repo.claim_for_lane("moku-horror-long", "moku", "w2", lease_seconds=600)
        assert first is not None and second is not None
        assert first["run_id"] != second["run_id"]

    def test_same_lane_cannot_double_claim(self, db_path):
        repo = QueueRepository(db_path)
        self._story(repo, "only")
        first = repo.claim_for_lane("moku-scp-shorts", "moku", "w1", lease_seconds=600)
        second = repo.claim_for_lane("moku-scp-shorts", "moku", "w2", lease_seconds=600)
        assert first is not None
        assert second is None

    def test_legacy_channel_lease_blocks_lane_claims(self, db_path):
        repo = QueueRepository(db_path)
        self._story(repo, "legacy")
        self._story(repo, "other")
        legacy = repo.claim("moku", "old-worker", lease_seconds=600)
        assert legacy is not None
        # A lane of the same channel must not produce alongside a legacy claim.
        assert repo.claim_for_lane("moku-horror-long", "moku", "w2") is None

    def test_release_state_frees_lane_and_allows_new_claim(self, db_path):
        repo = QueueRepository(db_path)
        self._story(repo, "cycle")
        job = repo.claim_for_lane("moku-scp-shorts", "moku", "w1", lease_seconds=600)
        # Pipeline failure pattern: a release-state set_status frees the lane
        # lease immediately (same contract as the legacy ``leases`` table).
        assert repo.set_status(
            "cycle", JobStatus.RETRYABLE_FAILED, run_id=job["run_id"], owner="w1"
        )
        assert not conn_rows(db_path, "SELECT 1 FROM lane_leases")
        again = repo.claim_for_lane("moku-scp-shorts", "moku", "w2", lease_seconds=600)
        assert again is not None

    def test_finish_run_releases_lane_without_owner(self, db_path):
        repo = QueueRepository(db_path)
        self._story(repo, "closeout")
        job = repo.claim_for_lane("moku-scp-shorts", "moku", "w1", lease_seconds=600)
        assert repo.finish_run(job["run_id"], JobStatus.PUBLISHED)
        assert not conn_rows(db_path, "SELECT 1 FROM lane_leases")

    def test_heartbeat_works_on_lane_lease(self, db_path):
        repo = QueueRepository(db_path)
        self._story(repo, "beat")
        job = repo.claim_for_lane("moku-scp-shorts", "moku", "w1", lease_seconds=600)
        assert repo.heartbeat(job["run_id"], "w1", lease_seconds=900)
        with connect(db_path, read_only=True) as conn:
            expires = conn.execute(
                "SELECT expires_at - heartbeat_at AS ttl FROM lane_leases WHERE run_id = ?",
                (job["run_id"],),
            ).fetchone()["ttl"]
        assert expires == 900

    def test_expired_lane_lease_recovers_to_retryable(self, db_path):
        repo = QueueRepository(db_path)
        self._story(repo, "stale")
        import time

        past = int(time.time()) - 10_000
        job = repo.claim_for_lane(
            "moku-scp-shorts", "moku", "w1", lease_seconds=600, now=past
        )
        recovered = repo.recover_expired_lane_leases()
        assert recovered == 1
        with connect(db_path, read_only=True) as conn:
            status = conn.execute(
                "SELECT status FROM stories WHERE story_id = 'stale'"
            ).fetchone()["status"]
        assert status == JobStatus.RETRYABLE_FAILED.value

    def test_paused_channel_blocks_lane_claim(self, db_path):
        repo = QueueRepository(db_path)
        self._story(repo, "paused-story")
        repo.pause("moku", reason="mantenimiento")
        assert repo.claim_for_lane("moku-scp-shorts", "moku", "w1") is None

    def test_story_lane_preference_over_unassigned(self, db_path):
        repo = QueueRepository(db_path)
        self._story(repo, "assigned")
        self._story(repo, "unassigned")
        with connect(db_path) as conn:
            conn.execute(
                "UPDATE stories SET lane_id = 'moku-horror-long' WHERE story_id = 'assigned'"
            )
            conn.commit()
        # A different lane prefers unassigned-compatible stories over stealing.
        job = repo.claim_for_lane("moku-scp-shorts", "moku", "w1", lease_seconds=600)
        assert job["story_id"] == "unassigned"

    def test_empty_lane_id_rejected(self, db_path):
        with pytest.raises(ValueError):
            QueueRepository(db_path).claim_for_lane("", "moku", "w1")


class TestLaneSchedulerState:
    def test_due_lanes_ordered_by_most_overdue(self, db_path):
        import time

        repo = QueueRepository(db_path)
        base = int(time.time()) - 5_000
        repo.ensure_lane_rows(["l1", "l2"], now=base)
        # l2 gets pushed into the future; only the never-fired l1 is due.
        repo.mark_lane_fired("l2", fired_at=base, next_due_at=base + 3_600)
        due = repo.due_lanes(now=base + 10)
        assert [row["lane_id"] for row in due] == ["l1"]

    def test_mark_lane_fired_sets_ceiling_not_accumulation(self, db_path):
        import time

        repo = QueueRepository(db_path)
        now = int(time.time())
        repo.ensure_lane_rows(["l1"], now=now)
        repo.mark_lane_fired(
            "l1", fired_at=now, next_due_at=now + 300, run_id="r1"
        )
        state = repo.get_lane_state("l1")
        assert state["next_due_at"] == now + 300
        assert state["last_run_id"] == "r1"
        # Even if the daemon slept 2 hours, only one fire happens per tick.
        assert repo.due_lanes(now=now + 7_200)[0]["lane_id"] == "l1"
        repo.mark_lane_fired("l1", fired_at=now + 7_200, next_due_at=now + 7_500)
        assert repo.due_lanes(now=now + 7_300) == []

    def test_empty_fire_counts_but_keeps_next_due(self, db_path):
        import time

        repo = QueueRepository(db_path)
        now = int(time.time())
        repo.ensure_lane_rows(["l1"], now=now)
        seeded = repo.get_lane_state("l1")["next_due_at"]
        repo.mark_lane_fired("l1", fired_at=now, next_due_at=seeded + 100, empty=True)
        state = repo.get_lane_state("l1")
        assert state["consecutive_empty"] == 1
        # An empty fire must not advance the cadence; the scheduler applies backoff.
        assert state["next_due_at"] == seeded + 100

    def test_pause_resume_lane(self, db_path):
        import time

        repo = QueueRepository(db_path)
        repo.ensure_lane_rows(["l1"], now=int(time.time()) - 60)
        repo.set_lane_paused("l1", True, reason="editorial")
        assert repo.due_lanes() == []
        repo.set_lane_paused("l1", False)
        assert len(repo.due_lanes()) == 1


def conn_rows(db_path: str, sql: str) -> list[sqlite3.Row]:
    with connect(db_path, read_only=True) as conn:
        return conn.execute(sql).fetchall()
