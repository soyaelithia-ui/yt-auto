"""Unit tests for the config-driven production lanes (src/core/lanes.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.core.lanes as lanes_module
from src.core.lanes import (
    LaneProfile,
    fallback_lanes,
    get_lane,
    lanes_for_channel,
    load_lanes,
    parse_lane,
    resolve_lane_for_run,
)


@pytest.fixture(autouse=True)
def _isolate_cache(monkeypatch):
    """Each test starts with a cold lane cache."""
    monkeypatch.setattr(lanes_module, "_LANES_CACHE", None)
    yield


BASE_LANE = {
    "id": "test-lane",
    "channel": "moku",
    "story_type": "scp",
    "orientation": "vertical",
    "duration": {"min_sec": 60, "target_sec": 150, "max_sec": 180},
    "template": "shorts_creepypasta",
    "cadence": {"min_gap_seconds": 300},
}


def _write(tmp_path: Path, document) -> Path:
    target = tmp_path / "lanes.json"
    if isinstance(document, str):
        target.write_text(document, encoding="utf-8")
    else:
        target.write_text(json.dumps(document), encoding="utf-8")
    return target


class TestParseLane:
    def test_minimal_lane_gets_sensible_defaults(self):
        lane = parse_lane(BASE_LANE)
        assert lane.id == "test-lane"
        assert lane.channel.value == "moku"
        assert lane.expected_resolution == (1080, 1920)
        assert lane.qa_profile == "short"
        assert lane.review_content_type == "short"
        assert lane.visual_pipeline == "beats"
        assert lane.multistory_collection is False
        assert lane.enabled is True

    def test_horizontal_lane_defaults_to_longform_qa(self):
        raw = dict(BASE_LANE)
        raw.update({"orientation": "horizontal", "words": {"min": 2600}})
        lane = parse_lane(raw)
        assert lane.expected_resolution == (1920, 1080)
        assert lane.qa_profile == "longform"
        assert lane.review_content_type == "long_video"

    @pytest.mark.parametrize(
        "mutation",
        [
            {"orientation": "square"},
            {"channel": "desconocido"},
            {"cadence": {"min_gap_seconds": 10}},
            {"duration": {"min_sec": 500, "target_sec": 100}},
            {"story_type": "western"},
            {"visual_pipeline": "holodeck"},
            {"topic_filter": {"mode": "psychic"}},
            {"sources": {"kind": "pastebin"}},
        ],
    )
    def test_invalid_values_rejected(self, mutation):
        raw = {**BASE_LANE, **mutation}
        with pytest.raises(ValueError):
            parse_lane(raw)

    def test_words_max_below_min_rejected(self):
        raw = {**BASE_LANE, "words": {"min": 300, "max": 100}}
        with pytest.raises(ValueError):
            parse_lane(raw)

    def test_missing_required_field(self):
        incomplete = {k: v for k, v in BASE_LANE.items() if k != "template"}
        with pytest.raises(ValueError):
            parse_lane(incomplete)


class TestLoadLanes:
    def test_missing_file_falls_back_fail_safe(self, tmp_path, caplog):
        result = load_lanes(tmp_path / "nope.json")
        assert len(result) == len(fallback_lanes()) == 3
        assert any("embebidos" in record.message for record in caplog.records)

    def test_corrupt_file_falls_back(self, tmp_path, caplog):
        path = _write(tmp_path, "{not json")
        result = load_lanes(path)
        assert [lane.id for lane in result] == [
            "moku-scp-shorts",
            "moku-horror-long",
            "aelithia-aita-long",
        ]
        assert any("embebidos" in record.message for record in caplog.records)

    def test_fallback_lanes_have_bounded_word_limits(self):
        lanes = {lane.id: lane for lane in fallback_lanes()}
        assert lanes["moku-horror-long"].words_max == 4800
        assert lanes["moku-horror-long"].words_recondense_max == 4500
        assert lanes["aelithia-aita-long"].words_max == 4800
        assert lanes["aelithia-aita-long"].words_recondense_max == 4500

    def test_valid_document_roundtrip(self, tmp_path):
        path = _write(
            tmp_path,
            {
                "version": 1,
                "lanes": [
                    BASE_LANE,
                    {
                        "id": "second",
                        "channel": "aelithia",
                        "orientation": "horizontal",
                        "duration": {"min_sec": 600},
                        "template": "aita",
                        "enabled": False,
                    },
                ],
            },
        )
        result = load_lanes(path)
        # Disabled lanes are filtered out of the active set.
        assert [lane.id for lane in result] == ["test-lane"]

    def test_duplicate_ids_rejected_falling_back(self, tmp_path, caplog):
        path = _write(tmp_path, {"version": 1, "lanes": [BASE_LANE, dict(BASE_LANE)]})
        result = load_lanes(path)
        assert len(result) == 3
        assert any("embebidos" in record.message for record in caplog.records)

    def test_cache_invalidation_on_rewrite(self, tmp_path):
        path = _write(tmp_path, {"version": 1, "lanes": [BASE_LANE]})
        assert [l.id for l in load_lanes(path)] == ["test-lane"]
        # Rewrite within the same mtime tick must not serve stale content.
        path = _write(
            tmp_path,
            {
                "version": 2,
                "lanes": [
                    {**BASE_LANE, "id": "other-lane"},
                    {
                        "id": "extra",
                        "channel": "aelithia",
                        "orientation": "horizontal",
                        "duration": {"min_sec": 600},
                        "template": "aita",
                    },
                ],
            },
        )
        ids = [lane.id for lane in load_lanes(path)]
        assert ids == ["other-lane", "extra"]


class TestResolution:
    def test_explicit_lane_wins(self):
        lane = resolve_lane_for_run("moku", "moku-horror-long", path="no/such/file")
        assert lane.orientation == "horizontal"

    def test_story_row_lane_used_when_no_explicit(self):
        row = {"lane_id": "moku-horror-long"}
        lane = resolve_lane_for_run("moku", None, story_row=row, path="no/such/file")
        assert lane.id == "moku-horror-long"

    def test_unknown_story_lane_warns_and_defaults(self, caplog):
        row = {"lane_id": "vanished-lane"}
        lane = resolve_lane_for_run("moku", None, story_row=row, path="no/such/file")
        assert lane.id == "moku-scp-shorts"
        assert any("vanished-lane" in record.message for record in caplog.records)

    def test_cross_channel_lane_rejected(self):
        with pytest.raises(ValueError, match="no existe o no pertenece"):
            resolve_lane_for_run("aelithia", "moku-scp-shorts", path="no/such/file")

    def test_default_is_first_enabled_of_channel(self):
        lane = resolve_lane_for_run("aelithia", None, path="no/such/file")
        assert lane.channel.value == "aelithia"

    def test_get_lane_none_when_absent(self):
        assert get_lane("does-not-exist", path="no/such/file") is None

    def test_lanes_for_channel_filters(self):
        moku = lanes_for_channel("moku", path="no/such/file")
        assert all(lane.channel.value == "moku" for lane in moku)


class TestOverrides:
    def test_with_overrides_only_touches_known_fields(self):
        lane = fallback_lanes()[0]
        merged = lane.with_overrides({"voice_rate": "+10%", "unknown_field": 42})
        assert merged.voice_rate == "+10%"
        assert merged is not lane

    def test_empty_overrides_return_same_profile(self):
        lane = fallback_lanes()[0]
        assert lane.with_overrides({}) is lane
