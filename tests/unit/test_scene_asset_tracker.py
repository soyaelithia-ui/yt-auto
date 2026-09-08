"""Unit tests for SceneAssetTracker extracting and recording storyboard assets."""
import json
import pytest
from pathlib import Path
from src.core.repository import QueueRepository
from src.visuals.scene_asset_tracker import SceneAssetTracker

def test_extract_and_record_scene_manifest(tmp_path):
    db_path = tmp_path / "test_queue.db"
    repo = QueueRepository(db_path)
    repo.initialize()

    story_id = "story_manifest_001"
    repo.enqueue(story_id=story_id, title="Manifest Story", content="Content", url="https://reddit.com/r/man1", channel="moku")
    lease = repo.claim("moku", owner="worker_1")
    run_id = lease["run_id"]

    manifest_data = {
        "version": "1.0",
        "channel": "moku",
        "scenes": [
            {
                "scene_index": 0,
                "image_path": "https://images.unsplash.com/photo-spooky",
                "asset_source": "curated_web",
                "framing_type": "WIDE_ESTABLISHING",
                "prompt": "wide misty lake at night",
                "dhash": "0123456789abcdef",
                "duration_sec": 5.0,
            },
            {
                "scene_index": 1,
                "image_path": "/assets/visual_bank/moku/scenery/abyssal_creature.jpg",
                "asset_source": "local_bank",
                "framing_type": "MEDIUM_SUBJECT",
                "prompt": "abandoned cabin",
                "dhash": "fedcba9876543210",
                "duration_sec": 4.2,
            },
        ],
    }
    manifest_path = tmp_path / "scene_manifest.json"
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

    tracker = SceneAssetTracker(repository=repo)
    count = tracker.extract_and_record(run_id=run_id, story_id=story_id, manifest_path=manifest_path)
    assert count == 2

    records = repo.get_scene_assets(story_id=story_id)
    assert len(records) == 2
    assert records[0]["framing_type"] == "WIDE_ESTABLISHING"
    assert records[0]["asset_source"] == "curated_web"
    assert records[1]["framing_type"] == "MEDIUM_SUBJECT"
    assert records[1]["asset_source"] == "local_bank"