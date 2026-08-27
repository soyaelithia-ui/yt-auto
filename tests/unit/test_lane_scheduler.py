"""Unit tests for the multi-lane cadence scheduler (LaneScheduler)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from src.core.lanes import fallback_lanes
from src.core.repository import QueueRepository, migrate_database
from src.core.scheduler import LanePick, LaneScheduler


@pytest.fixture()
def db_path(tmp_path):
    target = str(tmp_path / "sched.db")
    migrate_database(target)
    return target


@pytest.fixture()
def lanes():
    return fallback_lanes()


def _make(db_path, lanes) -> LaneScheduler:
    scheduler = LaneScheduler(str(db_path), lanes=lanes)
    scheduler.initialize()
    return scheduler


class TestTakeDueLanes:
    def test_all_new_lanes_due_immediately(self, db_path, lanes):
        scheduler = _make(db_path, lanes)
        picks = scheduler.take_due_lanes(now=int(time.time()), max_picks=5)
        assert {pick.lane_id for pick in picks} == {
            lane.id for lane in lanes
        }

    def test_max_picks_limits_per_tick(self, db_path, lanes):
        scheduler = _make(db_path, lanes)
        picks = scheduler.take_due_lanes(now=int(time.time()), max_picks=2)
        assert len(picks) == 2

    def test_fired_lane_respects_ceiling(self, db_path, lanes):
        now = int(time.time())
        scheduler = _make(db_path, lanes)
        first = scheduler.take_due_lanes(now=now, max_picks=5)
        for pick in first:
            scheduler.commit_fire(pick, run_id=f"run-{pick.lane_id}")
        # Within the gap: no lane is due again.
        assert scheduler.take_due_lanes(now=now + 60, max_picks=5) == []
        # After the gap: every lane becomes due again.
        later = scheduler.take_due_lanes(now=now + 1900, max_picks=5)
        assert {pick.lane_id for pick in later} == {lane.id for lane in lanes}

    def test_most_overdue_first(self, db_path, lanes):
        repo = QueueRepository(str(db_path))
        now = int(time.time())
        short, long = lanes[0], lanes[1]
        repo.ensure_lane_rows([lane.id for lane in lanes], now=now - 1000)
        # Push short AND aelithia forward; moku-horror-long is most overdue.
        repo.mark_lane_fired(short.id, fired_at=now - 500, next_due_at=now + 10_000)
        repo.mark_lane_fired(
            "aelithia-aita-long", fired_at=now - 500, next_due_at=now + 10_000
        )
        scheduler = LaneScheduler(str(db_path), lanes=lanes)
        scheduler.initialize()
        picks = scheduler.take_due_lanes(now=now, max_picks=1)
        assert picks[0].lane_id == long.id

    def test_live_lease_blocks_pick(self, db_path, lanes):
        repo = QueueRepository(str(db_path))
        now = int(time.time())
        scheduler = _make(db_path, lanes)
        lane_id = lanes[0].id
        channel = lanes[0].channel.value
        repo.enqueue("story-x", "Título", "Contenido " * 30, "https://example.com/x", channel)
        job = repo.claim_for_lane(lane_id, channel, "worker", lease_seconds=900, now=now)
        assert job is not None
        picks = [p for p in scheduler.take_due_lanes(now=now, max_picks=5)]
        assert all(pick.lane_id != lane_id for pick in picks)

    def test_paused_channel_blocks_all_its_lanes(self, db_path, lanes):
        repo = QueueRepository(str(db_path))
        scheduler = _make(db_path, lanes)
        repo.pause(lanes[0].channel.value, reason="qa")
        picks = scheduler.take_due_lanes(now=int(time.time()), max_picks=5)
        assert all(pick.channel.value != lanes[0].channel.value for pick in picks)

    def test_unknown_state_lane_skipped_safely(self, db_path, lanes):
        repo = QueueRepository(str(db_path))
        repo.ensure_lane_rows(["ghost-lane"], now=0)
        scheduler = _make(db_path, lanes)
        picks = scheduler.take_due_lanes(now=int(time.time()), max_picks=5)
        assert all(pick.lane_id != "ghost-lane" for pick in picks)


class TestCommitSemantics:
    def test_commit_fire_zeroes_empty_streak(self, db_path, lanes):
        scheduler = _make(db_path, lanes)
        pick = LanePick(
            lane_id=lanes[0].id,
            channel=lanes[0].channel,
            fired_at=int(time.time()),
            next_due_at=int(time.time()) + lanes[0].cadence_min_gap_seconds,
        )
        scheduler.commit_empty(pick)
        scheduler.commit_fire(pick, run_id="r9")
        state = scheduler.repository.get_lane_state(lanes[0].id)
        assert state["consecutive_empty"] == 0
        assert state["last_run_id"] == "r9"

    def test_backoff_ramps_and_caps(self, db_path, lanes):
        scheduler = _make(db_path, lanes)
        base = int(time.time())
        pick = LanePick(lane_id=lanes[0].id, channel=lanes[0].channel, fired_at=base,
                        next_due_at=base)
        scheduler.commit_empty(pick)  # streak 0 -> backoff low bound
        first_gap = (
            scheduler.repository.get_lane_state(lanes[0].id)["next_due_at"] - base
        )
        scheduler.commit_empty(pick)  # streak 1
        second_gap = (
            scheduler.repository.get_lane_state(lanes[0].id)["next_due_at"] - base
        )
        assert 0 < first_gap <= second_gap <= 120

    def test_no_catchup_after_long_outage(self, db_path, lanes):
        """After hours down, one fire happens and the ceiling moves from now."""
        scheduler = _make(db_path, lanes)
        before = int(time.time())
        outage_end = before + 7_200  # daemon slept two hours
        picks = scheduler.take_due_lanes(now=outage_end, max_picks=5)
        short = next(p for p in picks if p.lane_id == "moku-scp-shorts")
        scheduler.commit_fire(short, run_id="after-outage")
        state = scheduler.repository.get_lane_state("moku-scp-shorts")
        assert state["next_due_at"] == outage_end + 300
        # Exactly one pending fire per lane even after the outage.
        again = scheduler.take_due_lanes(now=outage_end + 1, max_picks=5)
        assert all(pick.lane_id != "moku-scp-shorts" for pick in again)


class TestInitialize:
    def test_initialize_seeds_lane_rows(self, tmp_path, lanes):
        from src.core.repository import QueueRepository, migrate_database

        db = str(tmp_path / "seed.db")
        migrate_database(db)
        scheduler = LaneScheduler(db, lanes=lanes)
        scheduler.initialize()
        for lane in lanes:
            assert QueueRepository(db).get_lane_state(lane.id) is not None
