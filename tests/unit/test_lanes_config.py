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
    "channel": "horror",
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
        assert lane.channel.value == "horror"
        assert lane.expected_resolution == (1080, 1920)
        assert lane.qa_profile == "short"
        assert lane.review_content_type == "short"
        assert lane.visual_pipeline == "video_loop"
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

    def test_cadence_initial_offset_seconds_parsed(self):
        raw = {**BASE_LANE, "cadence": {"min_gap_seconds": 600, "initial_offset_seconds": 300}}
        lane = parse_lane(raw)
        assert lane.cadence_min_gap_seconds == 600
        assert lane.cadence_initial_offset_seconds == 300

    def test_negative_initial_offset_rejected(self):
        raw = {**BASE_LANE, "cadence": {"min_gap_seconds": 600, "initial_offset_seconds": -50}}
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
            "horror-scp-shorts",
            "horror-horror-long",
            "drama-aita-long",
        ]
        assert any("embebidos" in record.message for record in caplog.records)

    def test_fallback_lanes_have_bounded_word_limits(self):
        lanes = {lane.id: lane for lane in fallback_lanes()}
        assert lanes["horror-horror-long"].words_max == 4800
        assert lanes["horror-horror-long"].words_recondense_max == 4500
        assert lanes["drama-aita-long"].words_max == 4800
        assert lanes["drama-aita-long"].words_recondense_max == 4500

    def test_valid_document_roundtrip(self, tmp_path):
        path = _write(
            tmp_path,
            {
                "version": 1,
                "lanes": [
                    BASE_LANE,
                    {
                        "id": "second",
                        "channel": "drama",
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
                        "channel": "drama",
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
        lane = resolve_lane_for_run("horror", "horror-horror-long", path="no/such/file")
        assert lane.orientation == "horizontal"

    def test_story_row_lane_used_when_no_explicit(self):
        row = {"lane_id": "horror-horror-long"}
        lane = resolve_lane_for_run("horror", None, story_row=row, path="no/such/file")
        assert lane.id == "horror-horror-long"

    def test_unknown_story_lane_warns_and_defaults(self, caplog):
        row = {"lane_id": "vanished-lane"}
        lane = resolve_lane_for_run("horror", None, story_row=row, path="no/such/file")
        assert lane.id == "horror-scp-shorts"
        assert any("vanished-lane" in record.message for record in caplog.records)

    def test_cross_channel_lane_rejected(self):
        with pytest.raises(ValueError, match="no existe o no pertenece"):
            resolve_lane_for_run("drama", "horror-scp-shorts", path="no/such/file")

    def test_default_is_first_enabled_of_channel(self):
        lane = resolve_lane_for_run("drama", None, path="no/such/file")
        assert lane.channel.value == "drama"

    def test_get_lane_none_when_absent(self):
        assert get_lane("does-not-exist", path="no/such/file") is None

    def test_lanes_for_channel_filters(self):
        horror = lanes_for_channel("horror", path="no/such/file")
        assert all(lane.channel.value == "horror" for lane in horror)

    def test_thematic_lane_aliases_resolve_get_lane(self):
        assert get_lane("horror-scp-shorts") is not None
        assert get_lane("horror-scp-shorts").id == "horror-scp-shorts"
        assert get_lane("horror-long") is not None
        assert get_lane("horror-long").id == "horror-horror-long"
        assert get_lane("drama-shorts") is not None
        assert get_lane("drama-shorts").id == "drama-drama-shorts"
        assert get_lane("drama-aita-long") is not None
        assert get_lane("drama-aita-long").id == "drama-aita-long"

    def test_thematic_and_numbered_channel_aliases_resolve_for_run(self):
        lane_h = resolve_lane_for_run("horror", "horror-scp-shorts")
        assert lane_h.id == "horror-scp-shorts"

        lane_d = resolve_lane_for_run("drama", "drama-aita-long")
        assert lane_d.id == "drama-aita-long"

        lane_c1 = resolve_lane_for_run("canal1", "horror-long")
        assert lane_c1.id == "horror-horror-long"

        lane_c2 = resolve_lane_for_run("canal2", "drama-shorts")
        assert lane_c2.id == "drama-drama-shorts"

        lane_ch1 = resolve_lane_for_run("channel_1", "horror-scp-shorts")
        assert lane_ch1.id == "horror-scp-shorts"

        lane_ch2 = resolve_lane_for_run("channel_2", "drama-aita-long")
        assert lane_ch2.id == "drama-aita-long"


class TestOverrides:
    def test_with_overrides_only_touches_known_fields(self):
        lane = fallback_lanes()[0]
        merged = lane.with_overrides({"voice_rate": "+10%", "unknown_field": 42})
        assert merged.voice_rate == "+10%"
        assert merged is not lane

    def test_empty_overrides_return_same_profile(self):
        lane = fallback_lanes()[0]
        assert lane.with_overrides({}) is lane
