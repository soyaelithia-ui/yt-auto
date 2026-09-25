"""
Unit tests for lane-level circuit breaker isolation, thumbnail anti-collision,
and narrative template diversity.
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from src.core.guard import ConsecutiveFailureBreaker
from src.core.repository import QueueRepository, connect
from src.daemon import _register_turn_failure
from src.agents.seo_optimizer import SeoOptimizerAgent
from src.core.quality import text_similarity
from src.templates.longform_stories import (
    AELITHIA_STORIES,
    MOKU_STORIES,
    get_aelithia_longform_story,
    get_moku_longform_story,
)


def test_lane_level_failure_breaker_pauses_lane_not_channel(tmp_path: Path):
    db_path = str(tmp_path / "test_queue.db")
    repo = QueueRepository(db_path)
    repo.initialize()

    # Seed channel control and two lanes
    repo._set_paused("moku", False, None)
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO scheduler_lane_state (lane_id, next_due_at, consecutive_empty, paused, updated_at) "
            "VALUES (?, ?, 0, 0, datetime('now'))",
            ("moku-horror-long", 1000),
        )
        conn.execute(
            "INSERT INTO scheduler_lane_state (lane_id, next_due_at, consecutive_empty, paused, updated_at) "
            "VALUES (?, ?, 0, 0, datetime('now'))",
            ("moku-scp-shorts", 1000),
        )
        conn.commit()

    breaker = ConsecutiveFailureBreaker(threshold=3)

    # 1. First two failures on moku-horror-long
    _register_turn_failure(db_path, "moku", breaker, "Simulated Error 1", lane_id="moku-horror-long")
    _register_turn_failure(db_path, "moku", breaker, "Simulated Error 2", lane_id="moku-horror-long")

    lane_state = repo.get_lane_state("moku-horror-long")
    assert lane_state is not None and lane_state["paused"] == 0
    assert repo.is_channel_paused("moku") is False

    # 2. Third failure trips the breaker for the lane
    _register_turn_failure(db_path, "moku", breaker, "Simulated Error 3", lane_id="moku-horror-long")

    # The failing lane must be paused
    lane_state_long = repo.get_lane_state("moku-horror-long")
    assert lane_state_long is not None
    assert lane_state_long["paused"] == 1
    assert lane_state_long["pause_reason"] == "consecutive_failures"

    # The sibling short lane must NOT be paused
    lane_state_short = repo.get_lane_state("moku-scp-shorts")
    assert lane_state_short is not None
    assert lane_state_short["paused"] == 0

    # The channel itself must remain ACTIVE (not paused!)
    assert repo.is_channel_paused("moku") is False


def test_queue_repository_resume_unpauses_channel_and_associated_lanes(tmp_path: Path):
    db_path = str(tmp_path / "test_queue.db")
    repo = QueueRepository(db_path)
    repo.initialize()

    repo.pause("moku", "test pause")
    repo.set_lane_paused("horror-horror-long", True, "test pause lane")
    repo.set_lane_paused("horror-scp-shorts", True, "test pause lane")

    assert repo.is_channel_paused("moku") is True
    assert (repo.get_lane_state("horror-horror-long") or {})["paused"] == 1

    # Resume channel
    repo.resume("moku")

    assert repo.is_channel_paused("moku") is False
    assert (repo.get_lane_state("horror-horror-long") or {})["paused"] == 0
    assert (repo.get_lane_state("horror-scp-shorts") or {})["paused"] == 0


def test_thumbnail_asset_requests_are_text_free_and_topic_bound():
    seo = SeoOptimizerAgent()
    res1 = seo.optimize(topic="El monstruo del lago negro", target_format="short", niche="horror")
    res2 = seo.optimize(topic="La cabaña desolada en el bosque", target_format="short", niche="horror")

    request1 = res1["thumbnail_asset_request"]
    request2 = res2["thumbnail_asset_request"]
    assert request1["bank"] == request2["bank"] == "local_ai"
    assert request1["text_free"] is True and request2["text_free"] is True
    assert request1["focal_subject"] != request2["focal_subject"]


def test_longform_aelithia_story_diversity_guaranteed_below_qa_limit():
    topic = "Disputa por herencia y cuentas familiares"
    # Populate recent_texts with all base stories
    base_texts = [story(topic) for story in AELITHIA_STORIES]

    # Generating next story against all base stories
    generated = get_aelithia_longform_story(topic, recent_texts=base_texts)
    assert len(generated.split()) >= 1500

    # Must be diverse and not exceed the 0.82 prepublication threshold
    max_sim = max(text_similarity(generated, prev) for prev in base_texts)
    assert max_sim < 0.70, f"Generated story similarity {max_sim:.3f} >= 0.70"


def test_longform_moku_story_diversity_guaranteed_below_qa_limit():
    topic = "La entidad desconocida en el Sector Siete"
    # Populate recent_texts with all base stories
    base_texts = [story(topic) for story in MOKU_STORIES]

    # Generating next story against all base stories
    generated = get_moku_longform_story(topic, recent_texts=base_texts)
    assert len(generated.split()) >= 1500

    # Must be diverse and not exceed the 0.82 prepublication threshold
    max_sim = max(text_similarity(generated, prev) for prev in base_texts)
    assert max_sim < 0.70, f"Generated story similarity {max_sim:.3f} >= 0.70"
