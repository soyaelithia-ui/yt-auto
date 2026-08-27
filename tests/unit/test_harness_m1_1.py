"""Offline regression checks replacing the incompatible milestone-1 harness."""

from src.config import get_channel_config
from src.core.domain import canonical_channel
from src.core.scheduler import PersistentScheduler


def test_aliases_are_input_compatibility_only():
    assert canonical_channel("terror").value == "moku"
    assert canonical_channel("soy_el_malo").value == "aelithia"
    assert get_channel_config("soy_el_malo") == get_channel_config("aelithia")


def test_scheduler_uses_an_explicit_temporary_database(tmp_path):
    scheduler = PersistentScheduler(str(tmp_path / "scheduler.db"), interval_seconds=1800)
    scheduler.initialize()
    first = scheduler.take_due_turn(now=1_000)
    second = scheduler.take_due_turn(now=2_800)
    assert first is not None and second is not None
    assert [first.channel.value, second.channel.value] == ["moku", "aelithia"]
