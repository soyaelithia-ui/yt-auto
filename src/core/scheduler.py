"""Persistent fair scheduler: lane cadence ceilings with no catch-up bursts."""

from __future__ import annotations

import time
from dataclasses import dataclass

from src.config import SETTINGS
from src.core.domain import CanonicalChannel
from src.core.lanes import LaneProfile, load_lanes
from src.core.repository import (
    QueueRepository,
    connect,
    migrate_database,
)


@dataclass(frozen=True)
class SchedulerDecision:
    channel: CanonicalChannel
    due_at: int
    next_due_at: int


@dataclass(frozen=True)
class LanePick:
    """One lane the scheduler has decided to fire on this tick."""

    lane_id: str
    channel: CanonicalChannel
    fired_at: int
    next_due_at: int


class PersistentScheduler:
    def __init__(self, db_path: str, interval_seconds: int | None = None):
        self.db_path = db_path
        self.interval_seconds = interval_seconds or SETTINGS.scheduler_interval_seconds
        if self.interval_seconds < 1:
            raise ValueError("El intervalo del scheduler debe ser positivo")

    def initialize(self) -> None:
        migrate_database(self.db_path)

    def take_due_turn(self, *, now: int | None = None) -> SchedulerDecision | None:
        current = int(time.time() if now is None else now)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT next_channel, next_run_at FROM scheduler_state "
                "WHERE scheduler_id = 1"
            ).fetchone()
            if not row:
                conn.rollback()
                raise RuntimeError("scheduler_state no está inicializado")
            due_at = int(row["next_run_at"])
            if due_at > current:
                conn.rollback()
                return None

            pref_raw = row["next_channel"]
            preferred = CanonicalChannel(pref_raw) if pref_raw in ("moku", "aelithia") else CanonicalChannel.MOKU
            alternate = (
                CanonicalChannel.AELITHIA
                if preferred is CanonicalChannel.MOKU
                else CanonicalChannel.MOKU
            )
            chosen: Optional[CanonicalChannel] = None
            for candidate in (preferred, alternate):
                control = conn.execute(
                    "SELECT paused FROM channel_controls WHERE channel = ?",
                    (candidate.value,),
                ).fetchone()
                lease = conn.execute(
                    "SELECT 1 FROM leases WHERE channel = ? AND expires_at > ?",
                    (candidate.value, current),
                ).fetchone()
                if not (control and control["paused"]) and not lease:
                    chosen = candidate
                    break

            # Always move the clock forward from "now": missed turns are never replayed.
            next_due = current + self.interval_seconds
            next_channel = alternate if chosen == preferred else preferred
            conn.execute(
                """
                UPDATE scheduler_state
                SET next_channel = ?, next_run_at = ?, last_run_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE scheduler_id = 1
                """,
                (next_channel.value, next_due, current if chosen else None),
            )
            conn.commit()
            if chosen is None:
                return None
            return SchedulerDecision(
                channel=chosen,
                due_at=due_at,
                next_due_at=next_due,
            )

    def seconds_until_due(self, *, now: int | None = None) -> int:
        current = int(time.time() if now is None else now)
        with connect(self.db_path, read_only=True) as conn:
            row = conn.execute(
                "SELECT next_run_at FROM scheduler_state WHERE scheduler_id = 1"
            ).fetchone()
        if not row:
            return 0
        return max(0, int(row["next_run_at"]) - current)


class LaneScheduler:
    """Fires production lanes respecting per-lane cadence ceilings.

    Semantics (deliberately different from a wall-clock cron grid):
    - ``next_due_at = fired_at + min_gap_seconds`` after every fire, so a daemon
      outage never produces catch-up bursts: missed time is simply lost.
    - Most-overdue lane fires first.
    - A lane with no claimable story backs off briefly instead of advancing its
      full cadence (production continues once stories arrive).
    """

    EMPTY_BACKOFF_SECONDS_RANGE = (60, 120)

    def __init__(
        self,
        db_path: str,
        *,
        lanes=None,
        repository: QueueRepository | None = None,
    ):
        self.db_path = db_path
        self.repository = repository or QueueRepository(db_path)
        self._lanes = tuple(lanes) if lanes is not None else load_lanes()

    def initialize(self, *, apply_offsets: bool = True) -> None:
        migrate_database(self.db_path)
        offsets = (
            {
                lane.id: getattr(lane, "cadence_initial_offset_seconds", 0)
                for lane in self._lanes
            }
            if apply_offsets
            else {}
        )
        self.repository.ensure_lane_rows([lane.id for lane in self._lanes], offsets=offsets)

    @property
    def lanes(self) -> tuple[LaneProfile, ...]:
        return self._lanes

    def _lane_by_id(self, lane_id: str) -> LaneProfile | None:
        for lane in self._lanes:
            if lane.id == lane_id:
                return lane
        return None

    def _backoff_seconds(self, consecutive_empty: int) -> int:
        low, high = self.EMPTY_BACKOFF_SECONDS_RANGE
        # Linear ramp capped at the ceiling: 60s first, 120s afterwards.
        return min(high, low + 30 * max(0, consecutive_empty - 1))

    def take_due_lanes(
        self,
        *,
        now: int | None = None,
        max_picks: int = 2,
        lanes_filter: set[str] | None = None,
        exclude_lanes: set[str] | None = None,
    ) -> list[LanePick]:
        """Return at most ``max_picks`` lanes to fire right now.

        Pure scheduling decision: marks each pick's post-fire ceiling and
        heartbeat bookkeeping, but does not execute any pipeline work. The
        caller owns execution and must honour ``LanePick.lane_id`` exclusively.
        ``lanes_filter`` restricts candidates so a filtered daemon never wastes
        its per-tick budget on lanes it will not execute.
        """
        current = int(time.time() if now is None else now)
        picks: list[LanePick] = []
        for state in self.repository.due_lanes(now=current):
            if len(picks) >= max_picks:
                break
            lane = self._lane_by_id(str(state["lane_id"]))
            if lane is None or not lane.enabled:
                continue
            if lanes_filter is not None and lane.id not in lanes_filter:
                continue
            if exclude_lanes is not None and lane.id in exclude_lanes:
                continue
            # A live lease on this lane means it is already producing.
            lease_row = None
            with connect(self.db_path, read_only=True) as conn:
                lease_row = conn.execute(
                    "SELECT 1 FROM lane_leases WHERE lane_id = ? AND expires_at > ?",
                    (lane.id, current),
                ).fetchone()
            if lease_row:
                continue
            paused_channel = False
            with connect(self.db_path, read_only=True) as conn:
                control = conn.execute(
                    "SELECT paused FROM channel_controls WHERE channel = ?",
                    (lane.channel.value,),
                ).fetchone()
                paused_channel = bool(control and control["paused"])
            if paused_channel:
                continue
            next_due = current + lane.cadence_min_gap_seconds
            picks.append(
                LanePick(
                    lane_id=lane.id,
                    channel=lane.channel,
                    fired_at=current,
                    next_due_at=next_due,
                )
            )
        return picks

    def commit_fire(self, pick: LanePick, *, run_id: str | None) -> None:
        """Record a productive fire: advance the lane's cadence ceiling."""
        self.repository.mark_lane_fired(
            pick.lane_id,
            fired_at=pick.fired_at,
            next_due_at=pick.next_due_at,
            run_id=run_id,
        )

    def commit_empty(self, pick: LanePick) -> None:
        """Record an empty fire: short backoff, cadence ceiling unchanged."""
        state = self.repository.get_lane_state(pick.lane_id) or {}
        backoff = self._backoff_seconds(int(state.get("consecutive_empty") or 0))
        self.repository.mark_lane_fired(
            pick.lane_id,
            fired_at=pick.fired_at,
            next_due_at=pick.fired_at + backoff,
            empty=True,
        )

    def seconds_until_due(
        self,
        *,
        now: int | None = None,
        lanes_filter: set[str] | None = None,
    ) -> int:
        """Return the number of seconds until the earliest eligible lane is due.

        Checks all enabled, non-paused, non-leased lanes and finds min(next_due_at - current).
        If no lanes are configured or pending, defaults to 60.
        """
        current = int(time.time() if now is None else now)
        min_wait: int | None = None
        for lane in self._lanes:
            if not lane.enabled:
                continue
            if lanes_filter is not None and lane.id not in lanes_filter:
                continue
            state = self.repository.get_lane_state(lane.id)
            if not state:
                return 0
            if state.get("paused"):
                continue
            with connect(self.db_path, read_only=True) as conn:
                control = conn.execute(
                    "SELECT paused FROM channel_controls WHERE channel = ?",
                    (lane.channel.value,),
                ).fetchone()
                if control and control["paused"]:
                    continue
                lease_row = conn.execute(
                    "SELECT 1 FROM lane_leases WHERE lane_id = ? AND expires_at > ?",
                    (lane.id, current),
                ).fetchone()
                if lease_row:
                    continue

            next_due_at = int(state.get("next_due_at") or state.get("next_run_at") or 0)
            wait = max(0, next_due_at - current)
            if min_wait is None or wait < min_wait:
                min_wait = wait
        return min_wait if min_wait is not None else 60


# Backward-compatible AutoPilot re-exports ported from Temp-
from src.core.autopilot import AUTO_TOPICS, AutoPilotScheduler

__all__ = [
    "SchedulerDecision",
    "LanePick",
    "PersistentScheduler",
    "LaneScheduler",
    "AUTO_TOPICS",
    "AutoPilotScheduler",
]
